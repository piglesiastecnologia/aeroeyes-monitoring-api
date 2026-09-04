from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from aeroeyes_monitoring_api.domain.session_context import SessionContext
from aeroeyes_monitoring_api.persistence.models import SessionContextRecord


class PostgresSessionContextRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, session_id: UUID) -> SessionContext | None:
        record = self._session.scalar(
            select(SessionContextRecord).where(
                SessionContextRecord.session_id == session_id
            )
        )
        if record is None:
            return None
        return _record_to_domain(record)

    def save(self, context: SessionContext) -> SessionContext:
        statement = (
            insert(SessionContextRecord)
            .values(
                session_id=context.session_id,
                flight_number=context.flight_number,
                departure_icao=context.departure_icao,
                destination_icao=context.destination_icao,
            )
            .on_conflict_do_update(
                index_elements=[SessionContextRecord.session_id],
                set_={
                    "flight_number": context.flight_number,
                    "departure_icao": context.departure_icao,
                    "destination_icao": context.destination_icao,
                },
            )
            .returning(
                SessionContextRecord.session_id,
                SessionContextRecord.flight_number,
                SessionContextRecord.departure_icao,
                SessionContextRecord.destination_icao,
            )
        )

        persisted = self._session.execute(statement).one()
        return _row_to_domain(persisted)

    def delete(self, session_id: UUID) -> bool:
        statement = (
            delete(SessionContextRecord)
            .where(SessionContextRecord.session_id == session_id)
            .returning(SessionContextRecord.session_id)
        )
        return self._session.scalar(statement) is not None


def _record_to_domain(record: SessionContextRecord) -> SessionContext:
    return SessionContext(
        session_id=record.session_id,
        flight_number=record.flight_number,
        departure_icao=record.departure_icao,
        destination_icao=record.destination_icao,
    )


def _row_to_domain(
    row: Row[tuple[UUID, str | None, str | None, str | None]],
) -> SessionContext:
    return SessionContext(
        session_id=row.session_id,
        flight_number=row.flight_number,
        departure_icao=row.departure_icao,
        destination_icao=row.destination_icao,
    )
