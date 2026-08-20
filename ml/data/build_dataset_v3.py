from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.commercial_rules import evaluate_commercial_rules
from app.treatment_contract import POLICY_VERSION, treatment_for_signals

from ml.data.schema import (
    AceDatasetExample,
    DatasetLabels,
    DatasetSplit,
    DeviationLabel,
    ExpectedTreatment,
    SemanticLabel,
)

DATASET_VERSION = "ace-development-v3"
SPLIT_VERSION = "single-purpose-splits-v1"
BUILD_SEED = 2029
ROLE_TARGETS = {
    "train_fit": 4_000,
    "calibration": 1_000,
    "policy_tuning": 1_000,
    "candidate_selection": 1_000,
}
MAX_ROLE_DISTRIBUTION_SHIFT = 0.15


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: str) -> str:
    return hashlib.sha256(f"{BUILD_SEED}:{value}".encode()).hexdigest()


def _read(path: Path) -> list[AceDatasetExample]:
    with path.open() as source:
        return [
            AceDatasetExample.model_validate_json(line)
            for line in source
            if line.strip()
        ]


def _attack(value: AceDatasetExample) -> str:
    transformation = value.provenance.transformation
    return transformation if transformation and transformation != "none" else "none"


def _audited_labels(
    reviewed_path: Path, ledger_path: Path
) -> dict[tuple[str, str], DatasetLabels]:
    reviewed = {value.identity.example_id: value.labels for value in _read(reviewed_path)}
    output: dict[tuple[str, str], DatasetLabels] = {}
    with ledger_path.open() as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["cohort"] != "development":
                continue
            labels = reviewed.get(row["example_id"])
            if labels is not None:
                output[(row["group_id"], row["attack_family"])] = labels
    return output


def _semantic_outcome(labels: DatasetLabels) -> SemanticLabel | None:
    values = {value.label for value in labels.semantic}
    if SemanticLabel.CONTRADICTION in values:
        return SemanticLabel.CONTRADICTION
    if SemanticLabel.NEUTRAL in values:
        return SemanticLabel.NEUTRAL
    if SemanticLabel.ENTAILMENT in values:
        return SemanticLabel.ENTAILMENT
    return None


def _v3_labels(
    value: AceDatasetExample,
    audited: DatasetLabels | None,
) -> DatasetLabels:
    source = audited or value.labels
    semantic = _semantic_outcome(source)
    signals = evaluate_commercial_rules(value.mandate, value.state, value.cart)
    failed_codes = sorted(
        {
            str(signal.reason_code)
            for signal in signals
            if signal.status == "FAIL" and signal.reason_code is not None
        }
    )
    has_unclassified = any(
        signal.status == "FAIL" and signal.reason_code is None for signal in signals
    )
    has_not_evaluable = any(signal.status == "NOT_EVALUABLE" for signal in signals)
    deterministic = treatment_for_signals(
        failed_codes,
        has_unclassified_failure=has_unclassified,
        has_not_evaluable=has_not_evaluable,
    )
    violation_types = set(failed_codes)
    semantic_escalation = semantic in {
        SemanticLabel.CONTRADICTION,
        SemanticLabel.NEUTRAL,
    }
    attack = _attack(value)
    if attack == "missing_required_evidence":
        violation_types.add("REQUIRED_ATTRIBUTE_EVIDENCE_MISSING")
        semantic_escalation = True
    elif attack == "unrelated_add_on":
        violation_types.add("SEMANTIC_UNRELATED_ITEM")
        semantic_escalation = True
    elif semantic == SemanticLabel.CONTRADICTION:
        violation_types.add("REQUIRED_ATTRIBUTE_CONTRADICTED")
    treatment = ExpectedTreatment(deterministic.value)
    if treatment == ExpectedTreatment.APPROVE and semantic_escalation:
        treatment = ExpectedTreatment.STEP_UP
    if audited is not None:
        label_source = "llm_assisted_v3"
        confidence = audited.reviewer_confidence
    elif deterministic != "APPROVE" or attack != "none":
        label_source = "deterministic_policy_v3"
        confidence = 1.0
    else:
        label_source = "weak_policy_v3"
        confidence = source.reviewer_confidence
    deviation = source.deviation
    if deviation is None:
        deviation = (
            DeviationLabel.MATCH
            if treatment == ExpectedTreatment.APPROVE
            else DeviationLabel.AMBIGUOUS
        )
    return DatasetLabels(
        deviation=deviation,
        semantic=source.semantic,
        violation_types=sorted(violation_types),
        expected_treatment=treatment,
        label_source=label_source,
        reviewer_confidence=confidence,
        deterministic_outcome=failed_codes,
        semantic_outcome=semantic,
        policy_intervention_target=treatment,
        binary_deviation=deviation,
    )


