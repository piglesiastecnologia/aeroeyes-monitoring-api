from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from aeroeyes_monitoring_api.domain.monitoring_session import (
    MonitoringSession,
    SessionStatus,
)
from aeroeyes_monitoring_api.domain.session_context import SessionContext
from aeroeyes_monitoring_api.persistence.postgres_session_context_repository import (
    PostgresSessionContextRepository,
)
from aeroeyes_monitoring_api.persistence.postgres_session_repository import (
    PostgresSessionRepository,
)

SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000001")
OTHER_SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000002")
UNKNOWN_SESSION_ID = UUID("01890f3d-2d00-7000-8000-000000000099")
STARTED_AT = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


def context(
    session_id: UUID = SESSION_ID,
    *,
    flight_number: str | None = "azul 1234",
    departure_icao: str | None = "sbgr",
    destination_icao: str | None = "sbrj",
) -> SessionContext:
    return SessionContext(
        session_id=session_id,
        flight_number=flight_number,
        departure_icao=departure_icao,
        destination_icao=destination_icao,
    )


def add_monitoring_session(session: Session, session_id: UUID = SESSION_ID) -> None:
    PostgresSessionRepository(session).add(
        MonitoringSession(
            session_id=session_id,
            status=SessionStatus.ACTIVE,
            started_at=STARTED_AT,
        )
    )


def test_get_missing_returns_none(db_session: Session) -> None:
    repository = PostgresSessionContextRepository(db_session)

    assert repository.get(SESSION_ID) is None


def test_save_for_existing_session_returns_and_persists_canonical_values(
    db_session: Session,
) -> None:
    add_monitoring_session(db_session)
    repository = PostgresSessionContextRepository(db_session)
    expected = context()

    saved = repository.save(expected)

    assert saved == expected
    assert saved == SessionContext(
        session_id=SESSION_ID,
        flight_number="AZUL 1234",
        departure_icao="SBGR",
        destination_icao="SBRJ",
    )
    assert repository.get(SESSION_ID) == expected


def test_caller_commit_makes_context_visible_from_fresh_session(
    postgres_engine: Engine,
) -> None:
    expected = context()
    with Session(postgres_engine) as writer:
        add_monitoring_session(writer)
        PostgresSessionContextRepository(writer).save(expected)
        writer.commit()

    with Session(postgres_engine) as reader:
        assert PostgresSessionContextRepository(reader).get(SESSION_ID) == expected


def test_save_same_session_performs_full_replacement(db_session: Session) -> None:
    add_monitoring_session(db_session)
    repository = PostgresSessionContextRepository(db_session)
    repository.save(context())
    replacement = context(
        flight_number="gol 4321",
        departure_icao="sbrf",
        destination_icao="sbsp",
    )

    saved = repository.save(replacement)

    assert saved == replacement
    assert repository.get(SESSION_ID) == replacement


def test_replacement_clears_populated_fields_with_none(db_session: Session) -> None:
    add_monitoring_session(db_session)
    repository = PostgresSessionContextRepository(db_session)
    repository.save(context())
    replacement = context(
        flight_number=None,
        departure_icao=None,
        destination_icao=None,
    )

    repository.save(replacement)

    assert repository.get(SESSION_ID) == replacement


def test_all_null_context_persists_and_reloads(db_session: Session) -> None:
    add_monitoring_session(db_session)
    repository = PostgresSessionContextRepository(db_session)
    expected = context(
        flight_number=None,
        departure_icao=None,
        destination_icao=None,
    )

    assert repository.save(expected) == expected
    assert repository.get(SESSION_ID) == expected


def test_two_sessions_have_independent_contexts(db_session: Session) -> None:
    add_monitoring_session(db_session)
    add_monitoring_session(db_session, OTHER_SESSION_ID)
    repository = PostgresSessionContextRepository(db_session)
    first = context()
    second = context(
        OTHER_SESSION_ID,
        flight_number="latam 9876",
        departure_icao="sbsp",
        destination_icao="sbcf",
    )

    repository.save(first)
    repository.save(second)

    assert repository.get(SESSION_ID) == first
    assert repository.get(OTHER_SESSION_ID) == second


def test_delete_existing_returns_true_and_caller_commit_removes_row(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as setup:
        add_monitoring_session(setup)
        PostgresSessionContextRepository(setup).save(context())
        setup.commit()

    with Session(postgres_engine) as writer:
        assert PostgresSessionContextRepository(writer).delete(SESSION_ID) is True
        writer.commit()

    with Session(postgres_engine) as reader:
        assert PostgresSessionContextRepository(reader).get(SESSION_ID) is None


def test_delete_missing_returns_false(db_session: Session) -> None:
    repository = PostgresSessionContextRepository(db_session)

    assert repository.delete(SESSION_ID) is False


def test_save_for_unknown_parent_preserves_postgresql_fk_error(
    db_session: Session,
) -> None:
    repository = PostgresSessionContextRepository(db_session)

    with pytest.raises(IntegrityError) as raised:
        repository.save(context(UNKNOWN_SESSION_ID))

    assert raised.value.orig.sqlstate == "23503"
    db_session.rollback()


def test_save_followed_by_caller_rollback_does_not_persist(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as setup:
        add_monitoring_session(setup)
        setup.commit()

    with Session(postgres_engine) as writer:
        PostgresSessionContextRepository(writer).save(context())
        writer.rollback()

    with Session(postgres_engine) as reader:
        assert PostgresSessionContextRepository(reader).get(SESSION_ID) is None


def test_delete_followed_by_caller_rollback_preserves_context(
    postgres_engine: Engine,
) -> None:
    expected = context()
    with Session(postgres_engine) as setup:
        add_monitoring_session(setup)
        PostgresSessionContextRepository(setup).save(expected)
        setup.commit()

    with Session(postgres_engine) as writer:
        assert PostgresSessionContextRepository(writer).delete(SESSION_ID) is True
        writer.rollback()

    with Session(postgres_engine) as reader:
        assert PostgresSessionContextRepository(reader).get(SESSION_ID) == expected
