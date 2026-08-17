from __future__ import annotations

import json

from app.annotations import AnnotationReview, AnnotationStore

from ml.data.export_annotations import export
from ml.data.llm_annotations import (
    MODEL_A,
    REVIEWER_A,
    REVIEWER_B,
    _api_key,
    batch_request,
    import_output,
    prepare_adjudications,
    prepare_reviews,
)
from ml.data.schema import AceDatasetExample, DatasetLabels
from tests.data.test_schema_v2 import example


def _unreviewed() -> AceDatasetExample:
    return example().model_copy(
        update={"labels": DatasetLabels(label_source="unreviewed")}
    )


def _batch_output(reviewer_id: str, example_id: str, deviation: str = "MATCH") -> dict:
    payload = {
        "deviation": deviation,
        "semantic_label": "ENTAILMENT" if deviation == "MATCH" else "CONTRADICTION",
        "expected_treatment": "APPROVE" if deviation == "MATCH" else "STEP_UP",
        "violation_types": [] if deviation == "MATCH" else ["semantic_mismatch"],
        "confidence": 0.9,
        "notes": "Evidence supports the selected label.",
    }
    return {
        "custom_id": f"{reviewer_id}:{example_id}",
        "response": {
            "body": {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(payload)}],
                    }
                ]
            }
        },
    }


def test_batch_request_is_strict_and_contains_only_review_evidence() -> None:
    value = _unreviewed()
    request = batch_request(
        value,
        role="a",
        reviewer_id=REVIEWER_A,
        model=MODEL_A,
    )
    body = request["body"]
    assert request["url"] == "/v1/responses"
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"]["additionalProperties"] is False
    supplied = json.loads(body["input"])
    assert supplied["example_id"] == value.identity.example_id
    assert "labels" not in supplied


def test_prepare_writes_two_independent_batches(tmp_path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(_unreviewed().model_dump_json() + "\n")
    batch_dir = tmp_path / "batches"
    batch_dir.mkdir()
    (batch_dir / "review-b.jsonl").write_text("obsolete model request\n")
    manifest = prepare_reviews(dataset, batch_dir)
    assert manifest["examples"] == 1
    assert manifest["requests"] == 2
    first = json.loads((tmp_path / "batches/review-a-000.jsonl").read_text())
    second = json.loads((tmp_path / "batches/review-b-000.jsonl").read_text())
    assert first["body"]["model"] != second["body"]["model"]
    assert first["custom_id"].startswith(f"{REVIEWER_A}:")
    assert second["custom_id"].startswith(f"{REVIEWER_B}:")
    assert not (batch_dir / "review-b.jsonl").exists()


def test_imported_llm_consensus_is_not_exported_as_expert_review(tmp_path) -> None:
    value = _unreviewed()
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(value.model_dump_json() + "\n")
    database = tmp_path / "reviews.sqlite3"
    for reviewer in (REVIEWER_A, REVIEWER_B):
        output = tmp_path / f"{reviewer}.jsonl"
        output.write_text(json.dumps(_batch_output(reviewer, value.identity.example_id)) + "\n")
        assert import_output(
            dataset, database, output, reviewer_id=reviewer
        ) == {"imported": 1, "failed": 0}

    reviewed_path = tmp_path / "reviewed.jsonl"
    export(dataset, database, reviewed_path)
    reviewed = AceDatasetExample.model_validate_json(reviewed_path.read_text())
    assert reviewed.labels.label_source == "llm_consensus"


def test_disagreements_prepare_adjudication_batch(tmp_path) -> None:
    value = _unreviewed()
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(value.model_dump_json() + "\n")
    database = tmp_path / "reviews.sqlite3"
    store = AnnotationStore(dataset, database)
    store.initialize()
    store.submit_review(
        value.identity.example_id,
        AnnotationReview(
            reviewer_id=REVIEWER_A,
            deviation="MATCH",
            semantic_label="ENTAILMENT",
            expected_treatment="APPROVE",
            confidence=0.9,
        ),
    )
    store.submit_review(
        value.identity.example_id,
        AnnotationReview(
            reviewer_id=REVIEWER_B,
            deviation="AMBIGUOUS",
            semantic_label="NEUTRAL",
            expected_treatment="STEP_UP",
            confidence=0.7,
        ),
    )
    output = tmp_path / "adjudication.jsonl"
    result = prepare_adjudications(dataset, database, output)
    request = json.loads(output.read_text())
    assert result["requests"] == 1
    assert len(json.loads(request["body"]["input"])["prior_reviews"]) == 2


def test_api_key_file_allows_comments_without_logging_or_committing(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    key_file = tmp_path / ".env.annotation"
    key_file.write_text("# local only\nOPENAI_API_KEY='test-secret'\n")
    assert _api_key(key_file) == "test-secret"