def _relationship_keys(values: list[AceDatasetExample]) -> dict[str, set[str]]:
    return {
        "example": {value.identity.example_id for value in values},
        "group": {value.identity.group_id for value in values},
        "parent": {
            value.identity.parent_example_id
            for value in values
            if value.identity.parent_example_id
        },
        "source": {value.provenance.source_record_id for value in values},
    }


def _select_groups(
    values: list[AceDatasetExample], audited_keys: set[tuple[str, str]]
) -> dict[str, str]:
    by_group: dict[str, list[AceDatasetExample]] = defaultdict(list)
    for value in values:
        by_group[value.identity.group_id].append(value)
    assigned: dict[str, str] = {}
    counts: Counter[str] = Counter()

    audited_groups = sorted(
        {
            group_id
            for group_id, attack in audited_keys
            if any(_attack(value) == attack for value in by_group.get(group_id, []))
        },
        key=_hash,
    )
    for group_id in audited_groups:
        size = len(by_group[group_id])
        if counts["candidate_selection"] + size <= ROLE_TARGETS["candidate_selection"]:
            assigned[group_id] = "candidate_selection"
            counts["candidate_selection"] += size

    groups = sorted(by_group, key=_hash)
    for role in ("candidate_selection", "calibration", "policy_tuning", "train_fit"):
        remaining = ROLE_TARGETS[role] - counts[role]
        while remaining:
            candidate = next(
                (
                    group_id
                    for group_id in groups
                    if group_id not in assigned and len(by_group[group_id]) <= remaining
                ),
                None,
            )
            if candidate is None:
                raise ValueError(f"group boundaries prevent exact {role} target")
            assigned[candidate] = role
            size = len(by_group[candidate])
            counts[role] += size
            remaining -= size
    return assigned


def _assert_isolation(values: list[AceDatasetExample]) -> None:
    roles: dict[str, dict[str, set[str]]] = {}
    for role in ROLE_TARGETS:
        role_values = [value for value in values if value.split.name == role]
        roles[role] = _relationship_keys(role_values)
    role_names = list(ROLE_TARGETS)
    for index, left in enumerate(role_names):
        for right in role_names[index + 1 :]:
            for key in ("example", "group", "parent", "source"):
                overlap = roles[left][key].intersection(roles[right][key])
                if overlap:
                    raise ValueError(f"{key} leakage between {left} and {right}")
            if roles[left]["parent"].intersection(roles[right]["example"]) or roles[
                right
            ]["parent"].intersection(roles[left]["example"]):
                raise ValueError(f"parent/example leakage between {left} and {right}")


def _assert_label_contract(values: list[AceDatasetExample]) -> None:
    for value in values:
        signals = evaluate_commercial_rules(value.mandate, value.state, value.cart)
        codes = sorted(
            {
                str(signal.reason_code)
                for signal in signals
                if signal.status == "FAIL" and signal.reason_code is not None
            }
        )
        if value.labels.deterministic_outcome != codes:
            raise ValueError("dataset v3 deterministic outcome drift")
        deterministic = treatment_for_signals(
            codes,
            has_unclassified_failure=any(
                signal.status == "FAIL" and signal.reason_code is None
                for signal in signals
            ),
            has_not_evaluable=any(
                signal.status == "NOT_EVALUABLE" for signal in signals
            ),
        )
        expected = ExpectedTreatment(deterministic.value)
        if expected == ExpectedTreatment.APPROVE and (
            value.labels.semantic_outcome
            in {SemanticLabel.CONTRADICTION, SemanticLabel.NEUTRAL}
            or "SEMANTIC_UNRELATED_ITEM" in value.labels.violation_types
            or "REQUIRED_ATTRIBUTE_EVIDENCE_MISSING" in value.labels.violation_types
        ):
            expected = ExpectedTreatment.STEP_UP
        if (
            value.labels.expected_treatment != expected
            or value.labels.policy_intervention_target != expected
        ):
            raise ValueError("dataset v3 treatment contract drift")


