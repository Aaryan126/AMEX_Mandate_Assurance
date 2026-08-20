from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.annotations import AnnotationStore
from app.commercial_rules import evaluate_commercial_rules
from app.treatment_contract import POLICY_VERSION, treatment_for_signals

from ml.data.schema import AceDatasetExample, DatasetLabels

AUDIT_VERSION = "human-audit-v1"
DEFAULT_ROWS = 400
HUMAN_ID_PREFIX = "human-"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_hash(value: str, seed: int) -> str:
    return hashlib.sha256(f"{AUDIT_VERSION}:{seed}:{value}".encode()).hexdigest()


def _load(path: Path, cohort: str) -> list[tuple[AceDatasetExample, str, Path]]:
    values: list[tuple[AceDatasetExample, str, Path]] = []
    with path.open() as source:
        for line in source:
            if line.strip():
                values.append((AceDatasetExample.model_validate_json(line), cohort, path))
    return values


def _attack_family(value: AceDatasetExample) -> str:
    transformation = value.provenance.transformation
    return transformation if transformation and transformation != "none" else "none"


def _stratum(value: AceDatasetExample, cohort: str) -> tuple[str, ...]:
    return (
        cohort,
        value.labels.label_source,
        _attack_family(value),
        str(value.provenance.evidence_origin),
    )


def select_audit_rows(
    candidates: list[tuple[AceDatasetExample, str, Path]],
    *,
    rows: int = DEFAULT_ROWS,
    seed: int = 2028,
) -> list[tuple[AceDatasetExample, str, Path]]:
    """Round-robin across provenance/attack strata while keeping one row per group."""
    if rows < 1:
        raise ValueError("rows must be positive")
    by_id: dict[str, tuple[AceDatasetExample, str, Path]] = {}
    for candidate in candidates:
        example_id = candidate[0].identity.example_id
        by_id.setdefault(example_id, candidate)
    buckets: dict[tuple[str, ...], list[tuple[AceDatasetExample, str, Path]]] = (
        defaultdict(list)
    )
    for candidate in by_id.values():
        buckets[_stratum(candidate[0], candidate[1])].append(candidate)
    for key, values in buckets.items():
        values.sort(key=lambda item: _stable_hash(f"{key}:{item[0].identity.example_id}", seed))

    selected: list[tuple[AceDatasetExample, str, Path]] = []
    used_groups: set[str] = set()
    active = sorted(buckets)
    cursors = {key: 0 for key in active}
    while active and len(selected) < rows:
        next_active: list[tuple[str, ...]] = []
        for key in active:
            values = buckets[key]
            cursor = cursors[key]
            while cursor < len(values) and values[cursor][0].identity.group_id in used_groups:
                cursor += 1
            cursors[key] = cursor
            if cursor >= len(values):
                continue
            candidate = values[cursor]
            cursors[key] += 1
            selected.append(candidate)
            used_groups.add(candidate[0].identity.group_id)
            if cursors[key] < len(values):
                next_active.append(key)
            if len(selected) == rows:
                break
        active = next_active
    if len(selected) != rows:
        raise ValueError(f"only {len(selected)} unique audit groups available for {rows} rows")
    return sorted(selected, key=lambda item: item[0].identity.example_id)


def _oracle(value: AceDatasetExample) -> dict[str, Any]:
    signals = evaluate_commercial_rules(value.mandate, value.state, value.cart)
    failed_codes = [
        signal.reason_code
        for signal in signals
        if signal.status == "FAIL" and signal.reason_code is not None
    ]
    has_unclassified = any(
        signal.status == "FAIL" and signal.reason_code is None for signal in signals
    )
    has_not_evaluable = any(signal.status == "NOT_EVALUABLE" for signal in signals)
    return {
        "policy_version": POLICY_VERSION,
        "signals": [asdict(signal) for signal in signals],
        "failed_reason_codes": failed_codes,
        "deterministic_treatment": treatment_for_signals(
            failed_codes,
            has_unclassified_failure=has_unclassified,
            has_not_evaluable=has_not_evaluable,
        ).value,
    }


def _blinded_payload(value: AceDatasetExample, oracle: dict[str, Any]) -> dict[str, Any]:
    blinded = value.model_copy(deep=True)
    blinded.identity.parent_example_id = None
    blinded.provenance.transformation = "none"
    blinded.provenance.generator_version = None
    blinded.provenance.field_origins = {}
    blinded.labels = DatasetLabels(label_source="unreviewed")
    payload = blinded.model_dump(mode="json")
    payload["audit_context"] = {
        "policy_version": oracle["policy_version"],
        "commercial_rule_results": oracle["signals"],
        "deterministic_treatment": oracle["deterministic_treatment"],
        "review_scope": "Review semantic fit and policy treatment; do not recompute arithmetic.",
    }
    return payload


