from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.annotations import AnnotationDecision, AnnotationReview, AnnotationStore

from ml.data.schema import AceDatasetExample

REVIEWER_A = "llm-a-gpt-5.4-2026-03-05"
REVIEWER_B = "llm-b-gpt-5.5-2026-04-23"
ADJUDICATOR = "llm-adjudicator-gpt-5.5-2026-04-23"
MODEL_A = "gpt-5.4-2026-03-05"
MODEL_B = "gpt-5.5-2026-04-23"
ADJUDICATION_MODEL = "gpt-5.5-2026-04-23"

LABEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "deviation": {"type": "string", "enum": ["MATCH", "VIOLATION", "AMBIGUOUS"]},
        "semantic_label": {
            "type": "string",
            "enum": ["ENTAILMENT", "CONTRADICTION", "NEUTRAL"],
        },
        "expected_treatment": {
            "type": "string",
            "enum": ["APPROVE", "STEP_UP", "HOLD"],
        },
        "violation_types": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "semantic_mismatch",
                    "budget_breach",
                    "cumulative_budget_breach",
                    "missing_evidence",
                    "unrelated_item",
                    "prohibited_item",
                    "unauthorized_merchant",
                    "fulfillment_limit",
                    "currency_mismatch",
                    "other",
                ],
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "notes": {"type": "string", "maxLength": 500},
    },
    "required": [
        "deviation",
        "semantic_label",
        "expected_treatment",
        "violation_types",
        "confidence",
        "notes",
    ],
    "additionalProperties": False,
}

BASE_RUBRIC = """You are labeling a public/synthetic purchase-integrity example.
Judge only the supplied mandate, constraints, cart evidence, and state. Do not assume missing facts.

Return three separate judgments:
1. semantic_label: ENTAILMENT only when the evidence clearly satisfies the semantic requirement;
   CONTRADICTION when it clearly conflicts; NEUTRAL when it is insufficient, merely a substitute,
   or the relationship cannot be established.
2. deviation: MATCH when the complete cart satisfies the mandate; VIOLATION for a clear breach;
   AMBIGUOUS when evidence or intent is insufficient.
3. expected_treatment: HOLD only for an observable deterministic critical breach such as total or
   cumulative budget overspend, prohibited item/category, unauthorized merchant, currency mismatch,
   or fulfillment-limit breach. Semantic mismatch, uncertainty, and missing evidence alone are STEP_UP.
   APPROVE requires a clear match with no hard breach.

Use only the enumerated violation types. Keep notes factual and under 500 characters."""

REVIEWER_PROMPTS = {
    "a": BASE_RUBRIC
    + "\nWork evidence-first: identify what the source actually proves before comparing it to each constraint.",
    "b": BASE_RUBRIC
    + "\nWork constraint-first: test every stated constraint independently, then reconcile the overall result.",
    "adjudication": BASE_RUBRIC
    + "\nYou are the adjudicator. Resolve the two prior labels from the original evidence; do not vote or average.",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review_input(example: AceDatasetExample) -> dict[str, Any]:
    return {
        "example_id": example.identity.example_id,
        "context": example.context.model_dump(mode="json"),
        "mandate": example.mandate.model_dump(mode="json"),
        "cart": example.cart.model_dump(mode="json"),
        "state": example.state.model_dump(mode="json"),
        "provenance": {
            "evidence_origin": example.provenance.evidence_origin,
            "mandate_origin": example.provenance.mandate_origin,
            "transformation": example.provenance.transformation,
            "field_origins": example.provenance.field_origins,
        },
    }


def batch_request(
    example: AceDatasetExample,
    *,
    role: str,
    reviewer_id: str,
    model: str,
    prior_reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if role not in REVIEWER_PROMPTS:
        raise ValueError(f"unknown annotation role: {role}")
    payload = _review_input(example)
    if prior_reviews is not None:
        payload["prior_reviews"] = prior_reviews
    body: dict[str, Any] = {
        "model": model,
        "instructions": REVIEWER_PROMPTS[role],
        "input": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        "max_output_tokens": 500,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "ace_annotation_review",
                "strict": True,
                "schema": LABEL_SCHEMA,
            }
        },
    }
    if model.startswith("gpt-5"):
        body["reasoning"] = {"effort": "low"}
    return {
        "custom_id": f"{reviewer_id}:{example.identity.example_id}",
        "method": "POST",
        "url": "/v1/responses",
        "body": body,
    }


def _iter_unreviewed(dataset_path: Path, locale: str) -> list[AceDatasetExample]:
    output: list[AceDatasetExample] = []
    with dataset_path.open() as source:
        for line in source:
            if not line.strip():
                continue
            example = AceDatasetExample.model_validate_json(line)
            if example.labels.label_source == "unreviewed" and example.context.locale == locale:
                output.append(example)
    return output


