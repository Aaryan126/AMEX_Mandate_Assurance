from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from ml.data.schema import (
    AceDatasetExample,
    DatasetLabels,
    DeviationLabel,
    SemanticAnnotation,
    SemanticLabel,
)


def _signature(value: dict[str, Any]) -> tuple[Any, ...]:
    return (
        value["deviation"],
        value["semantic_label"],
        value["expected_treatment"],
        tuple(sorted(value.get("violation_types", []))),
    )


def _semantic_labels(
    example: AceDatasetExample, label: SemanticLabel
) -> list[SemanticAnnotation]:
    return [
        SemanticAnnotation(
            constraint_id=value.constraint_id,
            label=label,
            confidence=1.0,
        )
        for value in example.mandate.constraints
        if value.type == "semantic_attribute"
    ]


def resolved_reviews(
    database_path: Path,
) -> dict[str, tuple[dict[str, Any], str, float]]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    adjudications = {
        row["example_id"]: json.loads(row["payload_json"])
        for row in connection.execute(
            "SELECT example_id, payload_json FROM annotation_adjudications"
        )
    }
    reviews: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in connection.execute(
        "SELECT example_id, payload_json FROM annotation_reviews"
    ):
        reviews[row["example_id"]].append(json.loads(row["payload_json"]))
    connection.close()
    resolved: dict[str, tuple[dict[str, Any], str, float]] = {}
    for example_id, values in reviews.items():
        if example_id in adjudications:
            value = adjudications[example_id]
            source_name = (
                "llm_adjudicated"
                if str(value.get("adjudicator_id", "")).startswith("llm-")
                else "adjudicated_review"
            )
            resolved[example_id] = (
                value,
                source_name,
                float(value["confidence"]),
            )
        elif len(values) >= 2 and len({_signature(value) for value in values}) == 1:
            llm_count = sum(
                str(value.get("reviewer_id", "")).startswith("llm-")
                for value in values
            )
            source_name = (
                "llm_consensus"
                if llm_count == len(values)
                else "expert_review"
                if llm_count == 0
                else "mixed_review"
            )
            resolved[example_id] = (
                values[0],
                source_name,
                sum(float(value["confidence"]) for value in values) / len(values),
            )
    return resolved


def export(
    dataset_path: Path, database_path: Path, output_path: Path
) -> dict[str, Any]:
    reviews = resolved_reviews(database_path)
    counts = {"rows": 0, "resolved_reviews": 0, "unresolved_reviews": 0}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with dataset_path.open() as source, output_path.open("w") as output:
        for line in source:
            if not line.strip():
                continue
            example = AceDatasetExample.model_validate_json(line)
            resolved = reviews.get(example.identity.example_id)
            if example.labels.label_source == "unreviewed":
                if resolved is None:
                    counts["unresolved_reviews"] += 1
                else:
                    review, source_name, confidence = resolved
                    deviation = DeviationLabel(review["deviation"])
                    example.labels = DatasetLabels(
                        deviation=deviation,
                        semantic=_semantic_labels(
                            example, SemanticLabel(review["semantic_label"])
                        ),
                        violation_types=review.get("violation_types", []),
                        expected_treatment=review["expected_treatment"],
                        label_source=source_name,
                        reviewer_confidence=confidence,
                    )
                    counts["resolved_reviews"] += 1
            output.write(example.model_dump_json() + "\n")
            counts["rows"] += 1
    manifest = {
        **counts,
        "source_dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "review_database_sha256": hashlib.sha256(
            database_path.read_bytes()
        ).hexdigest(),
        "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
    }
    output_path.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.dataset, args.reviews, args.output), indent=2))


if __name__ == "__main__":
    main()