def prepare_audit(
    development: Path,
    holdout: Path,
    output_dir: Path,
    *,
    rows: int = DEFAULT_ROWS,
    seed: int = 2028,
) -> dict[str, Any]:
    selected = select_audit_rows(
        [*_load(development, "development"), *_load(holdout, "consumed_holdout")],
        rows=rows,
        seed=seed,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    queue_path = output_dir / "review-queue.jsonl"
    ledger_path = output_dir / "audit-ledger.jsonl"
    queue_lines: list[str] = []
    ledger_lines: list[str] = []
    strata: Counter[str] = Counter()
    attack_families: Counter[str] = Counter()
    label_sources: Counter[str] = Counter()
    evidence_origins: Counter[str] = Counter()
    cohorts: Counter[str] = Counter()
    for value, cohort, source_path in selected:
        oracle = _oracle(value)
        queue_lines.append(json.dumps(_blinded_payload(value, oracle), sort_keys=True) + "\n")
        ledger = {
            "audit_version": AUDIT_VERSION,
            "example_id": value.identity.example_id,
            "group_id": value.identity.group_id,
            "parent_example_id": value.identity.parent_example_id,
            "cohort": cohort,
            "source_dataset_sha256": _sha256(source_path),
            "attack_family": _attack_family(value),
            "evidence_origin": str(value.provenance.evidence_origin),
            "original_labels": value.labels.model_dump(mode="json"),
            "oracle": oracle,
        }
        ledger_lines.append(json.dumps(ledger, sort_keys=True) + "\n")
        key = "|".join(_stratum(value, cohort))
        strata[key] += 1
        attack_families[ledger["attack_family"]] += 1
        label_sources[value.labels.label_source] += 1
        evidence_origins[ledger["evidence_origin"]] += 1
        cohorts[cohort] += 1
    queue_path.write_text("".join(queue_lines))
    ledger_path.write_text("".join(ledger_lines))
    manifest = {
        "audit_version": AUDIT_VERSION,
        "policy_version": POLICY_VERSION,
        "seed": seed,
        "row_count": rows,
        "required_reviews_per_row": 2,
        "requires_human_adjudication": True,
        "reviewer_id_prefix": HUMAN_ID_PREFIX,
        "queue_sha256": _sha256(queue_path),
        "ledger_sha256": _sha256(ledger_path),
        "source_datasets": {
            "development": {"path": str(development), "sha256": _sha256(development)},
            "consumed_holdout": {"path": str(holdout), "sha256": _sha256(holdout)},
        },
        "cohorts": dict(sorted(cohorts.items())),
        "label_sources": dict(sorted(label_sources.items())),
        "attack_families": dict(sorted(attack_families.items())),
        "evidence_origins": dict(sorted(evidence_origins.items())),
        "strata": dict(sorted(strata.items())),
        "blinding": {
            "hidden": [
                "original_labels",
                "attack_family",
                "transformation",
                "generator_version",
                "field_origins",
                "parent_example_id",
                "model_predictions",
            ],
            "shown": [
                "mandate",
                "cart",
                "state",
                "context",
                "source_dataset",
                "evidence_origin",
                "deterministic_rule_results",
            ],
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    validate_prepared_audit(output_dir)
    AnnotationStore(queue_path, output_dir / "human-reviews.sqlite3").initialize()
    return manifest


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def validate_prepared_audit(output_dir: Path) -> dict[str, Any]:
    manifest = json.loads((output_dir / "manifest.json").read_text())
    queue_path = output_dir / "review-queue.jsonl"
    ledger_path = output_dir / "audit-ledger.jsonl"
    queue = _jsonl(queue_path)
    ledger = _jsonl(ledger_path)
    expected = int(manifest["row_count"])
    if len(queue) != expected or len(ledger) != expected:
        raise ValueError("audit queue/ledger row count does not match manifest")
    if _sha256(queue_path) != manifest["queue_sha256"]:
        raise ValueError("audit queue checksum mismatch")
    if _sha256(ledger_path) != manifest["ledger_sha256"]:
        raise ValueError("audit ledger checksum mismatch")
    queue_ids = [row["identity"]["example_id"] for row in queue]
    ledger_ids = [row["example_id"] for row in ledger]
    if len(set(queue_ids)) != expected or set(queue_ids) != set(ledger_ids):
        raise ValueError("audit queue and private ledger IDs do not bind one-to-one")
    groups = [row["identity"]["group_id"] for row in queue]
    if len(set(groups)) != expected:
        raise ValueError("audit queue contains repeated groups")
    for row in queue:
        labels = row["labels"]
        if (
            labels["deviation"] is not None
            or labels["semantic"]
            or labels["violation_types"]
            or labels["expected_treatment"] is not None
            or labels["label_source"] != "unreviewed"
            or labels["reviewer_confidence"] is not None
            or labels["deterministic_outcome"]
            or labels["semantic_outcome"] is not None
            or labels["policy_intervention_target"] is not None
            or labels["binary_deviation"] is not None
        ):
            raise ValueError("audit queue leaks source labels")
        provenance = row["provenance"]
        if (
            provenance["transformation"] != "none"
            or provenance["generator_version"] is not None
            or provenance["field_origins"]
            or row["identity"]["parent_example_id"] is not None
        ):
            raise ValueError("audit queue leaks attack-family metadata")
        if "model_predictions" in row or "attack_family" in row:
            raise ValueError("audit queue leaks hidden evaluation metadata")
    return {"status": "valid", "rows": expected}


def audit_status(output_dir: Path) -> dict[str, Any]:
    validate_prepared_audit(output_dir)
    store = AnnotationStore(
        output_dir / "review-queue.jsonl", output_dir / "human-reviews.sqlite3"
    )
    store.initialize()
    progress = store.progress().model_dump()
    progress["complete"] = (
        progress["agreed"] + progress["adjudicated"] == progress["total"]
        and progress["unreviewed"] == 0
        and progress["single_review"] == 0
        and progress["needs_adjudication"] == 0
    )
    return progress


def prepare_assisted_inputs(output_dir: Path) -> dict[str, Any]:
    """Split the blinded UI queue into a strict dataset and bound LLM audit context."""
    validate_prepared_audit(output_dir)
    assisted_dir = output_dir / "assisted"
    assisted_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = assisted_dir / "assisted-review-dataset.jsonl"
    context_path = assisted_dir / "assisted-context.jsonl"
    dataset_lines: list[str] = []
    context_lines: list[str] = []
    for row in _jsonl(output_dir / "review-queue.jsonl"):
        audit_context = row.pop("audit_context")
        value = AceDatasetExample.model_validate(row)
        dataset_lines.append(value.model_dump_json() + "\n")
        context_lines.append(
            json.dumps(
                {
                    "example_id": value.identity.example_id,
                    "audit_context": audit_context,
                },
                sort_keys=True,
            )
            + "\n"
        )
    dataset_path.write_text("".join(dataset_lines))
    context_path.write_text("".join(context_lines))
    result = {
        "audit_version": AUDIT_VERSION,
        "provenance": "llm_assisted_not_human",
        "rows": len(dataset_lines),
        "dataset": str(dataset_path),
        "dataset_sha256": _sha256(dataset_path),
        "supplemental_context": str(context_path),
        "supplemental_context_sha256": _sha256(context_path),
        "source_queue_sha256": _sha256(output_dir / "review-queue.jsonl"),
    }
    (assisted_dir / "inputs.manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def _signature(payload: dict[str, Any]) -> tuple[Any, ...]:
    return (
        payload["deviation"],
        payload["semantic_label"],
        payload["expected_treatment"],
        tuple(sorted(payload.get("violation_types", []))),
    )


def build_audit_report(output_dir: Path, report_path: Path) -> dict[str, Any]:
    status = audit_status(output_dir)
    if not status["complete"]:
        raise ValueError(f"human audit is incomplete: {status}")
    ledger = {row["example_id"]: row for row in _jsonl(output_dir / "audit-ledger.jsonl")}
    connection = sqlite3.connect(output_dir / "human-reviews.sqlite3")
    connection.row_factory = sqlite3.Row
    reviews: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in connection.execute("SELECT example_id, payload_json FROM annotation_reviews"):
        payload = json.loads(row["payload_json"])
        if not str(payload["reviewer_id"]).startswith(HUMAN_ID_PREFIX):
            raise ValueError("audit contains a non-human reviewer identity")
        reviews[row["example_id"]].append(payload)
    adjudications: dict[str, dict[str, Any]] = {}
    for row in connection.execute(
        "SELECT example_id, payload_json FROM annotation_adjudications"
    ):
        payload = json.loads(row["payload_json"])
        if not str(payload["adjudicator_id"]).startswith(HUMAN_ID_PREFIX):
            raise ValueError("audit contains a non-human adjudicator identity")
        adjudications[row["example_id"]] = payload
    connection.close()

    agreement = 0
    oracle_eligible = 0
    oracle_agree = 0
    treatment_confusion: Counter[str] = Counter()
    attack_stats: dict[str, Counter[str]] = defaultdict(Counter)
    for example_id, private in ledger.items():
        values = reviews[example_id]
        if len(values) != 2 or len({value["reviewer_id"] for value in values}) != 2:
            raise ValueError(f"{example_id} does not have exactly two independent reviews")
        signatures = {_signature(value) for value in values}
        if len(signatures) == 1:
            agreement += 1
            resolved = values[0]
        else:
            resolved = adjudications.get(example_id)
            if resolved is None:
                raise ValueError(f"{example_id} disagreement lacks adjudication")
        original = private["original_labels"].get("expected_treatment") or "UNLABELED"
        treatment_confusion[f"{original}->{resolved['expected_treatment']}"] += 1
        family = private["attack_family"]
        attack_stats[family]["rows"] += 1
        attack_stats[family][f"resolved_{resolved['expected_treatment'].lower()}"] += 1
        deterministic = private["oracle"]["deterministic_treatment"]
        oracle_eligible += 1
        if deterministic != "APPROVE":
            expected = deterministic
        elif (
            resolved["semantic_label"] != "ENTAILMENT"
            or resolved["deviation"] != "MATCH"
            or resolved.get("violation_types")
        ):
            expected = "STEP_UP"
        else:
            expected = "APPROVE"
        oracle_agree += int(resolved["expected_treatment"] == expected)
    oracle_rate = oracle_agree / oracle_eligible if oracle_eligible else 1.0
    report = {
        "audit_version": AUDIT_VERSION,
        "policy_version": POLICY_VERSION,
        "complete": True,
        "rows": len(ledger),
        "independent_review_agreement": agreement / len(ledger),
        "disagreements_adjudicated": len(adjudications),
        "deterministic_oracle_rows": oracle_eligible,
        "deterministic_oracle_agreement": oracle_rate,
        "oracle_gate_passed": oracle_rate == 1.0,
        "treatment_confusion_vs_provisional_labels": dict(sorted(treatment_confusion.items())),
        "by_attack_family": {
            key: dict(sorted(value.items())) for key, value in sorted(attack_stats.items())
        },
        "queue_sha256": _sha256(output_dir / "review-queue.jsonl"),
        "ledger_sha256": _sha256(output_dir / "audit-ledger.jsonl"),
        "review_database_sha256": _sha256(output_dir / "human-reviews.sqlite3"),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if not report["oracle_gate_passed"]:
        raise ValueError(
            "human audit violates the deterministic/semantic treatment contract; "
            f"diagnostic report written to {report_path}"
        )
    return report


def build_assisted_report(output_dir: Path, report_path: Path) -> dict[str, Any]:
    """Report an LLM-assisted audit without representing it as human ground truth."""
    from ml.data.llm_annotations import ADJUDICATOR, REVIEWER_A, REVIEWER_B

    assisted_dir = output_dir / "assisted"
    ledger = {
        row["example_id"]: row for row in _jsonl(output_dir / "audit-ledger.jsonl")
    }
    database_path = assisted_dir / "assisted-reviews.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    reviews: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in connection.execute(
        "SELECT example_id, reviewer_id, payload_json FROM annotation_reviews"
    ):
        reviews[row["example_id"]].append(json.loads(row["payload_json"]))
    adjudications = {
        row["example_id"]: json.loads(row["payload_json"])
        for row in connection.execute(
            "SELECT example_id, payload_json FROM annotation_adjudications"
        )
    }
    connection.close()

    agreement = 0
    policy_agreement = 0
    treatment_confusion: Counter[str] = Counter()
    attack_stats: dict[str, Counter[str]] = defaultdict(Counter)
    resolved_sources: Counter[str] = Counter()
    for example_id, private in ledger.items():
        values = reviews.get(example_id, [])
        if len(values) != 2 or {value["reviewer_id"] for value in values} != {
            REVIEWER_A,
            REVIEWER_B,
        }:
            raise ValueError(f"{example_id} lacks both pinned LLM reviews")
        signatures = {_signature(value) for value in values}
        if len(signatures) == 1:
            agreement += 1
            resolved = values[0]
            resolved_sources["llm_consensus"] += 1
        else:
            resolved = adjudications.get(example_id)
            if resolved is None or resolved.get("adjudicator_id") != ADJUDICATOR:
                raise ValueError(f"{example_id} disagreement lacks pinned adjudication")
            resolved_sources["llm_adjudicated"] += 1
        deterministic = private["oracle"]["deterministic_treatment"]
        if deterministic != "APPROVE":
            expected = deterministic
        elif (
            resolved["semantic_label"] != "ENTAILMENT"
            or resolved["deviation"] != "MATCH"
            or resolved.get("violation_types")
        ):
            expected = "STEP_UP"
        else:
            expected = "APPROVE"
        matches_policy = resolved["expected_treatment"] == expected
        policy_agreement += int(matches_policy)
        original = private["original_labels"].get("expected_treatment") or "UNLABELED"
        treatment_confusion[f"{original}->{resolved['expected_treatment']}"] += 1
        family = private["attack_family"]
        attack_stats[family]["rows"] += 1
        attack_stats[family]["reviewer_agreements"] += int(len(signatures) == 1)
        attack_stats[family]["policy_contract_matches"] += int(matches_policy)
        attack_stats[family][f"resolved_{resolved['expected_treatment'].lower()}"] += 1

    reviewer_states = [
        json.loads(path.read_text()) for path in sorted((assisted_dir / "states").glob("*.json"))
    ]
    adjudication_state = json.loads((assisted_dir / "adjudication.state.json").read_text())
    usage = {
        "gpt_5_4_mini": reviewer_states[0]["usage"],
        "gpt_4_1_mini": reviewer_states[1]["usage"],
        "gpt_5_4_adjudication": adjudication_state["usage"],
    }
    # Official Batch token prices per million as of 2026-08-20.
    estimated_cost = (
        usage["gpt_5_4_mini"]["input_tokens"] * 0.75
        + usage["gpt_5_4_mini"]["output_tokens"] * 4.5
        + usage["gpt_4_1_mini"]["input_tokens"] * 0.4
        + usage["gpt_4_1_mini"]["output_tokens"] * 1.6
        + usage["gpt_5_4_adjudication"]["input_tokens"] * 2.5
        + usage["gpt_5_4_adjudication"]["output_tokens"] * 15.0
    ) / 1_000_000
    rows = len(ledger)
    report = {
        "audit_version": AUDIT_VERSION,
        "benchmark_type": "llm_assisted_not_human",
        "human_validated": False,
        "production_claim_eligible": False,
        "policy_version": POLICY_VERSION,
        "rows": rows,
        "reviewer_agreements": agreement,
        "reviewer_agreement_rate": agreement / rows,
        "disagreements_adjudicated": len(adjudications),
        "resolved_sources": dict(sorted(resolved_sources.items())),
        "policy_contract_matches": policy_agreement,
        "policy_contract_agreement": policy_agreement / rows,
        "treatment_confusion_vs_provisional_labels": dict(
            sorted(treatment_confusion.items())
        ),
        "by_attack_family": {
            key: dict(sorted(value.items())) for key, value in sorted(attack_stats.items())
        },
        "usage": usage,
        "estimated_openai_batch_cost_usd": round(estimated_cost, 4),
        "review_database_sha256": _sha256(database_path),
        "queue_sha256": _sha256(output_dir / "review-queue.jsonl"),
        "ledger_sha256": _sha256(output_dir / "audit-ledger.jsonl"),
        "limitation": (
            "This benchmark replaces manual workload for provisional model development, "
            "but it is not independent human evidence."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--development", type=Path, required=True)
    prepare.add_argument("--holdout", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    prepare.add_argument("--seed", type=int, default=2028)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--output", type=Path, required=True)
    status = subparsers.add_parser("status")
    status.add_argument("--output", type=Path, required=True)
    prepare_assisted = subparsers.add_parser("prepare-assisted")
    prepare_assisted.add_argument("--output", type=Path, required=True)
    report = subparsers.add_parser("report")
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--report", type=Path, required=True)
    assisted_report = subparsers.add_parser("assisted-report")
    assisted_report.add_argument("--output", type=Path, required=True)
    assisted_report.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare_audit(
            args.development,
            args.holdout,
            args.output,
            rows=args.rows,
            seed=args.seed,
        )
    elif args.command == "validate":
        result = validate_prepared_audit(args.output)
    elif args.command == "status":
        result = audit_status(args.output)
    elif args.command == "prepare-assisted":
        result = prepare_assisted_inputs(args.output)
    elif args.command == "assisted-report":
        result = build_assisted_report(args.output, args.report)
    else:
        result = build_audit_report(args.output, args.report)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
