import os
from collections.abc import Mapping

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL_ENV = "DATABASE_URL"

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def database_url_from_env(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    database_url = source.get(DATABASE_URL_ENV, "").strip()
    if not database_url:
        raise RuntimeError(f"{DATABASE_URL_ENV} must be set")
    return database_url


def create_database_engine(database_url: str) -> Engine:
    return create_engine(
        database_url,
        connect_args={"options": "-c timezone=UTC"},
        pool_pre_ping=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
