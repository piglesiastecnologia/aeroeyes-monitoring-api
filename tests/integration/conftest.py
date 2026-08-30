import os
from collections.abc import Iterator

import pytest
from sqlalchemy import delete
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from aeroeyes_monitoring_api.persistence.database import Base, create_database_engine
from aeroeyes_monitoring_api.persistence.models import (
    AttentionEventRecord,
    MonitoringSessionRecord,
)

TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"


@pytest.fixture(scope="session")
def postgres_engine() -> Iterator[Engine]:
    database_url = os.environ.get(TEST_DATABASE_URL_ENV, "").strip()
    if not database_url:
        pytest.skip(f"{TEST_DATABASE_URL_ENV} is required for PostgreSQL tests")

    engine = create_database_engine(database_url)
    Base.metadata.create_all(engine)

    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(postgres_engine: Engine) -> Iterator[None]:
    _delete_test_data(postgres_engine)
    yield
    _delete_test_data(postgres_engine)


@pytest.fixture
def db_session(postgres_engine: Engine) -> Iterator[Session]:
    with Session(postgres_engine, expire_on_commit=False) as session:
        yield session


def _delete_test_data(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        session.execute(delete(AttentionEventRecord))
        session.execute(delete(MonitoringSessionRecord))
