from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


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

