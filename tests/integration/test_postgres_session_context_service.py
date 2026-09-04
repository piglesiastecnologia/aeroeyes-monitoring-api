from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.domain.session_context import SessionContext
from aeroeyes_monitoring_api.persistence.database import create_session_factory
from aeroeyes_monitoring_api.persistence.postgres_session_repository import (
    PostgresSessionRepository,
)
from aeroeyes_monitoring_api.persistence.postgres_unit_of_work import (
    PostgresUnitOfWork,
)
from aeroeyes_monitoring_api.session_context_service import SessionContextService
from aeroeyes_monitoring_api.session_service import SessionNotFoundError

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
MISSING_SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000099")
STARTED_AT = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
COMPLETED_AT = STARTED_AT + timedelta(minutes=30)


def seed_session(
    engine: Engine,
    status: SessionStatus = SessionStatus.ACTIVE,
) -> None:
    with Session(engine) as database_session, database_session.begin():
        PostgresSessionRepository(database_session).add(
            MonitoringSession(
                session_id=SESSION_ID,
                status=status,
                started_at=STARTED_AT,
                ended_at=COMPLETED_AT if status is SessionStatus.COMPLETED else None,
            )
        )


def service_for(engine: Engine) -> SessionContextService:
    session_factory = create_session_factory(engine)
    return SessionContextService(lambda: PostgresUnitOfWork(session_factory))


def test_replace_creates_and_commits_context(postgres_engine: Engine) -> None:
    seed_session(postgres_engine)
    service = service_for(postgres_engine)

    created = service.replace_context(
        SESSION_ID,
        flight_number=" la8084 ",
        departure_icao=" sbgr ",
        destination_icao=" sbrj ",
    )

    assert created == SessionContext(
        session_id=SESSION_ID,
        flight_number="LA8084",
        departure_icao="SBGR",
        destination_icao="SBRJ",
    )
    assert service.get_context(SESSION_ID) == created


def test_replace_existing_context_is_full_replacement(postgres_engine: Engine) -> None:
    seed_session(postgres_engine)
    service = service_for(postgres_engine)
    service.replace_context(
        SESSION_ID,
        flight_number="LA8084",
        departure_icao="SBGR",
        destination_icao="SBGL",
    )

    replaced = service.replace_context(SESSION_ID, departure_icao="SBSP")

    assert replaced == SessionContext(session_id=SESSION_ID, departure_icao="SBSP")
    assert service.get_context(SESSION_ID) == replaced


def test_delete_commits_context_removal(postgres_engine: Engine) -> None:
    seed_session(postgres_engine)
    service = service_for(postgres_engine)
    service.replace_context(SESSION_ID, flight_number="LA8084")

    assert service.delete_context(SESSION_ID) is True
    assert service.delete_context(SESSION_ID) is False


def test_missing_session_does_not_create_orphan_context(postgres_engine: Engine) -> None:
    service = service_for(postgres_engine)

    with pytest.raises(SessionNotFoundError):
        service.replace_context(MISSING_SESSION_ID, flight_number="LA8084")

    with PostgresUnitOfWork(create_session_factory(postgres_engine)) as verification:
        assert verification.contexts.get(MISSING_SESSION_ID) is None


def test_completed_session_context_can_be_replaced_and_deleted(
    postgres_engine: Engine,
) -> None:
    seed_session(postgres_engine, SessionStatus.COMPLETED)
    service = service_for(postgres_engine)

    replaced = service.replace_context(SESSION_ID, destination_icao="SBRJ")

    assert replaced.destination_icao == "SBRJ"
    assert service.delete_context(SESSION_ID) is True
    assert service.delete_context(SESSION_ID) is False
