from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import (
    UUID7,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
)

from aeroeyes_monitoring_api.domain.attention_event import (
    AttentionSeverity,
    AttentionState,
    EyeState,
)
from aeroeyes_monitoring_api.event_ingestion_service import (
    EventConflictError,
    EventIngestionService,
    EventOutsideSessionError,
    UnsupportedSchemaVersionError,
)
from aeroeyes_monitoring_api.event_repository import EventAcceptanceStatus
from aeroeyes_monitoring_api.session_service import SessionNotFoundError


class EventCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID7
    occurred_at: datetime
    state: AttentionState
    severity: AttentionSeverity
    face_detected: StrictBool
    eye_state: EyeState | None
    closed_duration_ms: Annotated[StrictInt, Field(ge=0)] | None
    schema_version: StrictInt

    @field_validator("occurred_at", mode="before")
    @classmethod
    def require_rfc3339_string(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("occurred_at must be an RFC3339 string")
        return value

    @field_validator("occurred_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("occurred_at must be timezone-aware UTC")
        return value


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    session_id: UUID
    occurred_at: datetime
    received_at: datetime
    state: AttentionState
    severity: AttentionSeverity
    face_detected: bool
    eye_state: EyeState | None
    closed_duration_ms: int | None
    schema_version: int


class EventIngestionResponse(BaseModel):
    status: Literal["created", "already_processed"]
    event: EventResponse


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def create_events_router(service: EventIngestionService) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/sessions/{session_id}/events",
        response_model=EventIngestionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def ingest_event(
        session_id: UUID,
        request: EventCreateRequest,
        response: Response,
    ) -> EventIngestionResponse:
        try:
            result = service.ingest(
                session_id,
                event_id=request.event_id,
                occurred_at=request.occurred_at,
                state=request.state,
                severity=request.severity,
                face_detected=request.face_detected,
                eye_state=request.eye_state,
                closed_duration_ms=request.closed_duration_ms,
                schema_version=request.schema_version,
            )
        except UnsupportedSchemaVersionError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_error_detail(
                    "UNSUPPORTED_SCHEMA_VERSION",
                    "Unsupported event schema version",
                ),
            ) from error
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_error_detail(
                    "SESSION_NOT_FOUND",
                    "Session not found",
                ),
            ) from error
        except EventOutsideSessionError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_error_detail(
                    "EVENT_OUTSIDE_SESSION",
                    "Event occurred outside the session window",
                ),
            ) from error
        except EventConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_error_detail(
                    "EVENT_ID_CONFLICT",
                    "Event ID is already bound to a different event",
                ),
            ) from error

        if result.status is EventAcceptanceStatus.ALREADY_PROCESSED:
            response.status_code = status.HTTP_200_OK
            result_status = "already_processed"
        else:
            result_status = "created"

        return EventIngestionResponse(
            status=result_status,
            event=EventResponse.model_validate(result.event),
        )

    return router
