from __future__ import annotations

import os
from dataclasses import dataclass

from .treatment_contract import POLICY_VERSION


def _boolean_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("ACE_DATABASE_URL", "sqlite:///./ace.sqlite3")
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("ACE_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        if origin.strip()
    )
    model_mode: str = os.getenv("ACE_MODEL_MODE", "heuristic")
    schema_version: str = "1.0"
    policy_version: str = POLICY_VERSION
    feature_version: str = "features-v2"
    annotation_enabled: bool = _boolean_env("ACE_ANNOTATION_ENABLED")
    annotation_dataset: str = os.getenv(
        "ACE_ANNOTATION_DATASET",
        "ml/data/generated/option1-en/ace-esci-en-hybrid.jsonl",
    )
    annotation_database: str = os.getenv(
        "ACE_ANNOTATION_DATABASE",
        "ml/data/annotations/reviews-option1-en.sqlite3",
    )


settings = Settings()
