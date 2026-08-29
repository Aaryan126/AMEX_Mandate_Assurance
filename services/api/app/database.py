from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import settings


class Base(DeclarativeBase):
    pass


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_CONFIG = REPOSITORY_ROOT / "services/api/alembic.ini"
MIGRATIONS_PATH = REPOSITORY_ROOT / "services/api/migrations"


def build_engine(database_url: str):
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        kwargs["poolclass"] = StaticPool
    return create_engine(database_url, **kwargs)


engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _migration_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_CONFIG))
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["use_environment_url"] = False
    return config


def _bootstrap_unversioned_legacy_schema(database_engine: Engine, config: Config) -> None:
    inspector = inspect(database_engine)
    existing_tables = set(inspector.get_table_names())
    if not existing_tables or "alembic_version" in existing_tables:
        return

    expected_tables = set(Base.metadata.tables)
    if existing_tables != expected_tables:
        raise RuntimeError(
            "Existing unversioned database does not match a recognized Mandate Assurance schema. "
            "Back it up and run an explicit migration before starting the API."
        )

    allowed_missing = {("mandate_state", "row_version")}
    differences: list[str] = []
    for table_name, table in Base.metadata.tables.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        expected_columns = set(table.columns.keys())
        missing = expected_columns - actual_columns
        extra = actual_columns - expected_columns
        if any((table_name, column) not in allowed_missing for column in missing) or extra:
            differences.append(
                f"{table_name}: missing={sorted(missing)}, extra={sorted(extra)}"
            )
    if differences:
        raise RuntimeError(
            "Existing unversioned database has unsupported schema differences: " + "; ".join(differences)
        )

    # Databases created by the pre-Alembic prototype already contain the 0001 tables.
    # Stamping avoids recreating them; 0002 then adds row_version without deleting data.
    command.stamp(config, "0001")


def migrate_schema(database_url: str, database_engine: Engine | None = None) -> None:
    from . import models  # noqa: F401

    target_engine = database_engine or build_engine(database_url)
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        Base.metadata.create_all(target_engine)
        return

    config = _migration_config(database_url)
    _bootstrap_unversioned_legacy_schema(target_engine, config)
    command.upgrade(config, "head")

    inspector = inspect(target_engine)
    missing_columns = {
        table_name: sorted(
            set(table.columns.keys())
            - {column["name"] for column in inspector.get_columns(table_name)}
        )
        for table_name, table in Base.metadata.tables.items()
        if table_name in inspector.get_table_names()
    }
    missing_columns = {table: columns for table, columns in missing_columns.items() if columns}
    if missing_columns:
        raise RuntimeError(f"Database migration completed with missing columns: {missing_columns}")


def create_schema() -> None:
    migrate_schema(settings.database_url, engine)
