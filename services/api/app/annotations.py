from __future__ import annotations

import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .config import settings


class AnnotationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9_.@-]+$")
    deviation: Literal["MATCH", "VIOLATION", "AMBIGUOUS"]
    semantic_label: Literal["ENTAILMENT", "CONTRADICTION", "NEUTRAL"]
    expected_treatment: Literal["APPROVE", "STEP_UP", "HOLD"]
    violation_types: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0, le=1)
    notes: str = Field(default="", max_length=2_000)


class AnnotationDecision(AnnotationReview):
    adjudicator_id: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9_.@-]+$")


class AnnotationItem(BaseModel):
    example: dict[str, Any]
    completed_reviews: int
    needs_adjudication: bool


class AnnotationProgress(BaseModel):
    total: int
    unreviewed: int
    single_review: int
    agreed: int
    needs_adjudication: int
    adjudicated: int


class AnnotationStore:
    """A deliberately separate, local-only review store for immutable dataset examples."""

    def __init__(self, dataset_path: Path, database_path: Path):
        self.dataset_path = dataset_path
        self.database_path = database_path
        self._lock = Lock()

    def initialize(self) -> None:
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"annotation dataset not found: {self.dataset_path}")
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS annotation_examples (
                    example_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    split_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS annotation_reviews (
                    example_id TEXT NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (example_id, reviewer_id),
                    FOREIGN KEY (example_id) REFERENCES annotation_examples(example_id)
                );
                CREATE TABLE IF NOT EXISTS annotation_adjudications (
                    example_id TEXT PRIMARY KEY,
                    adjudicator_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (example_id) REFERENCES annotation_examples(example_id)
                );
                """
            )
            with self.dataset_path.open() as source:
                for line_number, line in enumerate(source, 1):
                    if not line.strip():
                        continue
                    payload = json.loads(line)
                    if payload.get("labels", {}).get("label_source") != "unreviewed":
                        continue
                    try:
                        identity = payload["identity"]
                        split = payload["split"]["name"]
                    except (KeyError, TypeError) as exc:
                        raise ValueError(f"invalid annotation row at line {line_number}") from exc
                    connection.execute(
                        """INSERT INTO annotation_examples(example_id, group_id, split_name, payload_json)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(example_id) DO UPDATE SET
                             group_id=excluded.group_id,
                             split_name=excluded.split_name,
                             payload_json=excluded.payload_json""",
                        (identity["example_id"], identity["group_id"], split, json.dumps(payload)),
                    )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @staticmethod
    def _review_signature(payload: dict[str, Any]) -> tuple[Any, ...]:
        return (
            payload["deviation"],
            payload["semantic_label"],
            payload["expected_treatment"],
            tuple(sorted(payload.get("violation_types", []))),
        )

    def next_item(self, reviewer_id: str, *, adjudication_only: bool = False) -> AnnotationItem | None:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT e.payload_json,
                          COUNT(r.reviewer_id) AS review_count,
                          GROUP_CONCAT(r.payload_json, char(30)) AS reviews,
                          MAX(CASE WHEN r.reviewer_id = ? THEN 1 ELSE 0 END) AS reviewed_by_requester,
                          MAX(CASE WHEN a.example_id IS NOT NULL THEN 1 ELSE 0 END) AS adjudicated
                   FROM annotation_examples e
                   LEFT JOIN annotation_reviews r ON r.example_id=e.example_id
                   LEFT JOIN annotation_adjudications a ON a.example_id=e.example_id
                   GROUP BY e.example_id
                   HAVING reviewed_by_requester=0 AND adjudicated=0
                   ORDER BY review_count ASC, e.example_id ASC""",
                (reviewer_id,),
            ).fetchall()
        for row in rows:
            reviews = [json.loads(value) for value in (row["reviews"] or "").split(chr(30)) if value]
            disagreement = len(reviews) >= 2 and len({self._review_signature(value) for value in reviews}) > 1
            if adjudication_only != disagreement:
                continue
            if not adjudication_only and row["review_count"] >= 2:
                continue
            return AnnotationItem(
                example=json.loads(row["payload_json"]),
                completed_reviews=row["review_count"],
                needs_adjudication=disagreement,
            )
        return None

    def submit_review(self, example_id: str, review: AnnotationReview) -> None:
        payload = review.model_dump_json()
        with self._lock, closing(self._connect()) as connection:
            try:
                connection.execute(
                    "INSERT INTO annotation_reviews(example_id, reviewer_id, payload_json) VALUES (?, ?, ?)",
                    (example_id, review.reviewer_id, payload),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                if not connection.execute(
                    "SELECT 1 FROM annotation_examples WHERE example_id=?", (example_id,)
                ).fetchone():
                    raise KeyError(example_id) from exc
                raise ValueError("this reviewer already submitted a label for the example") from exc

    def adjudicate(self, example_id: str, decision: AnnotationDecision) -> None:
        with self._lock, closing(self._connect()) as connection:
            review_count = connection.execute(
                "SELECT COUNT(*) FROM annotation_reviews WHERE example_id=?", (example_id,)
            ).fetchone()[0]
            if review_count < 2:
                raise ValueError("two independent reviews are required before adjudication")
            try:
                connection.execute(
                    "INSERT INTO annotation_adjudications(example_id, adjudicator_id, payload_json) VALUES (?, ?, ?)",
                    (example_id, decision.adjudicator_id, decision.model_dump_json()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("this example has already been adjudicated") from exc
            connection.commit()

    def progress(self) -> AnnotationProgress:
        counts: Counter[str] = Counter()
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT e.example_id, COUNT(r.reviewer_id) AS review_count,
                          GROUP_CONCAT(r.payload_json, char(30)) AS reviews,
                          MAX(CASE WHEN a.example_id IS NOT NULL THEN 1 ELSE 0 END) AS adjudicated
                   FROM annotation_examples e
                   LEFT JOIN annotation_reviews r ON r.example_id=e.example_id
                   LEFT JOIN annotation_adjudications a ON a.example_id=e.example_id
                   GROUP BY e.example_id"""
            ).fetchall()
        for row in rows:
            if row["adjudicated"]:
                counts["adjudicated"] += 1
            elif row["review_count"] == 0:
                counts["unreviewed"] += 1
            elif row["review_count"] == 1:
                counts["single_review"] += 1
            else:
                reviews = [json.loads(value) for value in row["reviews"].split(chr(30))]
                signatures = {self._review_signature(value) for value in reviews}
                key = "agreed" if len(signatures) == 1 else "needs_adjudication"
                counts[key] += 1
        fields = {key: counts[key] for key in AnnotationProgress.model_fields if key != "total"}
        return AnnotationProgress(total=len(rows), **fields)


_store: AnnotationStore | None = None


def configured_annotation_store() -> AnnotationStore:
    global _store
    if not settings.annotation_enabled:
        raise HTTPException(status_code=404, detail="annotation service is disabled")
    if _store is None:
        _store = AnnotationStore(Path(settings.annotation_dataset), Path(settings.annotation_database))
        _store.initialize()
    return _store
