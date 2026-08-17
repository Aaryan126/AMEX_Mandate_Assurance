from __future__ import annotations

from app.annotations import AnnotationReview, AnnotationStore

from ml.data.export_annotations import export
from ml.data.schema import AceDatasetExample, DatasetLabels
from tests.data.test_schema_v2 import example


def test_resolved_reviews_are_exported_without_mutating_source(tmp_path) -> None:
    source = tmp_path / "source.jsonl"
    value = example().model_copy(
        update={"labels": DatasetLabels(label_source="unreviewed")}
    )
    source.write_text(value.model_dump_json() + "\n")
    database = tmp_path / "reviews.sqlite3"
    store = AnnotationStore(source, database)
    store.initialize()
    for reviewer in ("reviewer-a", "reviewer-b"):
        store.submit_review(
            value.identity.example_id,
            AnnotationReview(
                reviewer_id=reviewer,
                deviation="MATCH",
                semantic_label="ENTAILMENT",
                expected_treatment="APPROVE",
                confidence=0.9,
            ),
        )

    output = tmp_path / "reviewed.jsonl"
    manifest = export(source, database, output)
    reviewed = AceDatasetExample.model_validate_json(output.read_text())
    original = AceDatasetExample.model_validate_json(source.read_text())
    assert manifest["resolved_reviews"] == 1
    assert reviewed.labels.label_source == "expert_review"
    assert reviewed.labels.semantic[0].label == "ENTAILMENT"
    assert original.labels.label_source == "unreviewed"


def test_llm_reviewer_ids_are_not_misrepresented_as_experts(tmp_path) -> None:
    source = tmp_path / "source.jsonl"
    value = example().model_copy(
        update={"labels": DatasetLabels(label_source="unreviewed")}
    )
    source.write_text(value.model_dump_json() + "\n")
    database = tmp_path / "reviews.sqlite3"
    store = AnnotationStore(source, database)
    store.initialize()
    for reviewer in ("llm-reviewer-a", "llm-reviewer-b"):
        store.submit_review(
            value.identity.example_id,
            AnnotationReview(
                reviewer_id=reviewer,
                deviation="MATCH",
                semantic_label="ENTAILMENT",
                expected_treatment="APPROVE",
                confidence=0.8,
            ),
        )
    output = tmp_path / "reviewed.jsonl"
    export(source, database, output)
    reviewed = AceDatasetExample.model_validate_json(output.read_text())
    assert reviewed.labels.label_source == "llm_consensus"
