from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.annotations import AnnotationReview, AnnotationStore

from ml.data import llm_annotations
from ml.data.export_annotations import export
from ml.data.llm_annotations import (
    ADJUDICATOR,
    MODEL_A,
    REVIEWER_A,
    REVIEWER_B,
    _api_key,
    batch_request,
    import_adjudication_output,
    import_output,
    import_output_directory,
    merge_adjudication_retry,
    merge_output_directory_retry,
    prepare_adjudication_retry,
    prepare_adjudications,
    prepare_output_directory_retry,
    prepare_reviews,
    validate_adjudication_output,
    validate_output_directory,
    validate_output_shard,
    validate_prepared_adjudications,
    validate_prepared_reviews,
    validate_submission_states,
)
from ml.data.schema import AceDatasetExample, DatasetLabels, DatasetSplit, Identity
from tests.data.test_schema_v2 import example


def _unreviewed(index: int = 0, split: str = "train") -> AceDatasetExample:
    return example().model_copy(
        update={
            "identity": Identity(example_id=f"review-{index}", group_id=f"group-{index}"),
            "labels": DatasetLabels(label_source="unreviewed"),
            "split": DatasetSplit(name=split, grouping_keys=["identity.group_id"]),
        }
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
    assert validate_prepared_reviews(batch_dir)["requests"] == 2


def test_blind_review_omits_transformation_and_field_origins(tmp_path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(_unreviewed().model_dump_json() + "\n")
    batch_dir = tmp_path / "batches"

    manifest = prepare_reviews(
        dataset,
        batch_dir,
        blind_provenance=True,
    )

    request = json.loads((batch_dir / "review-a-000.jsonl").read_text())
    supplied = json.loads(request["body"]["input"])
    assert manifest["blind_provenance"] is True
    assert set(supplied["provenance"]) == {"evidence_origin", "mandate_origin"}
    assert validate_prepared_reviews(batch_dir)["requests"] == 2


def test_policy_v3_review_includes_checksum_bound_audit_context(tmp_path) -> None:
    value = _unreviewed()
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(value.model_dump_json() + "\n")
    context = tmp_path / "context.jsonl"
    audit_context = {
        "policy_version": "policy-treatment-contract-v3",
        "deterministic_treatment": "APPROVE",
        "commercial_rule_results": [],
    }
    context.write_text(
        json.dumps(
            {"example_id": value.identity.example_id, "audit_context": audit_context}
        )
        + "\n"
    )
    batch_dir = tmp_path / "batches"

    manifest = prepare_reviews(
        dataset,
        batch_dir,
        supplemental_context_path=context,
        prompt_profile="policy-v3",
    )

    request = json.loads((batch_dir / "review-a-000.jsonl").read_text())
    supplied = json.loads(request["body"]["input"])
    assert manifest["prompt_profile"] == "policy-v3"
    assert supplied["audit_context"] == audit_context
    assert validate_prepared_reviews(batch_dir)["requests"] == 2


def test_batch_status_preserves_timing_and_progress_diagnostics(
    tmp_path, monkeypatch
) -> None:
    state_path = tmp_path / "review-a-000.state.json"
    state_path.write_text(
        json.dumps(
            {
                "batch_id": "batch-test",
                "input_file_id": "file-input",
                "input_path": "review-a-000.jsonl",
                "input_sha256": "abc",
                "status": "in_progress",
                "request_counts": {"completed": 0, "failed": 0, "total": 1},
                "output_file_id": None,
                "error_file_id": None,
                "usage": None,
            }
        )
    )
    remote = {
        "status": "in_progress",
        "completion_window": "24h",
        "created_at": 100,
        "in_progress_at": 110,
        "expires_at": 86_500,
        "finalizing_at": None,
        "completed_at": None,
        "failed_at": None,
        "expired_at": None,
        "cancelling_at": None,
        "cancelled_at": None,
        "request_counts": {"completed": 0, "failed": 0, "total": 1},
        "output_file_id": None,
        "error_file_id": None,
        "usage": None,
        "errors": None,
    }
    batch = SimpleNamespace(model_dump=lambda mode: remote)
    client = SimpleNamespace(
        batches=SimpleNamespace(retrieve=lambda batch_id: batch)
    )
    monkeypatch.setattr(llm_annotations, "_client", lambda key_file: client)

    state = llm_annotations.batch_status(state_path, None)

    assert state["completion_window"] == "24h"
    assert state["created_at"] == 100
    assert state["in_progress_at"] == 110
    assert state["expires_at"] == 86_500
    assert state["last_progress_at"] == 110
    assert state["progress_changed_on_last_check"] is False
    assert state["last_checked_at"] >= state["last_progress_at"]
    assert json.loads(state_path.read_text()) == state


def test_reduced_queue_keeps_train_and_golden_then_balances_other_splits(
    tmp_path,
) -> None:
    dataset = tmp_path / "dataset.jsonl"
    values = [
        *[_unreviewed(index, "train") for index in range(2)],
        *[_unreviewed(10 + index, "golden") for index in range(2)],
        *[_unreviewed(20 + index, "validation") for index in range(2)],
        *[_unreviewed(30 + index, "calibration") for index in range(2)],
    ]
    values[0].cart.line_items[0].evidence_text = "Public title with a Unicode separator\u2028inside it"
    dataset.write_text("".join(value.model_dump_json() + "\n" for value in values))
    batch_dir = tmp_path / "batches"
    batch_dir.mkdir()
    (batch_dir / "review-a-002.jsonl").write_text("stale request\n")

    manifest = prepare_reviews(
        dataset,
        batch_dir,
        chunk_size=5,
        max_examples=6,
        seed=2026,
    )

    assert manifest["eligible_examples"] == 8
    assert manifest["examples"] == 6
    assert manifest["selection"]["selected_splits"] == {
        "calibration": 1,
        "golden": 2,
        "train": 2,
        "validation": 1,
    }
    assert not (batch_dir / "review-a-002.jsonl").exists()
    assert validate_prepared_reviews(batch_dir) == {
        "dataset_sha256": manifest["dataset_sha256"],
        "examples": 6,
        "requests": 12,
        "selected_splits": manifest["selection"]["selected_splits"],
        "roles": {
            "a": {"model": manifest["files"]["a"]["model"], "requests": 6, "shards": 2},
            "b": {"model": manifest["files"]["b"]["model"], "requests": 6, "shards": 2},
        },
    }


def test_submission_states_bind_every_prepared_shard(tmp_path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(_unreviewed().model_dump_json() + "\n")
    batch_dir = tmp_path / "batches"
    manifest = prepare_reviews(dataset, batch_dir)
    state_dir = batch_dir / "states"
    state_dir.mkdir()
    for role in ("a", "b"):
        shard = manifest["files"][role]["shards"][0]
        input_path = shard["path"]
        (state_dir / f"{Path(input_path).stem}.state.json").write_text(
            json.dumps(
                {
                    "batch_id": f"batch-{role}",
                    "input_file_id": f"file-{role}",
                    "input_path": input_path,
                    "input_sha256": shard["sha256"],
                    "status": "validating",
                }
            )
        )

    assert validate_submission_states(batch_dir, state_dir) == {
        "states": 2,
        "roles": {"a": 1, "b": 1},
        "statuses": {"validating": 2},
        "unique_batch_ids": 2,
        "unique_input_file_ids": 2,
    }


def test_imported_llm_consensus_is_not_exported_as_expert_review(tmp_path) -> None:
    value = _unreviewed()
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(value.model_dump_json() + "\n")
    database = tmp_path / "reviews.sqlite3"
    reviewer_outputs = {}
    for reviewer in (REVIEWER_A, REVIEWER_B):
        output = tmp_path / f"{reviewer}.jsonl"
        output.write_text(json.dumps(_batch_output(reviewer, value.identity.example_id)) + "\n")
        reviewer_outputs[reviewer] = output
        assert import_output(
            dataset, database, output, reviewer_id=reviewer
        ) == {"imported": 1, "failed": 0}
    assert import_output(
        dataset,
        database,
        reviewer_outputs[REVIEWER_A],
        reviewer_id=REVIEWER_A,
    ) == {"imported": 1, "failed": 0}

    reviewed_path = tmp_path / "reviewed.jsonl"
    export(dataset, database, reviewed_path)
    reviewed = AceDatasetExample.model_validate_json(reviewed_path.read_text())
    assert reviewed.labels.label_source == "llm_consensus"


def test_downloaded_outputs_exactly_cover_prepared_shards(tmp_path) -> None:
    value = _unreviewed()
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(value.model_dump_json() + "\n")
    batch_dir = tmp_path / "batches"
    manifest = prepare_reviews(dataset, batch_dir)
    output_dir = batch_dir / "outputs"
    output_dir.mkdir()
    for role, reviewer in (("a", REVIEWER_A), ("b", REVIEWER_B)):
        input_path = Path(manifest["files"][role]["shards"][0]["path"])
        output_path = output_dir / f"{input_path.stem}.output.jsonl"
        batch_output = _batch_output(reviewer, value.identity.example_id)
        if role == "b":
            batch_output["response"]["body"]["output"].insert(
                0,
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": ""}],
                },
            )
        output_path.write_text(json.dumps(batch_output) + "\n")
        assert validate_output_shard(
            input_path, output_path, reviewer_id=reviewer
        )["requests"] == 1

    output_manifest = validate_output_directory(batch_dir, output_dir)
    assert output_manifest["requests"] == 2
    assert json.loads((output_dir / "manifest.json").read_text()) == output_manifest
    imported = import_output_directory(
        dataset,
        batch_dir / "reviews.sqlite3",
        batch_dir,
        output_dir,
    )
    assert imported["review_rows"] == 2
    assert imported["reviewed_examples"] == 1
    assert imported["progress"]["agreed"] == 1

    broken_output = output_dir / "review-a-000.output.jsonl"
    broken_output.write_text("")
    with pytest.raises(ValueError, match="exactly cover"):
        validate_output_shard(
            batch_dir / "review-a-000.jsonl",
            broken_output,
            reviewer_id=REVIEWER_A,
        )


def test_review_retry_replaces_only_incomplete_rows_across_shards(tmp_path) -> None:
    values = [_unreviewed(0), _unreviewed(1)]
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("".join(value.model_dump_json() + "\n" for value in values))
    batch_dir = tmp_path / "batches"
    manifest = prepare_reviews(dataset, batch_dir, chunk_size=1)
    output_dir = batch_dir / "outputs"
    output_dir.mkdir()

    retry_ids: list[str] = []
    for role, reviewer in (("a", REVIEWER_A), ("b", REVIEWER_B)):
        for shard in manifest["files"][role]["shards"]:
            input_path = Path(shard["path"])
            request = json.loads(input_path.read_text())
            custom_id = str(request["custom_id"])
            example_id = custom_id.split(":", 1)[1]
            output = _batch_output(reviewer, example_id)
            if role == "a":
                retry_ids.append(custom_id)
                output["response"]["body"]["status"] = "incomplete"
                output["response"]["body"]["incomplete_details"] = {
                    "reason": "max_output_tokens"
                }
                output["response"]["body"]["output"][0]["content"][0]["text"] = (
                    '{"deviation":"MATCH"'
                )
            output_path = output_dir / f"{input_path.stem}.output.jsonl"
            output_path.write_text(json.dumps(output) + "\n")

    retry_input = batch_dir / "review-a.retry-01.jsonl"
    prepared_retry = prepare_output_directory_retry(
        batch_dir,
        output_dir,
        retry_input,
        role="a",
    )
    assert prepared_retry["requests"] == 2
    assert prepared_retry["reasons"] == {"max_output_tokens": 2}
    retry_requests = [json.loads(line) for line in retry_input.read_text().splitlines()]
    assert [row["custom_id"] for row in retry_requests] == sorted(retry_ids)
    assert {row["body"]["max_output_tokens"] for row in retry_requests} == {1_000}

    retry_output = batch_dir / "review-a.retry-01.output.jsonl"
    retry_output.write_text(
        "".join(
            json.dumps(_batch_output(REVIEWER_A, custom_id.split(":", 1)[1])) + "\n"
            for custom_id in sorted(retry_ids)
        )
    )
    merged_dir = batch_dir / "validated-outputs"
    merged = merge_output_directory_retry(
        batch_dir,
        output_dir,
        retry_input,
        retry_output,
        merged_dir,
    )
    assert merged["requests"] == 4
    assert merged["replaced_requests"] == 2
    assert validate_output_directory(batch_dir, merged_dir)["requests"] == 4
    original = json.loads((output_dir / "review-a-000.output.jsonl").read_text())
    assert original["response"]["body"]["status"] == "incomplete"


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
    manifest_path = output.with_suffix(".manifest.json")
    assert result["requests"] == 1
    assert result["model"] == "gpt-5.4-2026-03-05"
    assert result["splits"] == {"train": 1}
    assert json.loads(manifest_path.read_text()) == result
    assert len(json.loads(request["body"]["input"])["prior_reviews"]) == 2
    assert validate_prepared_adjudications(
        dataset, database, output, manifest_path
    ) == {
        "requests": 1,
        "model": "gpt-5.4-2026-03-05",
        "reviewer_id": "llm-adjudicator-gpt-5.4-2026-03-05",
        "input_sha256": result["sha256"],
        "dataset_sha256": result["dataset_sha256"],
        "review_database_sha256": result["review_database_sha256"],
        "splits": {"train": 1},
    }

    request["body"]["model"] = "gpt-5.4"
    output.write_text(json.dumps(request) + "\n")
    result["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="request model mismatch"):
        validate_prepared_adjudications(dataset, database, output, manifest_path)


def test_adjudication_output_is_validated_imported_idempotently_and_exported(
    tmp_path,
) -> None:
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
            deviation="VIOLATION",
            semantic_label="CONTRADICTION",
            expected_treatment="STEP_UP",
            violation_types=["semantic_mismatch"],
            confidence=0.8,
        ),
    )
    input_path = tmp_path / "adjudication.jsonl"
    prepared = prepare_adjudications(dataset, database, input_path)
    output_path = tmp_path / "adjudication.output.jsonl"
    output_path.write_text(
        json.dumps(_batch_output(ADJUDICATOR, value.identity.example_id)) + "\n"
    )
    state_path = tmp_path / "adjudication.state.json"
    state_path.write_text(
        json.dumps(
            {
                "batch_id": "batch-adjudication",
                "input_file_id": "file-input",
                "input_path": str(input_path),
                "input_sha256": prepared["sha256"],
                "status": "completed",
                "request_counts": {"completed": 1, "failed": 0, "total": 1},
                "output_file_id": "file-output",
                "error_file_id": None,
                "download_path": str(output_path),
                "download_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            }
        )
    )

    validated = validate_adjudication_output(input_path, output_path, state_path)
    assert validated["requests"] == 1
    first = import_adjudication_output(dataset, database, input_path, output_path)
    assert first["failed"] == 0
    assert first["adjudications"] == 1
    assert first["progress"] == {
        "total": 1,
        "unreviewed": 0,
        "single_review": 0,
        "agreed": 0,
        "needs_adjudication": 0,
        "adjudicated": 1,
    }
    second = import_adjudication_output(dataset, database, input_path, output_path)
    assert second["database_sha256"] == first["database_sha256"]

    reviewed_path = tmp_path / "reviewed.jsonl"
    manifest = export(dataset, database, reviewed_path)
    reviewed = AceDatasetExample.model_validate_json(reviewed_path.read_text())
    assert manifest["row_count"] == 1
    assert manifest["dataset_sha256"] == manifest["output_sha256"]
    assert manifest["label_sources"] == {"llm_adjudicated": 1}
    assert reviewed.labels.label_source == "llm_adjudicated"

    incomplete_path = tmp_path / "adjudication.incomplete.jsonl"
    incomplete = _batch_output(ADJUDICATOR, value.identity.example_id)
    incomplete["response"]["body"]["status"] = "incomplete"
    incomplete["response"]["body"]["incomplete_details"] = {
        "reason": "max_output_tokens"
    }
    incomplete["response"]["body"]["output"][0]["content"][0]["text"] = (
        '{"deviation":"MATCH"'
    )
    incomplete_path.write_text(json.dumps(incomplete) + "\n")
    retry_input = tmp_path / "adjudication.retry-01.jsonl"
    retry = prepare_adjudication_retry(input_path, incomplete_path, retry_input)
    assert retry["requests"] == 1
    assert retry["reasons"] == {"max_output_tokens": 1}
    assert json.loads(retry_input.read_text())["body"]["max_output_tokens"] == 1_000
    merged_path = tmp_path / "adjudication.validated.jsonl"
    merged = merge_adjudication_retry(
        input_path,
        incomplete_path,
        retry_input,
        output_path,
        merged_path,
    )
    assert merged["requests"] == 1
    assert merged["replaced_requests"] == 1


def test_api_key_file_allows_comments_without_logging_or_committing(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    key_file = tmp_path / ".env.annotation"
    key_file.write_text("# local only\nOPENAI_API_KEY='test-secret'\n")
    assert _api_key(key_file) == "test-secret"
