from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any

from app.annotations import AnnotationDecision, AnnotationReview, AnnotationStore

from ml.data.schema import AceDatasetExample

REVIEWER_A = "llm-a-gpt-5.4-mini-2026-03-17"
REVIEWER_B = "llm-b-gpt-4.1-mini-2025-04-14"
ADJUDICATOR = "llm-adjudicator-gpt-5.4-2026-03-05"
MODEL_A = "gpt-5.4-mini-2026-03-17"
MODEL_B = "gpt-4.1-mini-2025-04-14"
ADJUDICATION_MODEL = "gpt-5.4-2026-03-05"
DEFAULT_REVIEW_SEED = 2026

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

POLICY_V3_RUBRIC = """You are independently auditing a purchase-integrity example under policy-treatment-contract-v3.
Judge only the supplied mandate, constraints, cart evidence, state, and audit_context. Do not assume
missing facts. The audit_context deterministic rule results are authoritative; do not recompute them.

Return three separate judgments:
1. semantic_label: ENTAILMENT only when the evidence clearly satisfies the semantic requirement;
   CONTRADICTION when it clearly conflicts; NEUTRAL when it is insufficient, merely a substitute,
   unrelated, or cannot be established.
2. deviation: MATCH when the complete cart satisfies the mandate; VIOLATION for a clear breach;
   AMBIGUOUS when evidence or intent is insufficient.
3. expected_treatment: exactly follow the supplied deterministic treatment when it is STEP_UP or HOLD.
   When it is APPROVE, semantic contradiction, unrelatedness, or missing evidence changes the result to
   STEP_UP. HOLD is permitted only for a supplied critical deterministic result (cumulative budget,
   fulfillment limit, explicit prohibition, or unauthorized merchant). Single-cart overspend, currency
   mismatch, semantic issues, and missing evidence are STEP_UP. Semantic judgment never creates HOLD.

Use the closest enumerated violation types. Keep notes factual and under 500 characters."""

POLICY_V3_PROMPTS = {
    "a": POLICY_V3_RUBRIC
    + "\nWork evidence-first: identify what the source proves before comparing it to each constraint.",
    "b": POLICY_V3_RUBRIC
    + "\nWork constraint-first: test every stated constraint independently, then reconcile the result.",
    "adjudication": POLICY_V3_RUBRIC
    + "\nResolve the two prior labels from the original evidence and policy; do not vote or average.",
}

PROMPT_PROFILES = {"legacy": REVIEWER_PROMPTS, "policy-v3": POLICY_V3_PROMPTS}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    # File iteration follows JSONL's physical LF/CRLF records. str.splitlines()
    # also splits on valid in-string Unicode separators such as U+2028.
    with path.open() as source:
        return [json.loads(line) for line in source if line.strip()]


def _review_input(
    example: AceDatasetExample, *, blind_provenance: bool = False
) -> dict[str, Any]:
    provenance = {
        "evidence_origin": example.provenance.evidence_origin,
        "mandate_origin": example.provenance.mandate_origin,
    }
    if not blind_provenance:
        provenance.update(
            {
                "transformation": example.provenance.transformation,
                "field_origins": example.provenance.field_origins,
            }
        )
    return {
        "example_id": example.identity.example_id,
        "context": example.context.model_dump(mode="json"),
        "mandate": example.mandate.model_dump(mode="json"),
        "cart": example.cart.model_dump(mode="json"),
        "state": example.state.model_dump(mode="json"),
        "provenance": provenance,
    }