def prepare_reviews(
    dataset_path: Path,
    output_dir: Path,
    locale: str = "en-US",
    chunk_size: int = 1_000,
) -> dict[str, Any]:
    examples = _iter_unreviewed(dataset_path, locale)
    if not examples:
        raise ValueError(f"no unreviewed {locale} examples found")
    if chunk_size < 1:
        raise ValueError("chunk size must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    specifications = (
        ("a", REVIEWER_A, MODEL_A),
        ("b", REVIEWER_B, MODEL_B),
    )
    files: dict[str, Any] = {}
    for role, reviewer_id, model in specifications:
        # Remove the legacy unsharded request format so stale model choices
        # cannot be submitted after regenerating the current shards.
        (output_dir / f"review-{role}.jsonl").unlink(missing_ok=True)
        shards: list[dict[str, Any]] = []
        for shard_index, offset in enumerate(range(0, len(examples), chunk_size)):
            path = output_dir / f"review-{role}-{shard_index:03d}.jsonl"
            with path.open("w") as output:
                for example in examples[offset : offset + chunk_size]:
                    output.write(
                        json.dumps(
                            batch_request(
                                example,
                                role=role,
                                reviewer_id=reviewer_id,
                                model=model,
                            ),
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            shards.append(
                {
                    "path": str(path),
                    "requests": min(chunk_size, len(examples) - offset),
                    "sha256": _sha256(path),
                }
            )
        files[role] = {
            "model": model,
            "reviewer_id": reviewer_id,
            "shards": shards,
        }
    manifest = {
        "dataset": str(dataset_path),
        "dataset_sha256": _sha256(dataset_path),
        "locale": locale,
        "examples": len(examples),
        "requests": len(examples) * 2,
        "chunk_size": chunk_size,
        "prompt_sha256": {
            key: hashlib.sha256(value.encode()).hexdigest()
            for key, value in REVIEWER_PROMPTS.items()
        },
        "files": files,
        "notice": "LLM labels are provisional and are not expert human ground truth.",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def _signature(value: dict[str, Any]) -> tuple[Any, ...]:
    return (
        value["deviation"],
        value["semantic_label"],
        value["expected_treatment"],
        tuple(sorted(value.get("violation_types", []))),
    )


def disagreement_rows(
    dataset_path: Path, database_path: Path
) -> list[tuple[AceDatasetExample, list[dict[str, Any]]]]:
    examples = {
        value.identity.example_id: value
        for value in _iter_unreviewed(dataset_path, "en-US")
    }
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """SELECT r.example_id, r.payload_json
           FROM annotation_reviews r
           LEFT JOIN annotation_adjudications a ON a.example_id=r.example_id
           WHERE a.example_id IS NULL
           ORDER BY r.example_id, r.reviewer_id"""
    ).fetchall()
    connection.close()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["example_id"], []).append(json.loads(row["payload_json"]))
    return [
        (examples[example_id], reviews)
        for example_id, reviews in sorted(grouped.items())
        if example_id in examples
        and len(reviews) >= 2
        and len({_signature(value) for value in reviews}) > 1
    ]


def prepare_adjudications(
    dataset_path: Path, database_path: Path, output_path: Path
) -> dict[str, Any]:
    candidates = disagreement_rows(dataset_path, database_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as output:
        for example, reviews in candidates:
            output.write(
                json.dumps(
                    batch_request(
                        example,
                        role="adjudication",
                        reviewer_id=ADJUDICATOR,
                        model=ADJUDICATION_MODEL,
                        prior_reviews=reviews,
                    ),
                    ensure_ascii=False,
                )
                + "\n"
            )
    return {
        "path": str(output_path),
        "requests": len(candidates),
        "model": ADJUDICATION_MODEL,
        "reviewer_id": ADJUDICATOR,
        "sha256": _sha256(output_path),
    }


def _response_text(row: dict[str, Any]) -> str:
    if row.get("error"):
        raise ValueError(f"batch request failed: {row['error']}")
    body = row.get("response", {}).get("body", {})
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return str(content["text"])
    raise ValueError("batch response does not contain output_text")


def import_output(
    dataset_path: Path,
    database_path: Path,
    output_path: Path,
    *,
    reviewer_id: str,
    adjudication: bool = False,
) -> dict[str, int]:
    store = AnnotationStore(dataset_path, database_path)
    store.initialize()
    counts = {"imported": 0, "failed": 0}
    with output_path.open() as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                prefix = f"{reviewer_id}:"
                if not str(row.get("custom_id", "")).startswith(prefix):
                    raise ValueError("custom_id does not match reviewer")
                example_id = str(row["custom_id"])[len(prefix) :]
                payload = json.loads(_response_text(row))
                if adjudication:
                    store.adjudicate(
                        example_id,
                        AnnotationDecision(
                            **payload,
                            reviewer_id=reviewer_id,
                            adjudicator_id=reviewer_id,
                        ),
                    )
                else:
                    store.submit_review(
                        example_id,
                        AnnotationReview(**payload, reviewer_id=reviewer_id),
                    )
                counts["imported"] += 1
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                counts["failed"] += 1
                print(f"line {line_number}: {exc}")
    return counts


def _api_key(key_file: Path | None) -> str:
    value = os.getenv("OPENAI_API_KEY", "").strip()
    if value:
        return value
    if key_file is not None and key_file.exists():
        lines = [
            line.strip()
            for line in key_file.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if len(lines) != 1:
            raise ValueError("key file must contain exactly one OPENAI_API_KEY entry")
        text = lines[0]
        if "=" in text:
            key, text = text.split("=", 1)
            if key.strip() != "OPENAI_API_KEY":
                raise ValueError("key file must contain OPENAI_API_KEY=<value>")
        value = text.strip().strip("\"'")
    if not value:
        raise RuntimeError(
            "set OPENAI_API_KEY or create the gitignored .env.annotation key file"
        )
    return value


def _client(key_file: Path | None):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("install services/api[annotation] before submitting batches") from exc
    return OpenAI(api_key=_api_key(key_file))


def submit_batch(input_path: Path, state_path: Path, key_file: Path | None) -> dict[str, Any]:
    client = _client(key_file)
    with input_path.open("rb") as source:
        uploaded = client.files.create(file=source, purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint="/v1/responses",
        completion_window="24h",
        metadata={"workflow": "ace-annotation", "input_sha256": _sha256(input_path)},
    )
    state = {
        "batch_id": batch.id,
        "input_file_id": uploaded.id,
        "input_path": str(input_path),
        "input_sha256": _sha256(input_path),
        "status": batch.status,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return state


def submit_shards(
    input_dir: Path,
    state_dir: Path,
    role: str,
    key_file: Path | None,
) -> dict[str, Any]:
    paths = sorted(input_dir.glob(f"review-{role}-[0-9][0-9][0-9].jsonl"))
    if not paths:
        raise FileNotFoundError(f"no review-{role} shards found in {input_dir}")
    states: list[dict[str, Any]] = []
    for path in paths:
        state_path = state_dir / f"{path.stem}.state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state.get("input_sha256") != _sha256(path):
                raise ValueError(f"existing state does not match shard: {path}")
        else:
            state = submit_batch(path, state_path, key_file)
        states.append(state)
    return {"role": role, "submitted": len(states), "states": states}


def batch_status(state_path: Path, key_file: Path | None) -> dict[str, Any]:
    state = json.loads(state_path.read_text())
    batch = _client(key_file).batches.retrieve(state["batch_id"])
    status = batch.model_dump(mode="json")
    state["status"] = status["status"]
    state["request_counts"] = status.get("request_counts")
    state["output_file_id"] = status.get("output_file_id")
    state["error_file_id"] = status.get("error_file_id")
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return state


def download_batch_output(
    state_path: Path, output_path: Path, key_file: Path | None
) -> dict[str, Any]:
    state = batch_status(state_path, key_file)
    if state["status"] != "completed" or not state.get("output_file_id"):
        raise RuntimeError(f"batch is not complete: {state['status']}")
    response = _client(key_file).files.content(state["output_file_id"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    response.write_to_file(output_path)
    return {"path": str(output_path), "sha256": _sha256(output_path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--dataset", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--locale", default="en-US")
    prepare.add_argument("--chunk-size", type=int, default=1_000)

    adjudicate = subparsers.add_parser("prepare-adjudication")
    adjudicate.add_argument("--dataset", type=Path, required=True)
    adjudicate.add_argument("--reviews", type=Path, required=True)
    adjudicate.add_argument("--output", type=Path, required=True)

    submit = subparsers.add_parser("submit")
    submit.add_argument("--input", type=Path, required=True)
    submit.add_argument("--state", type=Path, required=True)
    submit.add_argument("--key-file", type=Path)

    submit_many = subparsers.add_parser("submit-shards")
    submit_many.add_argument("--input", type=Path, required=True)
    submit_many.add_argument("--states", type=Path, required=True)
    submit_many.add_argument("--role", choices=["a", "b"], required=True)
    submit_many.add_argument("--key-file", type=Path)

    status = subparsers.add_parser("status")
    status.add_argument("--state", type=Path, required=True)
    status.add_argument("--key-file", type=Path)

    download = subparsers.add_parser("download")
    download.add_argument("--state", type=Path, required=True)
    download.add_argument("--output", type=Path, required=True)
    download.add_argument("--key-file", type=Path)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--dataset", type=Path, required=True)
    import_parser.add_argument("--reviews", type=Path, required=True)
    import_parser.add_argument("--output", type=Path, required=True)
    import_parser.add_argument("--reviewer-id", required=True)
    import_parser.add_argument("--adjudication", action="store_true")

    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_reviews(args.dataset, args.output, args.locale, args.chunk_size)
    elif args.command == "prepare-adjudication":
        result = prepare_adjudications(args.dataset, args.reviews, args.output)
    elif args.command == "submit":
        result = submit_batch(args.input, args.state, args.key_file)
    elif args.command == "submit-shards":
        result = submit_shards(args.input, args.states, args.role, args.key_file)
    elif args.command == "status":
        result = batch_status(args.state, args.key_file)
    elif args.command == "download":
        result = download_batch_output(args.state, args.output, args.key_file)
    else:
        result = import_output(
            args.dataset,
            args.reviews,
            args.output,
            reviewer_id=args.reviewer_id,
            adjudication=args.adjudication,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
