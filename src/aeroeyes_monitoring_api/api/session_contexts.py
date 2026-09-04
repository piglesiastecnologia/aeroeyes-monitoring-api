from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict

from aeroeyes_monitoring_api.domain.session_context import SessionContext
from aeroeyes_monitoring_api.session_context_service import (
    SessionContextNotFoundError,
    SessionContextService,
)
from aeroeyes_monitoring_api.session_service import SessionNotFoundError


class SessionContextReplaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flight_number: str | None = None
    departure_icao: str | None = None
    destination_icao: str | None = None


class SessionContextResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    flight_number: str | None
    departure_icao: str | None
    destination_icao: str | None


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _session_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_error_detail("SESSION_NOT_FOUND", "Session not found"),
    )


def create_session_contexts_router(service: SessionContextService) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/sessions/{session_id}/context",
        response_model=SessionContextResponse,
    )
    def get_context(session_id: UUID) -> SessionContext:
        try:
            return service.get_context(session_id)
        except SessionNotFoundError as error:
            raise _session_not_found() from error
        except SessionContextNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_error_detail(
                    "SESSION_CONTEXT_NOT_FOUND",
                    "Session context not found",
                ),
            ) from error

    @router.put(
        "/sessions/{session_id}/context",
        response_model=SessionContextResponse,
    )
    def replace_context(
        session_id: UUID,
        request: SessionContextReplaceRequest,
    ) -> SessionContext:
        try:
            return service.replace_context(
                session_id,
                flight_number=request.flight_number,
                departure_icao=request.departure_icao,
                destination_icao=request.destination_icao,
            )
        except SessionNotFoundError as error:
            raise _session_not_found() from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_error_detail(
                    "INVALID_SESSION_CONTEXT",
                    str(error),
                ),
            ) from error

    @router.delete(
        "/sessions/{session_id}/context",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_context(session_id: UUID) -> Response:
        try:
            service.delete_context(session_id)
        except SessionNotFoundError as error:
            raise _session_not_found() from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