def batch_request(
    example: AceDatasetExample,
    *,
    role: str,
    reviewer_id: str,
    model: str,
    prior_reviews: list[dict[str, Any]] | None = None,
    blind_provenance: bool = False,
    supplemental_context: dict[str, Any] | None = None,
    prompt_profile: str = "legacy",
) -> dict[str, Any]:
    prompts = PROMPT_PROFILES.get(prompt_profile)
    if prompts is None:
        raise ValueError(f"unknown prompt profile: {prompt_profile}")
    if role not in prompts:
        raise ValueError(f"unknown annotation role: {role}")
    payload = _review_input(example, blind_provenance=blind_provenance)
    if supplemental_context is not None:
        payload["audit_context"] = supplemental_context
    if prior_reviews is not None:
        payload["prior_reviews"] = prior_reviews
    body: dict[str, Any] = {
        "model": model,
        "instructions": prompts[role],
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


def _review_hash(example: AceDatasetExample, seed: int) -> str:
    return hashlib.sha256(
        f"{seed}:{example.identity.example_id}".encode()
    ).hexdigest()


def select_review_queue(
    examples: list[AceDatasetExample],
    *,
    max_examples: int | None,
    seed: int = DEFAULT_REVIEW_SEED,
) -> tuple[list[AceDatasetExample], dict[str, Any]]:
    """Select a deterministic reduced queue without sacrificing train or golden rows."""
    if max_examples is not None and max_examples < 1:
        raise ValueError("max examples must be positive")
    by_split: dict[str, list[AceDatasetExample]] = {}
    for example in examples:
        by_split.setdefault(example.split.name, []).append(example)
    for bucket in by_split.values():
        bucket.sort(key=lambda value: _review_hash(value, seed))

    target = len(examples) if max_examples is None else min(max_examples, len(examples))
    selected: list[AceDatasetExample] = []
    # Review every sampled training row and every golden row whenever the cap allows.
    # Remaining capacity is shared evenly across validation/calibration (and any
    # future non-priority splits) to avoid one held-out split consuming the queue.
    for split in ("train", "golden"):
        bucket = by_split.get(split, [])
        take = min(len(bucket), target - len(selected))
        selected.extend(bucket[:take])
        by_split[split] = bucket[take:]
        if len(selected) == target:
            break

    balanced_splits = sorted(
        split for split, bucket in by_split.items() if bucket and split not in {"train", "golden"}
    )
    positions = {split: 0 for split in balanced_splits}
    while len(selected) < target and balanced_splits:
        made_progress = False
        for split in balanced_splits:
            position = positions[split]
            bucket = by_split[split]
            if position >= len(bucket):
                continue
            selected.append(bucket[position])
            positions[split] += 1
            made_progress = True
            if len(selected) == target:
                break
        if not made_progress:
            break

    if len(selected) != target:
        raise ValueError(f"could select only {len(selected)} of {target} review examples")
    selected.sort(key=lambda value: value.identity.example_id)
    report = {
        "policy": "all_train_all_golden_then_balanced_other_splits",
        "seed": seed,
        "eligible_examples": len(examples),
        "eligible_splits": dict(sorted(Counter(value.split.name for value in examples).items())),
        "selected_examples": len(selected),
        "selected_splits": dict(sorted(Counter(value.split.name for value in selected).items())),
        "selected_example_ids_sha256": hashlib.sha256(
            "\n".join(value.identity.example_id for value in selected).encode()
        ).hexdigest(),
    }
    return selected, report


def prepare_reviews(
    dataset_path: Path,
    output_dir: Path,
    locale: str = "en-US",
    chunk_size: int = 1_000,
    max_examples: int | None = None,
    seed: int = DEFAULT_REVIEW_SEED,
    blind_provenance: bool = False,
    supplemental_context_path: Path | None = None,
    prompt_profile: str = "legacy",
) -> dict[str, Any]:
    eligible_examples = _iter_unreviewed(dataset_path, locale)
    if not eligible_examples:
        raise ValueError(f"no unreviewed {locale} examples found")
    if chunk_size < 1:
        raise ValueError("chunk size must be positive")
    examples, selection = select_review_queue(
        eligible_examples, max_examples=max_examples, seed=seed
    )
    prompts = PROMPT_PROFILES.get(prompt_profile)
    if prompts is None:
        raise ValueError(f"unknown prompt profile: {prompt_profile}")
    supplemental_contexts: dict[str, dict[str, Any]] = {}
    if supplemental_context_path is not None:
        rows = _read_jsonl(supplemental_context_path)
        supplemental_contexts = {
            str(row["example_id"]): dict(row["audit_context"]) for row in rows
        }
        if len(supplemental_contexts) != len(rows):
            raise ValueError("supplemental contexts contain duplicate example IDs")
        expected_ids = {example.identity.example_id for example in examples}
        if set(supplemental_contexts) != expected_ids:
            raise ValueError("supplemental contexts do not exactly cover selected examples")
    output_dir.mkdir(parents=True, exist_ok=True)
    queue_path = output_dir / "review-queue.jsonl"
    queue_path.write_text(
        "".join(
            json.dumps(
                {
                    "example_id": example.identity.example_id,
                    "group_id": example.identity.group_id,
                    "split": example.split.name,
                },
                sort_keys=True,
            )
            + "\n"
            for example in examples
        )
    )
    specifications = (
        ("a", REVIEWER_A, MODEL_A),
        ("b", REVIEWER_B, MODEL_B),
    )
    files: dict[str, Any] = {}
    for role, reviewer_id, model in specifications:
        # Remove every prior shard and the legacy unsharded request format so
        # stale model choices or a previous, larger queue cannot be submitted.
        for stale_path in output_dir.glob(f"review-{role}-[0-9][0-9][0-9].jsonl"):
            stale_path.unlink()
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
                                blind_provenance=blind_provenance,
                                supplemental_context=supplemental_contexts.get(
                                    example.identity.example_id
                                ),
                                prompt_profile=prompt_profile,
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
        "eligible_examples": len(eligible_examples),
        "requests": len(examples) * 2,
        "chunk_size": chunk_size,
        "blind_provenance": blind_provenance,
        "prompt_profile": prompt_profile,
        "supplemental_context": (
            {
                "path": str(supplemental_context_path),
                "sha256": _sha256(supplemental_context_path),
            }
            if supplemental_context_path is not None
            else None
        ),
        "selection": selection,
        "review_queue": {
            "path": str(queue_path),
            "sha256": _sha256(queue_path),
        },
        "prompt_sha256": {
            key: hashlib.sha256(value.encode()).hexdigest()
            for key, value in prompts.items()
        },
        "files": files,
        "notice": "LLM labels are provisional and are not expert human ground truth.",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def validate_prepared_reviews(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    dataset_path = Path(manifest["dataset"])
    if _sha256(dataset_path) != manifest["dataset_sha256"]:
        raise ValueError("annotation manifest dataset checksum mismatch")
    blind_provenance = bool(manifest.get("blind_provenance", False))
    prompt_profile = str(manifest.get("prompt_profile", "legacy"))
    prompts = PROMPT_PROFILES.get(prompt_profile)
    if prompts is None:
        raise ValueError("annotation manifest has an unknown prompt profile")
    expected_prompt_sha256 = {
        key: hashlib.sha256(value.encode()).hexdigest()
        for key, value in prompts.items()
    }
    if manifest.get("prompt_sha256") != expected_prompt_sha256:
        raise ValueError("annotation manifest prompt checksum mismatch")
    examples = {
        value.identity.example_id: value
        for value in _iter_unreviewed(dataset_path, manifest["locale"])
    }
    supplemental_contexts: dict[str, dict[str, Any]] = {}
    supplemental = manifest.get("supplemental_context")
    if supplemental is not None:
        supplemental_path = Path(supplemental["path"])
        if _sha256(supplemental_path) != supplemental["sha256"]:
            raise ValueError("supplemental context checksum mismatch")
        supplemental_rows = _read_jsonl(supplemental_path)
        supplemental_contexts = {
            str(row["example_id"]): dict(row["audit_context"])
            for row in supplemental_rows
        }

    queue = manifest["review_queue"]
    queue_path = Path(queue["path"])
    if _sha256(queue_path) != queue["sha256"]:
        raise ValueError("review queue checksum mismatch")
    queue_rows = _read_jsonl(queue_path)
    queue_ids = [str(row["example_id"]) for row in queue_rows]
    if len(queue_ids) != len(set(queue_ids)):
        raise ValueError("review queue contains duplicate example IDs")
    if len(queue_ids) != manifest["examples"]:
        raise ValueError("review queue count does not match manifest")
    split_counts = dict(sorted(Counter(str(row["split"]) for row in queue_rows).items()))
    if split_counts != manifest["selection"]["selected_splits"]:
        raise ValueError("review queue split counts do not match manifest")
    id_hash = hashlib.sha256("\n".join(queue_ids).encode()).hexdigest()
    if id_hash != manifest["selection"]["selected_example_ids_sha256"]:
        raise ValueError("review queue ID hash does not match manifest")

    role_results: dict[str, Any] = {}
    for role in ("a", "b"):
        specification = manifest["files"][role]
        reviewer_id = specification["reviewer_id"]
        model = specification["model"]
        request_ids: list[str] = []
        for shard in specification["shards"]:
            path = Path(shard["path"])
            if _sha256(path) != shard["sha256"]:
                raise ValueError(f"reviewer {role} shard checksum mismatch: {path}")
            rows = _read_jsonl(path)
            if len(rows) != shard["requests"]:
                raise ValueError(f"reviewer {role} shard count mismatch: {path}")
            for row in rows:
                prefix = f"{reviewer_id}:"
                if not str(row.get("custom_id", "")).startswith(prefix):
                    raise ValueError(f"reviewer {role} custom ID mismatch")
                if row.get("method") != "POST" or row.get("url") != "/v1/responses":
                    raise ValueError(f"reviewer {role} request endpoint mismatch")
                body = row["body"]
                if body.get("model") != model:
                    raise ValueError(f"reviewer {role} model mismatch")
                if body.get("instructions") != prompts[role]:
                    raise ValueError(f"reviewer {role} prompt mismatch")
                if body.get("text", {}).get("format", {}).get("strict") is not True:
                    raise ValueError(f"reviewer {role} schema is not strict")
                supplied = json.loads(body["input"])
                example_id = str(row["custom_id"])[len(prefix) :]
                expected_example = examples.get(example_id)
                expected_input = (
                    _review_input(
                        expected_example,
                        blind_provenance=blind_provenance,
                    )
                    if expected_example is not None
                    else None
                )
                if expected_input is not None and supplemental is not None:
                    expected_input["audit_context"] = supplemental_contexts.get(
                        example_id
                    )
                if supplied != expected_input or "labels" in supplied:
                    raise ValueError(f"reviewer {role} supplied evidence mismatch")
                request_ids.append(example_id)
        if request_ids != queue_ids:
            raise ValueError(f"reviewer {role} requests do not match the review queue")
        role_results[role] = {
            "model": model,
            "requests": len(request_ids),
            "shards": len(specification["shards"]),
        }
    return {
        "dataset_sha256": manifest["dataset_sha256"],
        "examples": len(queue_ids),
        "requests": sum(value["requests"] for value in role_results.values()),
        "selected_splits": split_counts,
        "roles": role_results,
    }


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
    dataset_path: Path,
    database_path: Path,
    output_path: Path,
    *,
    blind_provenance: bool = False,
    supplemental_context_path: Path | None = None,
    prompt_profile: str = "legacy",
) -> dict[str, Any]:
    candidates = disagreement_rows(dataset_path, database_path)
    prompts = PROMPT_PROFILES.get(prompt_profile)
    if prompts is None:
        raise ValueError(f"unknown prompt profile: {prompt_profile}")
    supplemental_contexts: dict[str, dict[str, Any]] = {}
    if supplemental_context_path is not None:
        supplemental_rows = _read_jsonl(supplemental_context_path)
        supplemental_contexts = {
            str(row["example_id"]): dict(row["audit_context"])
            for row in supplemental_rows
        }
        if len(supplemental_contexts) != len(supplemental_rows):
            raise ValueError("supplemental contexts contain duplicate example IDs")
        missing = {
            example.identity.example_id for example, _ in candidates
        } - set(supplemental_contexts)
        if missing:
            raise ValueError("supplemental contexts do not cover all disagreements")
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
                        blind_provenance=blind_provenance,
                        supplemental_context=supplemental_contexts.get(
                            example.identity.example_id
                        ),
                        prompt_profile=prompt_profile,
                    ),
                    ensure_ascii=False,
                )
                + "\n"
            )
    manifest = {
        "path": str(output_path),
        "requests": len(candidates),
        "model": ADJUDICATION_MODEL,
        "reviewer_id": ADJUDICATOR,
        "sha256": _sha256(output_path),
        "dataset": str(dataset_path),
        "dataset_sha256": _sha256(dataset_path),
        "review_database": str(database_path),
        "review_database_sha256": _sha256(database_path),
        "prompt_profile": prompt_profile,
        "prompt_sha256": hashlib.sha256(prompts["adjudication"].encode()).hexdigest(),
        "supplemental_context": (
            {
                "path": str(supplemental_context_path),
                "sha256": _sha256(supplemental_context_path),
            }
            if supplemental_context_path is not None
            else None
        ),
        "blind_provenance": blind_provenance,
        "splits": dict(
            sorted(Counter(example.split.name for example, _ in candidates).items())
        ),
    }
    manifest_path = output_path.with_suffix(".manifest.json")
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def validate_prepared_adjudications(
    dataset_path: Path,
    database_path: Path,
    input_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    blind_provenance = bool(manifest.get("blind_provenance", False))
    prompt_profile = str(manifest.get("prompt_profile", "legacy"))
    prompts = PROMPT_PROFILES.get(prompt_profile)
    if prompts is None:
        raise ValueError("adjudication manifest has an unknown prompt profile")
    if manifest["dataset"] != str(dataset_path) or manifest["dataset_sha256"] != _sha256(
        dataset_path
    ):
        raise ValueError("adjudication manifest dataset binding mismatch")
    if manifest["review_database"] != str(database_path) or manifest[
        "review_database_sha256"
    ] != _sha256(database_path):
        raise ValueError("adjudication manifest review-database binding mismatch")
    if manifest["path"] != str(input_path) or manifest["sha256"] != _sha256(input_path):
        raise ValueError("adjudication manifest request-file binding mismatch")
    if manifest["model"] != ADJUDICATION_MODEL or manifest["reviewer_id"] != ADJUDICATOR:
        raise ValueError("adjudication manifest model identity mismatch")
    if manifest["prompt_sha256"] != hashlib.sha256(
        prompts["adjudication"].encode()
    ).hexdigest():
        raise ValueError("adjudication prompt checksum mismatch")
    supplemental_contexts: dict[str, dict[str, Any]] = {}
    supplemental = manifest.get("supplemental_context")
    if supplemental is not None:
        supplemental_path = Path(supplemental["path"])
        if _sha256(supplemental_path) != supplemental["sha256"]:
            raise ValueError("adjudication supplemental context checksum mismatch")
        supplemental_rows = _read_jsonl(supplemental_path)
        supplemental_contexts = {
            str(row["example_id"]): dict(row["audit_context"])
            for row in supplemental_rows
        }

    candidates = disagreement_rows(dataset_path, database_path)
    candidate_by_id = {
        example.identity.example_id: (example, reviews)
        for example, reviews in candidates
    }
    rows = _read_jsonl(input_path)
    seen_ids: set[str] = set()
    for row in rows:
        prefix = f"{ADJUDICATOR}:"
        custom_id = str(row.get("custom_id", ""))
        if not custom_id.startswith(prefix):
            raise ValueError("adjudication custom ID mismatch")
        example_id = custom_id[len(prefix) :]
        if example_id in seen_ids:
            raise ValueError("duplicate adjudication example ID")
        seen_ids.add(example_id)
        if example_id not in candidate_by_id:
            raise ValueError("adjudication request is not a current disagreement")
        if row.get("method") != "POST" or row.get("url") != "/v1/responses":
            raise ValueError("adjudication request endpoint mismatch")
        body = row["body"]
        if body.get("model") != ADJUDICATION_MODEL:
            raise ValueError("adjudication request model mismatch")
        if body.get("instructions") != prompts["adjudication"]:
            raise ValueError("adjudication request prompt mismatch")
        expected_format = {
            "type": "json_schema",
            "name": "ace_annotation_review",
            "strict": True,
            "schema": LABEL_SCHEMA,
        }
        if body.get("text", {}).get("format") != expected_format:
            raise ValueError("adjudication request schema mismatch")
        if body.get("max_output_tokens") != 500:
            raise ValueError("adjudication output-token limit mismatch")
        if body.get("reasoning") != {"effort": "low"}:
            raise ValueError("adjudication reasoning configuration mismatch")
        supplied = json.loads(body["input"])
        prior_reviews = supplied.get("prior_reviews", [])
        if len(prior_reviews) != 2 or len({_signature(value) for value in prior_reviews}) != 2:
            raise ValueError("adjudication request lacks two disagreeing prior reviews")
        example, expected_reviews = candidate_by_id[example_id]
        if prior_reviews != expected_reviews:
            raise ValueError("adjudication prior reviews do not match the review database")
        expected_payload = _review_input(
            example, blind_provenance=blind_provenance
        )
        if supplemental is not None:
            expected_payload["audit_context"] = supplemental_contexts.get(example_id)
        expected_payload["prior_reviews"] = expected_reviews
        if supplied != expected_payload:
            raise ValueError("adjudication evidence payload mismatch")
    if seen_ids != set(candidate_by_id) or len(rows) != manifest["requests"]:
        raise ValueError("adjudication requests do not exactly cover current disagreements")
    split_counts = dict(
        sorted(
            Counter(
                candidate_by_id[example_id][0].split.name for example_id in seen_ids
            ).items()
        )
    )
    if split_counts != manifest["splits"]:
        raise ValueError("adjudication split counts do not match manifest")
    return {
        "requests": len(rows),
        "model": ADJUDICATION_MODEL,
        "reviewer_id": ADJUDICATOR,
        "input_sha256": _sha256(input_path),
        "dataset_sha256": _sha256(dataset_path),
        "review_database_sha256": _sha256(database_path),
        "splits": split_counts,
    }


def _response_text(row: dict[str, Any]) -> str:
    if row.get("error"):
        raise ValueError(f"batch request failed: {row['error']}")
    body = row.get("response", {}).get("body", {})
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and str(content.get("text", "")).strip():
                return str(content["text"])
    raise ValueError("batch response does not contain output_text")


def _validate_output_row(row: dict[str, Any], reviewer_id: str) -> None:
    if row.get("error"):
        raise ValueError(f"batch request failed: {row['error']}")
    custom_id = str(row.get("custom_id", ""))
    if not custom_id.startswith(f"{reviewer_id}:"):
        raise ValueError("batch output custom ID does not match reviewer")
    response_status = row.get("response", {}).get("body", {}).get("status")
    if response_status not in {None, "completed"}:
        raise ValueError(f"batch response is not complete: {response_status}")
    payload = json.loads(_response_text(row))
    required_fields = set(LABEL_SCHEMA["required"])
    if set(payload) != required_fields:
        raise ValueError("batch output fields do not match the strict label schema")
    allowed_violation_types = set(
        LABEL_SCHEMA["properties"]["violation_types"]["items"]["enum"]
    )
    if not set(payload["violation_types"]).issubset(allowed_violation_types):
        raise ValueError("batch output contains an unknown violation type")
    if len(payload["notes"]) > 500:
        raise ValueError("batch output notes exceed the strict schema limit")
    AnnotationReview(**payload, reviewer_id=reviewer_id)


def validate_output_shard(
    input_path: Path,
    output_path: Path,
    *,
    reviewer_id: str,
) -> dict[str, Any]:
    input_rows = _read_jsonl(input_path)
    expected_ids = [str(row["custom_id"]) for row in input_rows]
    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("input shard contains duplicate custom IDs")
    output_rows = _read_jsonl(output_path)
    seen_ids: set[str] = set()
    for row in output_rows:
        custom_id = str(row.get("custom_id", ""))
        if custom_id in seen_ids:
            raise ValueError("batch output contains duplicate custom IDs")
        seen_ids.add(custom_id)
        _validate_output_row(row, reviewer_id)
    if seen_ids != set(expected_ids) or len(output_rows) != len(expected_ids):
        raise ValueError("batch output does not exactly cover the input shard")
    return {
        "input": str(input_path),
        "input_sha256": _sha256(input_path),
        "output": str(output_path),
        "output_sha256": _sha256(output_path),
        "reviewer_id": reviewer_id,
        "requests": len(output_rows),
    }


def prepare_output_retry(
    input_path: Path,
    output_path: Path,
    retry_path: Path,
    *,
    reviewer_id: str,
    max_output_tokens: int = 1_000,
) -> dict[str, Any]:
    if max_output_tokens <= 500:
        raise ValueError("retry output-token limit must exceed the original limit")
    input_rows = _read_jsonl(input_path)
    output_rows = _read_jsonl(output_path)
    inputs = {str(row["custom_id"]): row for row in input_rows}
    outputs = {str(row["custom_id"]): row for row in output_rows}
    if len(inputs) != len(input_rows) or len(outputs) != len(output_rows):
        raise ValueError("batch files contain duplicate custom IDs")
    if set(inputs) != set(outputs):
        raise ValueError("batch output does not cover the prepared input")
    retry_ids: list[str] = []
    reasons: Counter[str] = Counter()
    for custom_id, row in outputs.items():
        try:
            _validate_output_row(row, reviewer_id)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            retry_ids.append(custom_id)
            body = row.get("response", {}).get("body", {})
            detail = body.get("incomplete_details") or {}
            reason = str(detail.get("reason") or type(exc).__name__)
            reasons[reason] += 1
    if not retry_ids:
        raise ValueError("batch output has no invalid rows to retry")
    retry_ids.sort()
    retry_path.parent.mkdir(parents=True, exist_ok=True)
    with retry_path.open("w") as destination:
        for custom_id in retry_ids:
            request = copy.deepcopy(inputs[custom_id])
            request["body"]["max_output_tokens"] = max_output_tokens
            destination.write(json.dumps(request, ensure_ascii=False) + "\n")
    manifest = {
        "path": str(retry_path),
        "requests": len(retry_ids),
        "model": inputs[retry_ids[0]]["body"]["model"],
        "reviewer_id": reviewer_id,
        "max_output_tokens": max_output_tokens,
        "sha256": _sha256(retry_path),
        "source_input": str(input_path),
        "source_input_sha256": _sha256(input_path),
        "source_output": str(output_path),
        "source_output_sha256": _sha256(output_path),
        "retry_custom_ids": retry_ids,
        "reasons": dict(sorted(reasons.items())),
    }
    manifest_path = retry_path.with_suffix(".manifest.json")
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def prepare_adjudication_retry(
    input_path: Path,
    output_path: Path,
    retry_path: Path,
    *,
    max_output_tokens: int = 1_000,
) -> dict[str, Any]:
    return prepare_output_retry(
        input_path,
        output_path,
        retry_path,
        reviewer_id=ADJUDICATOR,
        max_output_tokens=max_output_tokens,
    )


def prepare_output_directory_retry(
    input_dir: Path,
    output_dir: Path,
    retry_path: Path,
    *,
    role: str,
    max_output_tokens: int = 1_000,
) -> dict[str, Any]:
    if max_output_tokens <= 500:
        raise ValueError("retry output-token limit must exceed the original limit")
    prepared_path = input_dir / "manifest.json"
    prepared = json.loads(prepared_path.read_text())
    if role not in prepared["files"]:
        raise ValueError("unknown reviewer role")
    role_manifest = prepared["files"][role]
    reviewer_id = str(role_manifest["reviewer_id"])
    inputs: dict[str, dict[str, Any]] = {}
    invalid: dict[str, dict[str, Any]] = {}
    reasons: Counter[str] = Counter()
    source_outputs: dict[str, str] = {}
    for shard in role_manifest["shards"]:
        input_path = Path(shard["path"])
        if _sha256(input_path) != shard["sha256"]:
            raise ValueError("prepared retry input checksum mismatch")
        output_path = output_dir / f"{input_path.stem}.output.jsonl"
        input_rows = _read_jsonl(input_path)
        output_rows = _read_jsonl(output_path)
        shard_inputs = {str(row["custom_id"]): row for row in input_rows}
        shard_outputs = {str(row["custom_id"]): row for row in output_rows}
        if len(shard_inputs) != len(input_rows) or len(shard_outputs) != len(output_rows):
            raise ValueError("review shard contains duplicate custom IDs")
        if set(shard_inputs) != set(shard_outputs):
            raise ValueError("review output does not exactly cover its input shard")
        if set(inputs).intersection(shard_inputs):
            raise ValueError("review shards contain duplicate custom IDs")
        inputs.update(shard_inputs)
        source_outputs[str(output_path)] = _sha256(output_path)
        for custom_id, row in shard_outputs.items():
            try:
                _validate_output_row(row, reviewer_id)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                invalid[custom_id] = row
                body = row.get("response", {}).get("body", {})
                detail = body.get("incomplete_details") or {}
                reason = str(detail.get("reason") or type(exc).__name__)
                reasons[reason] += 1
    if not invalid:
        raise ValueError("review outputs have no invalid rows to retry")
    retry_ids = sorted(invalid)
    retry_path.parent.mkdir(parents=True, exist_ok=True)
    with retry_path.open("w") as destination:
        for custom_id in retry_ids:
            request = copy.deepcopy(inputs[custom_id])
            request["body"]["max_output_tokens"] = max_output_tokens
            destination.write(json.dumps(request, ensure_ascii=False) + "\n")
    manifest = {
        "path": str(retry_path),
        "requests": len(retry_ids),
        "model": role_manifest["model"],
        "reviewer_id": reviewer_id,
        "role": role,
        "max_output_tokens": max_output_tokens,
        "sha256": _sha256(retry_path),
        "source_manifest": str(prepared_path),
        "source_manifest_sha256": _sha256(prepared_path),
        "source_outputs": dict(sorted(source_outputs.items())),
        "retry_custom_ids": retry_ids,
        "reasons": dict(sorted(reasons.items())),
    }
    manifest_path = retry_path.with_suffix(".manifest.json")
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def merge_output_retry(
    input_path: Path,
    output_path: Path,
    retry_input_path: Path,
    retry_output_path: Path,
    merged_path: Path,
    *,
    reviewer_id: str,
) -> dict[str, Any]:
    input_rows = _read_jsonl(input_path)
    output_rows = _read_jsonl(output_path)
    retry_input_rows = _read_jsonl(retry_input_path)
    retry_output_rows = _read_jsonl(retry_output_path)
    expected_ids = [str(row["custom_id"]) for row in input_rows]
    retry_ids = {str(row["custom_id"]) for row in retry_input_rows}
    retry_outputs = {str(row["custom_id"]): row for row in retry_output_rows}
    if len(retry_ids) != len(retry_input_rows) or len(retry_outputs) != len(
        retry_output_rows
    ):
        raise ValueError("retry files contain duplicate custom IDs")
    if retry_ids != set(retry_outputs) or not retry_ids.issubset(expected_ids):
        raise ValueError("retry output does not exactly cover retry input")
    original_outputs = {str(row["custom_id"]): row for row in output_rows}
    if set(original_outputs) != set(expected_ids):
        raise ValueError("original output does not exactly cover original input")
    merged_path.parent.mkdir(parents=True, exist_ok=True)
    with merged_path.open("w") as destination:
        for custom_id in expected_ids:
            row = retry_outputs.get(custom_id, original_outputs[custom_id])
            destination.write(json.dumps(row, ensure_ascii=False) + "\n")
    validated = validate_output_shard(input_path, merged_path, reviewer_id=reviewer_id)
    return {
        **validated,
        "replaced_requests": len(retry_ids),
        "source_output_sha256": _sha256(output_path),
        "retry_input_sha256": _sha256(retry_input_path),
        "retry_output_sha256": _sha256(retry_output_path),
    }


def merge_adjudication_retry(
    input_path: Path,
    output_path: Path,
    retry_input_path: Path,
    retry_output_path: Path,
    merged_path: Path,
) -> dict[str, Any]:
    return merge_output_retry(
        input_path,
        output_path,
        retry_input_path,
        retry_output_path,
        merged_path,
        reviewer_id=ADJUDICATOR,
    )


def merge_output_directory_retry(
    input_dir: Path,
    output_dir: Path,
    retry_input_path: Path,
    retry_output_path: Path,
    merged_dir: Path,
) -> dict[str, Any]:
    if merged_dir.exists():
        raise ValueError("merged output directory already exists")
    prepared = json.loads((input_dir / "manifest.json").read_text())
    retry_inputs_list = _read_jsonl(retry_input_path)
    retry_outputs_list = _read_jsonl(retry_output_path)
    retry_inputs = {str(row["custom_id"]): row for row in retry_inputs_list}
    retry_outputs = {str(row["custom_id"]): row for row in retry_outputs_list}
    if len(retry_inputs) != len(retry_inputs_list) or len(retry_outputs) != len(
        retry_outputs_list
    ):
        raise ValueError("retry files contain duplicate custom IDs")
    if set(retry_inputs) != set(retry_outputs):
        raise ValueError("retry output does not exactly cover retry input")

    all_inputs: dict[str, dict[str, Any]] = {}
    reviewer_by_id: dict[str, str] = {}
    plans: list[tuple[Path, list[str], dict[str, dict[str, Any]], str]] = []
    for role in ("a", "b"):
        reviewer_id = str(prepared["files"][role]["reviewer_id"])
        for shard in prepared["files"][role]["shards"]:
            input_path = Path(shard["path"])
            output_path = output_dir / f"{input_path.stem}.output.jsonl"
            input_rows = _read_jsonl(input_path)
            output_rows = _read_jsonl(output_path)
            expected_ids = [str(row["custom_id"]) for row in input_rows]
            original_outputs = {str(row["custom_id"]): row for row in output_rows}
            if len(expected_ids) != len(set(expected_ids)) or len(original_outputs) != len(
                output_rows
            ):
                raise ValueError("review files contain duplicate custom IDs")
            if set(expected_ids) != set(original_outputs):
                raise ValueError("review output does not exactly cover its input shard")
            if set(all_inputs).intersection(expected_ids):
                raise ValueError("review shards contain duplicate custom IDs")
            for row in input_rows:
                custom_id = str(row["custom_id"])
                all_inputs[custom_id] = row
                reviewer_by_id[custom_id] = reviewer_id
            plans.append((input_path, expected_ids, original_outputs, reviewer_id))

    if not set(retry_inputs).issubset(all_inputs):
        raise ValueError("retry input contains an unknown custom ID")
    for custom_id, retry_request in retry_inputs.items():
        expected = copy.deepcopy(all_inputs[custom_id])
        original_limit = int(expected["body"]["max_output_tokens"])
        retry_limit = int(retry_request["body"]["max_output_tokens"])
        if retry_limit <= original_limit:
            raise ValueError("retry output-token limit was not increased")
        expected["body"]["max_output_tokens"] = retry_limit
        if retry_request != expected:
            raise ValueError("retry request differs from its source beyond output-token limit")
        _validate_output_row(retry_outputs[custom_id], reviewer_by_id[custom_id])

    rendered: list[tuple[str, list[dict[str, Any]]]] = []
    replaced_ids: set[str] = set()
    for input_path, expected_ids, original_outputs, reviewer_id in plans:
        rows: list[dict[str, Any]] = []
        for custom_id in expected_ids:
            row = retry_outputs.get(custom_id, original_outputs[custom_id])
            _validate_output_row(row, reviewer_id)
            if custom_id in retry_outputs:
                replaced_ids.add(custom_id)
            rows.append(row)
        rendered.append((f"{input_path.stem}.output.jsonl", rows))
    if replaced_ids != set(retry_inputs):
        raise ValueError("not every retry output replaced a source row")

    merged_dir.mkdir(parents=True)
    for filename, rows in rendered:
        with (merged_dir / filename).open("w") as destination:
            for row in rows:
                destination.write(json.dumps(row, ensure_ascii=False) + "\n")
    validated = validate_output_directory(input_dir, merged_dir)
    return {
        **validated,
        "replaced_requests": len(replaced_ids),
        "source_output_directory": str(output_dir),
        "retry_input_sha256": _sha256(retry_input_path),
        "retry_output_sha256": _sha256(retry_output_path),
    }


def validate_batch_output(
    input_path: Path,
    output_path: Path,
    state_path: Path,
    *,
    reviewer_id: str,
) -> dict[str, Any]:
    result = validate_output_shard(input_path, output_path, reviewer_id=reviewer_id)
    state = json.loads(state_path.read_text())
    if state.get("input_path") != str(input_path):
        raise ValueError("Batch state input path mismatch")
    if state.get("input_sha256") != result["input_sha256"]:
        raise ValueError("Batch state input checksum mismatch")
    if state.get("status") != "completed" or not state.get("output_file_id"):
        raise ValueError("Batch is not recorded as completed")
    request_counts = state.get("request_counts") or {}
    expected_counts = {
        "completed": result["requests"],
        "failed": 0,
        "total": result["requests"],
    }
    if request_counts != expected_counts:
        raise ValueError("Batch request counts are incomplete")
    if state.get("error_file_id"):
        raise ValueError("Batch has an error output file")
    if state.get("download_path") != str(output_path):
        raise ValueError("Batch state download path mismatch")
    if state.get("download_sha256") != result["output_sha256"]:
        raise ValueError("Batch state download checksum mismatch")
    return {
        **result,
        "batch_id": state["batch_id"],
        "output_file_id": state["output_file_id"],
        "request_counts": request_counts,
        "usage": state.get("usage"),
    }


def validate_adjudication_output(
    input_path: Path,
    output_path: Path,
    state_path: Path,
) -> dict[str, Any]:
    return validate_batch_output(
        input_path,
        output_path,
        state_path,
        reviewer_id=ADJUDICATOR,
    )


def validate_output_directory(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    prepared = json.loads((input_dir / "manifest.json").read_text())
    roles: dict[str, Any] = {}
    total = 0
    for role in ("a", "b"):
        reviewer_id = prepared["files"][role]["reviewer_id"]
        shards = []
        for shard in prepared["files"][role]["shards"]:
            input_path = Path(shard["path"])
            output_path = output_dir / f"{input_path.stem}.output.jsonl"
            result = validate_output_shard(
                input_path, output_path, reviewer_id=reviewer_id
            )
            if result["input_sha256"] != shard["sha256"]:
                raise ValueError("downloaded output is bound to an unexpected input shard")
            shards.append(result)
            total += result["requests"]
        roles[role] = {
            "model": prepared["files"][role]["model"],
            "reviewer_id": reviewer_id,
            "requests": sum(value["requests"] for value in shards),
            "shards": shards,
        }
    manifest = {
        "dataset": prepared["dataset"],
        "dataset_sha256": prepared["dataset_sha256"],
        "prepared_manifest_sha256": _sha256(input_dir / "manifest.json"),
        "requests": total,
        "roles": roles,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def _existing_payload_matches(
    database_path: Path,
    *,
    table: str,
    example_id: str,
    identity_column: str,
    identity_value: str,
    payload: dict[str, Any],
) -> bool:
    connection = sqlite3.connect(database_path)
    row = connection.execute(
        f"SELECT payload_json FROM {table} WHERE example_id=? AND {identity_column}=?",
        (example_id, identity_value),
    ).fetchone()
    connection.close()
    return row is not None and json.loads(row[0]) == payload


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
                    decision = AnnotationDecision(
                        **payload,
                        reviewer_id=reviewer_id,
                        adjudicator_id=reviewer_id,
                    )
                    if not _existing_payload_matches(
                        database_path,
                        table="annotation_adjudications",
                        example_id=example_id,
                        identity_column="adjudicator_id",
                        identity_value=reviewer_id,
                        payload=decision.model_dump(mode="json"),
                    ):
                        store.adjudicate(example_id, decision)
                else:
                    review = AnnotationReview(**payload, reviewer_id=reviewer_id)
                    if not _existing_payload_matches(
                        database_path,
                        table="annotation_reviews",
                        example_id=example_id,
                        identity_column="reviewer_id",
                        identity_value=reviewer_id,
                        payload=review.model_dump(mode="json"),
                    ):
                        store.submit_review(example_id, review)
                counts["imported"] += 1
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                counts["failed"] += 1
                print(f"line {line_number}: {exc}")
    return counts


def import_adjudication_output(
    dataset_path: Path,
    database_path: Path,
    input_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    validated = validate_output_shard(
        input_path, output_path, reviewer_id=ADJUDICATOR
    )
    prefix = f"{ADJUDICATOR}:"
    expected_ids = {
        str(row["custom_id"])[len(prefix) :] for row in _read_jsonl(input_path)
    }
    result = import_output(
        dataset_path,
        database_path,
        output_path,
        reviewer_id=ADJUDICATOR,
        adjudication=True,
    )
    if result["failed"]:
        raise ValueError(f"adjudication import failed for {result['failed']} rows")

    connection = sqlite3.connect(database_path)
    adjudication_rows = connection.execute(
        "SELECT example_id, adjudicator_id FROM annotation_adjudications"
    ).fetchall()
    review_rows = connection.execute(
        "SELECT example_id, payload_json FROM annotation_reviews"
    ).fetchall()
    connection.close()
    actual_ids = {
        str(example_id)
        for example_id, adjudicator_id in adjudication_rows
        if adjudicator_id == ADJUDICATOR
    }
    if actual_ids != expected_ids or len(adjudication_rows) != len(expected_ids):
        raise ValueError("stored adjudications do not exactly match the prepared requests")
    reviews_by_id: dict[str, list[dict[str, Any]]] = {}
    for example_id, payload_json in review_rows:
        if example_id in expected_ids:
            reviews_by_id.setdefault(str(example_id), []).append(json.loads(payload_json))
    if set(reviews_by_id) != expected_ids or any(
        len(values) != 2 or len({_signature(value) for value in values}) != 2
        for values in reviews_by_id.values()
    ):
        raise ValueError("adjudications are not backed by two disagreeing reviews")
    progress = AnnotationStore(dataset_path, database_path).progress().model_dump()
    return {
        **result,
        "database": str(database_path),
        "database_sha256": _sha256(database_path),
        "adjudications": len(actual_ids),
        "validated_output_sha256": validated["output_sha256"],
        "progress": progress,
    }


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


def validate_submission_states(input_dir: Path, state_dir: Path) -> dict[str, Any]:
    manifest = json.loads((input_dir / "manifest.json").read_text())
    expected_state_paths: set[Path] = set()
    batch_ids: set[str] = set()
    input_file_ids: set[str] = set()
    statuses: Counter[str] = Counter()
    roles: dict[str, int] = {}
    for role in ("a", "b"):
        shards = manifest["files"][role]["shards"]
        roles[role] = len(shards)
        for shard in shards:
            input_path = Path(shard["path"])
            state_path = state_dir / f"{input_path.stem}.state.json"
            expected_state_paths.add(state_path)
            state = json.loads(state_path.read_text())
            if state.get("input_path") != str(input_path):
                raise ValueError(f"submission state input path mismatch: {state_path}")
            if state.get("input_sha256") != shard["sha256"]:
                raise ValueError(f"submission state checksum mismatch: {state_path}")
            batch_id = str(state.get("batch_id", ""))
            input_file_id = str(state.get("input_file_id", ""))
            status = str(state.get("status", ""))
            if not batch_id or not input_file_id or not status:
                raise ValueError(f"submission state is incomplete: {state_path}")
            if batch_id in batch_ids or input_file_id in input_file_ids:
                raise ValueError("submission states contain duplicate remote IDs")
            batch_ids.add(batch_id)
            input_file_ids.add(input_file_id)
            statuses[status] += 1
    actual_state_paths = set(state_dir.glob("*.state.json"))
    if actual_state_paths != expected_state_paths:
        raise ValueError("submission state files do not exactly match prepared shards")
    return {
        "states": len(expected_state_paths),
        "roles": roles,
        "statuses": dict(sorted(statuses.items())),
        "unique_batch_ids": len(batch_ids),
        "unique_input_file_ids": len(input_file_ids),
    }


def batch_status(state_path: Path, key_file: Path | None) -> dict[str, Any]:
    state = json.loads(state_path.read_text())
    batch = _client(key_file).batches.retrieve(state["batch_id"])
    status = batch.model_dump(mode="json")
    previous_progress = {
        "status": state.get("status"),
        "request_counts": state.get("request_counts"),
        "output_file_id": state.get("output_file_id"),
        "error_file_id": state.get("error_file_id"),
        "usage": state.get("usage"),
    }
    state["status"] = status["status"]
    state["request_counts"] = status.get("request_counts")
    state["output_file_id"] = status.get("output_file_id")
    state["error_file_id"] = status.get("error_file_id")
    state["usage"] = status.get("usage")
    for field in (
        "completion_window",
        "created_at",
        "in_progress_at",
        "expires_at",
        "finalizing_at",
        "completed_at",
        "failed_at",
        "expired_at",
        "cancelling_at",
        "cancelled_at",
        "errors",
    ):
        state[field] = status.get(field)
    current_progress = {
        "status": state.get("status"),
        "request_counts": state.get("request_counts"),
        "output_file_id": state.get("output_file_id"),
        "error_file_id": state.get("error_file_id"),
        "usage": state.get("usage"),
    }
    checked_at = int(time.time())
    state["last_checked_at"] = checked_at
    state["progress_changed_on_last_check"] = current_progress != previous_progress
    if state["progress_changed_on_last_check"]:
        state["last_progress_at"] = checked_at
    elif not state.get("last_progress_at"):
        state["last_progress_at"] = state.get("in_progress_at") or state.get(
            "created_at"
        )
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return state


def status_shards(state_dir: Path, key_file: Path | None) -> dict[str, Any]:
    paths = sorted(state_dir.glob("*.state.json"))
    if not paths:
        raise FileNotFoundError(f"no submission states found in {state_dir}")
    states = [batch_status(path, key_file) for path in paths]
    return {
        "jobs": [
            {
                "batch_id": state["batch_id"],
                "input_path": state["input_path"],
                "status": state["status"],
                "request_counts": state.get("request_counts"),
                "output_file_id": state.get("output_file_id"),
                "error_file_id": state.get("error_file_id"),
                "created_at": state.get("created_at"),
                "in_progress_at": state.get("in_progress_at"),
                "expires_at": state.get("expires_at"),
                "finalizing_at": state.get("finalizing_at"),
                "completed_at": state.get("completed_at"),
                "failed_at": state.get("failed_at"),
                "expired_at": state.get("expired_at"),
                "last_checked_at": state.get("last_checked_at"),
                "last_progress_at": state.get("last_progress_at"),
                "progress_changed_on_last_check": state.get(
                    "progress_changed_on_last_check"
                ),
                "usage": state.get("usage"),
            }
            for state in states
        ],
        "statuses": dict(sorted(Counter(state["status"] for state in states).items())),
    }


def wait_for_shards(
    state_dir: Path,
    key_file: Path | None,
    *,
    interval_seconds: int = 30,
) -> dict[str, Any]:
    if interval_seconds < 1:
        raise ValueError("poll interval must be positive")
    terminal_failures = {"failed", "expired", "cancelled", "canceled"}
    while True:
        result = status_shards(state_dir, key_file)
        print(json.dumps(result["statuses"], sort_keys=True), flush=True)
        statuses = set(result["statuses"])
        failed = statuses & terminal_failures
        if failed:
            raise RuntimeError(f"batch jobs ended unsuccessfully: {', '.join(sorted(failed))}")
        if statuses == {"completed"}:
            return result
        time.sleep(interval_seconds)


def wait_for_batch(
    state_path: Path,
    key_file: Path | None,
    *,
    interval_seconds: int = 30,
) -> dict[str, Any]:
    if interval_seconds < 1:
        raise ValueError("poll interval must be positive")
    terminal_failures = {"failed", "expired", "cancelled", "canceled"}
    while True:
        state = batch_status(state_path, key_file)
        print(json.dumps({"status": state["status"]}, sort_keys=True), flush=True)
        if state["status"] in terminal_failures:
            raise RuntimeError(f"batch job ended unsuccessfully: {state['status']}")
        if state["status"] == "completed":
            return state
        time.sleep(interval_seconds)


def download_batch_output(
    state_path: Path, output_path: Path, key_file: Path | None
) -> dict[str, Any]:
    state = batch_status(state_path, key_file)
    if state["status"] != "completed" or not state.get("output_file_id"):
        raise RuntimeError(f"batch is not complete: {state['status']}")
    response = _client(key_file).files.content(state["output_file_id"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    response.write_to_file(output_path)
    state["download_path"] = str(output_path)
    state["download_sha256"] = _sha256(output_path)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return {"path": str(output_path), "sha256": state["download_sha256"]}


def download_shards(
    state_dir: Path,
    output_dir: Path,
    key_file: Path | None,
) -> dict[str, Any]:
    state_paths = sorted(state_dir.glob("*.state.json"))
    if not state_paths:
        raise FileNotFoundError(f"no submission states found in {state_dir}")
    states = [json.loads(path.read_text()) for path in state_paths]
    output_dir.mkdir(parents=True, exist_ok=True)
    client = None
    files = []
    existing = []
    pending = []
    for state_path, state in zip(state_paths, states, strict=True):
        if state.get("status") != "completed":
            pending.append(state["batch_id"])
            continue
        output_file_id = state.get("output_file_id")
        if not output_file_id:
            raise RuntimeError(f"completed batch has no output file: {state['batch_id']}")
        output_path = output_dir / f"{Path(state['input_path']).stem}.output.jsonl"
        if (
            output_path.exists()
            and state.get("download_sha256") == _sha256(output_path)
        ):
            existing.append(str(output_path))
            continue
        if client is None:
            client = _client(key_file)
        response = client.files.content(output_file_id)
        response.write_to_file(output_path)
        output_sha256 = _sha256(output_path)
        state["download_path"] = str(output_path)
        state["download_sha256"] = output_sha256
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        files.append(
            {
                "batch_id": state["batch_id"],
                "input_path": state["input_path"],
                "output_file_id": output_file_id,
                "output_path": str(output_path),
                "output_sha256": output_sha256,
            }
        )
    return {
        "downloaded": len(files),
        "existing": existing,
        "pending_batch_ids": pending,
        "files": files,
    }


def import_output_directory(
    dataset_path: Path,
    database_path: Path,
    input_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    outputs = validate_output_directory(input_dir, output_dir)
    counts = {"imported": 0, "failed": 0}
    for role in ("a", "b"):
        reviewer_id = outputs["roles"][role]["reviewer_id"]
        for shard in outputs["roles"][role]["shards"]:
            result = import_output(
                dataset_path,
                database_path,
                Path(shard["output"]),
                reviewer_id=reviewer_id,
            )
            counts["imported"] += result["imported"]
            counts["failed"] += result["failed"]
    if counts["failed"]:
        raise ValueError(f"review import failed for {counts['failed']} rows")

    queue_ids = {
        str(row["example_id"])
        for row in _read_jsonl(input_dir / "review-queue.jsonl")
    }
    connection = sqlite3.connect(database_path)
    review_rows = connection.execute(
        "SELECT example_id, reviewer_id FROM annotation_reviews"
    ).fetchall()
    connection.close()
    reviewed_ids = {str(row[0]) for row in review_rows}
    reviewer_counts = dict(sorted(Counter(str(row[1]) for row in review_rows).items()))
    if reviewed_ids != queue_ids:
        raise ValueError("imported review IDs do not exactly match the prepared queue")
    expected_reviewer_counts = {
        outputs["roles"][role]["reviewer_id"]: outputs["roles"][role]["requests"]
        for role in ("a", "b")
    }
    if reviewer_counts != dict(sorted(expected_reviewer_counts.items())):
        raise ValueError("imported reviewer counts do not match validated outputs")
    progress = AnnotationStore(dataset_path, database_path).progress().model_dump()
    return {
        **counts,
        "database": str(database_path),
        "database_sha256": _sha256(database_path),
        "review_rows": len(review_rows),
        "reviewed_examples": len(reviewed_ids),
        "reviewer_counts": reviewer_counts,
        "progress": progress,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--dataset", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--locale", default="en-US")
    prepare.add_argument("--chunk-size", type=int, default=1_000)
    prepare.add_argument("--max-examples", type=int)
    prepare.add_argument("--seed", type=int, default=DEFAULT_REVIEW_SEED)
    prepare.add_argument("--blind-provenance", action="store_true")
    prepare.add_argument("--supplemental-context", type=Path)
    prepare.add_argument(
        "--prompt-profile", choices=sorted(PROMPT_PROFILES), default="legacy"
    )

    validate_prepared = subparsers.add_parser("validate-prepared")
    validate_prepared.add_argument("--input", type=Path, required=True)

    validate_submissions = subparsers.add_parser("validate-submissions")
    validate_submissions.add_argument("--input", type=Path, required=True)
    validate_submissions.add_argument("--states", type=Path, required=True)

    adjudicate = subparsers.add_parser("prepare-adjudication")
    adjudicate.add_argument("--dataset", type=Path, required=True)
    adjudicate.add_argument("--reviews", type=Path, required=True)
    adjudicate.add_argument("--output", type=Path, required=True)
    adjudicate.add_argument("--blind-provenance", action="store_true")
    adjudicate.add_argument("--supplemental-context", type=Path)
    adjudicate.add_argument(
        "--prompt-profile", choices=sorted(PROMPT_PROFILES), default="legacy"
    )

    validate_adjudication = subparsers.add_parser("validate-adjudication")
    validate_adjudication.add_argument("--dataset", type=Path, required=True)
    validate_adjudication.add_argument("--reviews", type=Path, required=True)
    validate_adjudication.add_argument("--input", type=Path, required=True)
    validate_adjudication.add_argument("--manifest", type=Path, required=True)

    validate_adjudication_output_parser = subparsers.add_parser(
        "validate-adjudication-output"
    )
    validate_adjudication_output_parser.add_argument("--input", type=Path, required=True)
    validate_adjudication_output_parser.add_argument("--output", type=Path, required=True)
    validate_adjudication_output_parser.add_argument("--state", type=Path, required=True)

    retry_adjudication = subparsers.add_parser("prepare-adjudication-retry")
    retry_adjudication.add_argument("--input", type=Path, required=True)
    retry_adjudication.add_argument("--output", type=Path, required=True)
    retry_adjudication.add_argument("--retry", type=Path, required=True)
    retry_adjudication.add_argument("--max-output-tokens", type=int, default=1_000)

    retry_reviews = subparsers.add_parser("prepare-review-retry")
    retry_reviews.add_argument("--input", type=Path, required=True)
    retry_reviews.add_argument("--outputs", type=Path, required=True)
    retry_reviews.add_argument("--retry", type=Path, required=True)
    retry_reviews.add_argument("--role", choices=["a", "b"], required=True)
    retry_reviews.add_argument("--max-output-tokens", type=int, default=1_000)

    merge_adjudication = subparsers.add_parser("merge-adjudication-retry")
    merge_adjudication.add_argument("--input", type=Path, required=True)
    merge_adjudication.add_argument("--output", type=Path, required=True)
    merge_adjudication.add_argument("--retry-input", type=Path, required=True)
    merge_adjudication.add_argument("--retry-output", type=Path, required=True)
    merge_adjudication.add_argument("--merged", type=Path, required=True)

    merge_reviews = subparsers.add_parser("merge-review-retry")
    merge_reviews.add_argument("--input", type=Path, required=True)
    merge_reviews.add_argument("--outputs", type=Path, required=True)
    merge_reviews.add_argument("--retry-input", type=Path, required=True)
    merge_reviews.add_argument("--retry-output", type=Path, required=True)
    merge_reviews.add_argument("--merged-outputs", type=Path, required=True)

    validate_batch = subparsers.add_parser("validate-batch-output")
    validate_batch.add_argument("--input", type=Path, required=True)
    validate_batch.add_argument("--output", type=Path, required=True)
    validate_batch.add_argument("--state", type=Path, required=True)
    validate_batch.add_argument("--reviewer-id", required=True)

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

    status_many = subparsers.add_parser("status-shards")
    status_many.add_argument("--states", type=Path, required=True)
    status_many.add_argument("--key-file", type=Path)

    wait_many = subparsers.add_parser("wait-shards")
    wait_many.add_argument("--states", type=Path, required=True)
    wait_many.add_argument("--key-file", type=Path)
    wait_many.add_argument("--interval-seconds", type=int, default=30)

    wait_one = subparsers.add_parser("wait")
    wait_one.add_argument("--state", type=Path, required=True)
    wait_one.add_argument("--key-file", type=Path)
    wait_one.add_argument("--interval-seconds", type=int, default=30)

    download = subparsers.add_parser("download")
    download.add_argument("--state", type=Path, required=True)
    download.add_argument("--output", type=Path, required=True)
    download.add_argument("--key-file", type=Path)

    download_many = subparsers.add_parser("download-shards")
    download_many.add_argument("--states", type=Path, required=True)
    download_many.add_argument("--outputs", type=Path, required=True)
    download_many.add_argument("--key-file", type=Path)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--dataset", type=Path, required=True)
    import_parser.add_argument("--reviews", type=Path, required=True)
    import_parser.add_argument("--output", type=Path, required=True)
    import_parser.add_argument("--reviewer-id", required=True)
    import_parser.add_argument("--adjudication", action="store_true")

    import_many = subparsers.add_parser("import-shards")
    import_many.add_argument("--dataset", type=Path, required=True)
    import_many.add_argument("--reviews", type=Path, required=True)
    import_many.add_argument("--input", type=Path, required=True)
    import_many.add_argument("--outputs", type=Path, required=True)

    import_adjudication = subparsers.add_parser("import-adjudication")
    import_adjudication.add_argument("--dataset", type=Path, required=True)
    import_adjudication.add_argument("--reviews", type=Path, required=True)
    import_adjudication.add_argument("--input", type=Path, required=True)
    import_adjudication.add_argument("--output", type=Path, required=True)

    validate_outputs = subparsers.add_parser("validate-outputs")
    validate_outputs.add_argument("--input", type=Path, required=True)
    validate_outputs.add_argument("--outputs", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_reviews(
            args.dataset,
            args.output,
            locale=args.locale,
            chunk_size=args.chunk_size,
            max_examples=args.max_examples,
            seed=args.seed,
            blind_provenance=args.blind_provenance,
            supplemental_context_path=args.supplemental_context,
            prompt_profile=args.prompt_profile,
        )
    elif args.command == "validate-prepared":
        result = validate_prepared_reviews(args.input)
    elif args.command == "validate-submissions":
        result = validate_submission_states(args.input, args.states)
    elif args.command == "prepare-adjudication":
        result = prepare_adjudications(
            args.dataset,
            args.reviews,
            args.output,
            blind_provenance=args.blind_provenance,
            supplemental_context_path=args.supplemental_context,
            prompt_profile=args.prompt_profile,
        )
    elif args.command == "validate-adjudication":
        result = validate_prepared_adjudications(
            args.dataset, args.reviews, args.input, args.manifest
        )
    elif args.command == "validate-adjudication-output":
        result = validate_adjudication_output(args.input, args.output, args.state)
    elif args.command == "prepare-adjudication-retry":
        result = prepare_adjudication_retry(
            args.input,
            args.output,
            args.retry,
            max_output_tokens=args.max_output_tokens,
        )
    elif args.command == "prepare-review-retry":
        result = prepare_output_directory_retry(
            args.input,
            args.outputs,
            args.retry,
            role=args.role,
            max_output_tokens=args.max_output_tokens,
        )
    elif args.command == "merge-adjudication-retry":
        result = merge_adjudication_retry(
            args.input,
            args.output,
            args.retry_input,
            args.retry_output,
            args.merged,
        )
    elif args.command == "merge-review-retry":
        result = merge_output_directory_retry(
            args.input,
            args.outputs,
            args.retry_input,
            args.retry_output,
            args.merged_outputs,
        )
    elif args.command == "validate-batch-output":
        result = validate_batch_output(
            args.input,
            args.output,
            args.state,
            reviewer_id=args.reviewer_id,
        )
    elif args.command == "submit":
        result = submit_batch(args.input, args.state, args.key_file)
    elif args.command == "submit-shards":
        result = submit_shards(args.input, args.states, args.role, args.key_file)
    elif args.command == "status":
        result = batch_status(args.state, args.key_file)
    elif args.command == "status-shards":
        result = status_shards(args.states, args.key_file)
    elif args.command == "wait-shards":
        result = wait_for_shards(
            args.states,
            args.key_file,
            interval_seconds=args.interval_seconds,
        )
    elif args.command == "wait":
        result = wait_for_batch(
            args.state,
            args.key_file,
            interval_seconds=args.interval_seconds,
        )
    elif args.command == "download":
        result = download_batch_output(args.state, args.output, args.key_file)
    elif args.command == "download-shards":
        result = download_shards(args.states, args.outputs, args.key_file)
    elif args.command == "validate-outputs":
        result = validate_output_directory(args.input, args.outputs)
    elif args.command == "import-shards":
        result = import_output_directory(
            args.dataset, args.reviews, args.input, args.outputs
        )
    elif args.command == "import-adjudication":
        result = import_adjudication_output(
            args.dataset, args.reviews, args.input, args.output
        )
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
