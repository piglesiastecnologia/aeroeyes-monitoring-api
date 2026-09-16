from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from aeroeyes_monitoring_api.api.events import EventResponse
from aeroeyes_monitoring_api.session_attention_state_service import (
    SessionAttentionStateService,
)
from aeroeyes_monitoring_api.session_service import SessionNotFoundError


class SessionAttentionStateResponse(BaseModel):
    session_id: UUID
    availability: Literal["NO_DATA", "AVAILABLE"]
    latest_event: EventResponse | None


class RecentAttentionEventsResponse(BaseModel):
    session_id: UUID
    events: list[EventResponse]


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def create_attention_states_router(
    service: SessionAttentionStateService,
) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/sessions/{session_id}/attention-state",
        response_model=SessionAttentionStateResponse,
    )
    def get_session_attention_state(
        session_id: UUID,
    ) -> SessionAttentionStateResponse:
        try:
            latest_event = service.get_latest_event(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_error_detail(
                    "SESSION_NOT_FOUND",
                    "Session not found",
                ),
            ) from error

        return SessionAttentionStateResponse(
            session_id=session_id,
            availability=(
                "NO_DATA" if latest_event is None else "AVAILABLE"
            ),
            latest_event=(
                None
                if latest_event is None
                else EventResponse.model_validate(latest_event)
            ),
        )

    @router.get(
        "/sessions/{session_id}/events",
        response_model=RecentAttentionEventsResponse,
    )
    def get_recent_attention_events(
        session_id: UUID,
        limit: Annotated[int, Query(ge=1, le=50)] = 10,
    ) -> RecentAttentionEventsResponse:
        try:
            events = service.get_recent_events(session_id, limit=limit)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_error_detail(
                    "SESSION_NOT_FOUND",
                    "Session not found",
                ),
            ) from error

        return RecentAttentionEventsResponse(
            session_id=session_id,
            events=[EventResponse.model_validate(event) for event in events],
        )

    return router