def _distribution_report(values: list[AceDatasetExample]) -> dict[str, Any]:
    dimensions = {
        "treatment": lambda value: str(value.labels.policy_intervention_target),
        "attack_family": _attack,
        "evidence_origin": lambda value: str(value.provenance.evidence_origin),
    }
    report: dict[str, Any] = {}
    max_shift = 0.0
    for name, getter in dimensions.items():
        overall = Counter(getter(value) for value in values)
        categories = sorted(overall)
        roles: dict[str, Any] = {}
        for role in ROLE_TARGETS:
            role_values = [value for value in values if value.split.name == role]
            counts = Counter(getter(value) for value in role_values)
            tvd = sum(
                abs(counts[category] / len(role_values) - overall[category] / len(values))
                for category in categories
            ) / 2
            max_shift = max(max_shift, tvd)
            roles[role] = {
                "counts": dict(sorted(counts.items())),
                "total_variation_distance": round(tvd, 6),
            }
        report[name] = roles
    if max_shift > MAX_ROLE_DISTRIBUTION_SHIFT:
        raise ValueError(
            f"role distribution shift {max_shift:.4f} exceeds "
            f"{MAX_ROLE_DISTRIBUTION_SHIFT:.4f}"
        )
    return {"dimensions": report, "max_total_variation_distance": round(max_shift, 6)}


def build(
    source_path: Path,
    consumed_holdout_path: Path,
    audit_reviewed_path: Path,
    audit_ledger_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source = _read(source_path)
    consumed = _read(consumed_holdout_path)
    excluded = _relationship_keys(consumed)
    candidates = [
        value
        for value in source
        if value.split.name != "golden"
        and value.labels.label_source != "unreviewed"
        and value.identity.example_id not in excluded["example"]
        and value.identity.group_id not in excluded["group"]
        and value.provenance.source_record_id not in excluded["source"]
        and (value.identity.parent_example_id or "") not in excluded["example"]
    ]
    audited = _audited_labels(audit_reviewed_path, audit_ledger_path)
    assignments = _select_groups(candidates, set(audited))
    selected: list[AceDatasetExample] = []
    audit_matches = 0
    for value in candidates:
        role = assignments.get(value.identity.group_id)
        if role is None:
            continue
        audit_label = audited.get((value.identity.group_id, _attack(value)))
        audit_matches += int(audit_label is not None)
        selected.append(
            value.model_copy(
                deep=True,
                update={
                    "labels": _v3_labels(value, audit_label),
                    "split": DatasetSplit(
                        name=role,
                        grouping_keys=[
                            value.identity.group_id,
                            value.provenance.source_record_id,
                        ],
                    ),
                },
            )
        )
    selected.sort(key=lambda value: value.identity.example_id)
    _assert_isolation(selected)
    _assert_label_contract(selected)
    if len(selected) != sum(ROLE_TARGETS.values()):
        raise ValueError("dataset v3 row count does not match declared roles")
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "ace-development-v3.jsonl"
    dataset_path.write_text(
        "".join(value.model_dump_json() + "\n" for value in selected)
    )
    manifest = {
        "dataset_version": DATASET_VERSION,
        "schema_version": "2.0",
        "split_version": SPLIT_VERSION,
        "policy_version": POLICY_VERSION,
        "seed": BUILD_SEED,
        "row_count": len(selected),
        "roles": dict(sorted(Counter(value.split.name for value in selected).items())),
        "label_sources": dict(
            sorted(Counter(value.labels.label_source for value in selected).items())
        ),
        "treatments": dict(
            sorted(
                Counter(
                    str(value.labels.policy_intervention_target) for value in selected
                ).items()
            )
        ),
        "attack_families": dict(
            sorted(Counter(_attack(value) for value in selected).items())
        ),
        "audited_matches": audit_matches,
        "role_distribution_tolerance": MAX_ROLE_DISTRIBUTION_SHIFT,
        "role_distribution": _distribution_report(selected),
        "consumed_holdout_excluded": str(consumed_holdout_path),
        "source_sha256": _sha256(source_path),
        "consumed_holdout_sha256": _sha256(consumed_holdout_path),
        "audit_reviewed_sha256": _sha256(audit_reviewed_path),
        "audit_ledger_sha256": _sha256(audit_ledger_path),
        "dataset_sha256": _sha256(dataset_path),
        "production_claim_eligible": False,
        "limitation": "semantic audit supervision is LLM-assisted, not human",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--consumed-holdout", type=Path, required=True)
    parser.add_argument("--audit-reviewed", type=Path, required=True)
    parser.add_argument("--audit-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                args.source,
                args.consumed_holdout,
                args.audit_reviewed,
                args.audit_ledger,
                args.output,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
