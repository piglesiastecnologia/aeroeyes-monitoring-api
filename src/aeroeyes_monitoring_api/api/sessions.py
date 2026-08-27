from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict

from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.session_service import (
    SessionNotFoundError,
    SessionService,
)


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None


def create_sessions_router(service: SessionService) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/sessions",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_session(response: Response) -> MonitoringSession:
        session = service.create_session()
        response.headers["Location"] = f"/sessions/{session.session_id}"
        return session

    @router.get(
        "/sessions/{session_id}",
        response_model=SessionResponse,
    )
    def get_session(session_id: UUID) -> MonitoringSession:
        try:
            return service.get_session(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            ) from error

    @router.post(
        "/sessions/{session_id}/complete",
        response_model=SessionResponse,
    )
    def complete_session(session_id: UUID) -> MonitoringSession:
        try:
            return service.complete_session(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            ) from error

    return router
