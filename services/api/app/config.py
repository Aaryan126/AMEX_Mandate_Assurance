from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("ACE_DATABASE_URL", "sqlite:///./ace.sqlite3")
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "ACE_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if origin.strip()
    )
    model_mode: str = os.getenv("ACE_MODEL_MODE", "heuristic")
    schema_version: str = "1.0"
    policy_version: str = "policy-v1"
    feature_version: str = "features-v1"


settings = Settings()
