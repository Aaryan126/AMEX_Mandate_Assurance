from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app import models  # noqa: F401
from app.database import Base, migrate_schema


def test_initial_migration_creates_expected_tables(tmp_path: Path) -> None:
    database = tmp_path / "migration.sqlite3"
    config = Config("services/api/alembic.ini")
    config.set_main_option("script_location", str(Path("services/api/migrations").resolve()))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    command.upgrade(config, "head")
    tables = set(inspect(create_engine(f"sqlite:///{database}")).get_table_names())
    assert {
        "mandates",
        "mandate_constraints",
        "mandate_state",
        "carts",
        "cart_line_items",
        "decisions",
        "decision_signals",
        "resolutions",
        "audit_events",
        "idempotency_keys",
        "model_registry",
    } <= tables
    assert "row_version" in {
        column["name"] for column in inspect(create_engine(f"sqlite:///{database}")).get_columns("mandate_state")
    }


def test_unversioned_legacy_database_is_upgraded_without_data_loss(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    database_url = f"sqlite:///{database}"
    legacy_engine = create_engine(database_url)
    Base.metadata.create_all(legacy_engine)
    with legacy_engine.begin() as connection:
        connection.execute(text("ALTER TABLE mandate_state DROP COLUMN row_version"))
        connection.execute(
            text(
                "INSERT INTO mandates "
                "(id, version, principal_id, agent_id, payload_json, authorization_reference, "
                "status, authenticated_at, created_at) VALUES "
                "('legacy-mandate', 1, 'principal', 'agent', '{}', 'signature', "
                "'active', '2026-08-29T00:00:00Z', '2026-08-29T00:00:00Z')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO mandate_state "
                "(mandate_id, current_version, status, fulfilled_amount_minor, fulfillment_count, "
                "prior_transaction_ids_json, last_updated_at) VALUES "
                "('legacy-mandate', 1, 'active', 4200, 1, '[]', '2026-08-29T00:00:00Z')"
            )
        )

    migrate_schema(database_url, legacy_engine)

    migrated = inspect(legacy_engine)
    assert "row_version" in {column["name"] for column in migrated.get_columns("mandate_state")}
    with legacy_engine.connect() as connection:
        state = connection.execute(
            text(
                "SELECT fulfilled_amount_minor, fulfillment_count, row_version "
                "FROM mandate_state WHERE mandate_id = 'legacy-mandate'"
            )
        ).one()
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert state == (4200, 1, 0)
    assert revision == "0002"
