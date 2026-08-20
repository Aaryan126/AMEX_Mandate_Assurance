from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ml.fusion.policy_selection import policy_metrics, predict_policy_treatment
from ml.tabular.train_catboost import load_rows, validate_feature_dataset


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _counts(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _rate(value: int, total: int) -> float:
    return value / total if total else 0.0


def profile_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reviewed = [
        row
        for row in rows
        if row.get("expected_treatment") in {"APPROVE", "STEP_UP", "HOLD"}
    ]
    if not reviewed:
        raise ValueError("diagnosis requires reviewed treatment labels")
    disabled_threshold = math.nextafter(1.0, math.inf)
    fixed_predictions = [
        predict_policy_treatment(row, 0.0, disabled_threshold) for row in reviewed
    ]
    fixed_metrics = policy_metrics(
        reviewed, [0.0] * len(reviewed), disabled_threshold
    )
    by_attack: dict[str, Any] = {}
    grouped: defaultdict[str, list[tuple[dict[str, Any], str]]] = defaultdict(list)
    for row, prediction in zip(reviewed, fixed_predictions, strict=True):
        grouped[str(row.get("attack_family", "unknown"))].append((row, prediction))
    for attack, values in sorted(grouped.items()):
        attack_rows = [row for row, _ in values]
        by_attack[attack] = {
            "rows": len(values),
            "expected_treatments": _counts(
                [str(row["expected_treatment"]) for row in attack_rows]
            ),
            "fixed_policy_confusion": _counts(
                [
                    f"{row['expected_treatment']}->{prediction}"
                    for row, prediction in values
                ]
            ),
            "adjudication_rate": _rate(
                sum(row.get("label_source") == "llm_adjudicated" for row in attack_rows),
                len(attack_rows),
            ),
        }
    return {
        "rows": len(reviewed),
        "expected_treatments": _counts(
            [str(row["expected_treatment"]) for row in reviewed]
        ),
        "label_sources": _counts(
            [str(row.get("label_source", "unknown")) for row in reviewed]
        ),
        "attack_families": _counts(
            [str(row.get("attack_family", "unknown")) for row in reviewed]
        ),
        "trigger_rates": {
            "critical_hold": _rate(
                sum(bool(row.get("critical_hold_count")) for row in reviewed),
                len(reviewed),
            ),
            "hard_fail": _rate(
                sum(bool(row.get("hard_fail_count")) for row in reviewed),
                len(reviewed),
            ),
            "semantic_override": _rate(
                sum(
                    float(row.get("semantic_contradiction", 0)) >= 0.8
                    or float(row.get("semantic_neutral", 0)) >= 0.6
                    for row in reviewed
                ),
                len(reviewed),
            ),
        },
        "fixed_policy_metrics": fixed_metrics,
        "fixed_policy_confusion": _counts(
            [
                f"{row['expected_treatment']}->{prediction}"
                for row, prediction in zip(
                    reviewed, fixed_predictions, strict=True
                )
            ]
        ),
        "by_attack_family": by_attack,
    }


def source_label_audit(
    source_path: Path, reviewed_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    reviewed_by_id = {str(row["example_id"]): row for row in reviewed_rows}
    source_labels: dict[str, dict[str, Any]] = {}
    with source_path.open() as source:
        for line in source:
            if not line.strip():
                continue
            value = json.loads(line)
            example_id = str(value["identity"]["example_id"])
            if example_id in reviewed_by_id:
                source_labels[example_id] = value["labels"]
    if set(source_labels) != set(reviewed_by_id):
        raise ValueError("source dataset does not cover every reviewed holdout row")

    by_attack: defaultdict[str, list[tuple[str | None, str]]] = defaultdict(list)
    by_source: defaultdict[str, list[tuple[str | None, str]]] = defaultdict(list)
    for example_id, reviewed in reviewed_by_id.items():
        source_label = source_labels[example_id]
        pair = (
            source_label.get("expected_treatment"),
            str(reviewed["expected_treatment"]),
        )
        by_attack[str(reviewed.get("attack_family", "unknown"))].append(pair)
        by_source[str(source_label.get("label_source", "unknown"))].append(pair)

    def summarize(values: list[tuple[str | None, str]]) -> dict[str, Any]:
        comparable = [pair for pair in values if pair[0] is not None]
        return {
            "rows": len(values),
            "comparable_rows": len(comparable),
            "exact_treatment_agreement": _rate(
                sum(source == reviewed for source, reviewed in comparable),
                len(comparable),
            ),
            "treatment_transitions": _counts(
                [f"{source}->{reviewed}" for source, reviewed in comparable]
            ),
        }

    return {
        "source_dataset_sha256": _sha256(source_path),
        "rows": len(reviewed_by_id),
        "by_attack_family": {
            name: summarize(values) for name, values in sorted(by_attack.items())
        },
        "by_original_label_source": {
            name: summarize(values) for name, values in sorted(by_source.items())
        },
    }


def diagnose(
    development_path: Path,
    holdout_path: Path,
    source_path: Path,
    artifact_dir: Path,
    evaluation_report_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    development_rows = load_rows(development_path)
    holdout_rows = load_rows(holdout_path)
    development_manifest = validate_feature_dataset(
        development_path, development_rows
    )
    holdout_manifest = validate_feature_dataset(holdout_path, holdout_rows)
    validation = [
        row
        for row in development_rows
        if row.get("split") == "validation"
        and row.get("expected_treatment") in {"APPROVE", "STEP_UP", "HOLD"}
    ]
    reviewed_holdout = [
        row
        for row in holdout_rows
        if row.get("expected_treatment") in {"APPROVE", "STEP_UP", "HOLD"}
    ]
    artifact_manifest_path = artifact_dir / "fusion-v2.manifest.json"
    artifact_manifest = json.loads(artifact_manifest_path.read_text())
    bundle = json.loads((artifact_dir / artifact_manifest["fusion_artifact"]).read_text())
    evaluation = json.loads(evaluation_report_path.read_text())
    if evaluation.get("status") != "failed_gate":
        raise ValueError("Step 24 diagnosis expects the immutable failed-gate report")
    if evaluation.get("artifact_manifest_sha256") != _sha256(artifact_manifest_path):
        raise ValueError("evaluation report is not bound to the diagnosed artifact")
    if evaluation.get("evaluation_dataset_sha256") != _sha256(holdout_path):
        raise ValueError("evaluation report is not bound to the diagnosed holdout features")

    stack_features = [str(value) for value in artifact_manifest["stack_features"]]
    coefficients = [float(value) for value in bundle["stacker"]["coefficients"]]
    stacker_weights = dict(zip(stack_features, coefficients, strict=True))
    development_profile = profile_rows(validation)
    holdout_profile = profile_rows(reviewed_holdout)
    source_audit = source_label_audit(source_path, reviewed_holdout)

    development_treatments = development_profile["expected_treatments"]
    holdout_treatments = holdout_profile["expected_treatments"]
    report = {
        "schema_version": "step24-failure-diagnosis-v1",
        "status": "diagnosed",
        "scope": "post-gate diagnosis; consumed holdout is analysis-only",
        "inputs": {
            "development_features_sha256": _sha256(development_path),
            "development_feature_manifest_sha256": development_manifest[
                "manifest_sha256"
            ],
            "holdout_features_sha256": _sha256(holdout_path),
            "holdout_feature_manifest_sha256": holdout_manifest["manifest_sha256"],
            "artifact_manifest_sha256": _sha256(artifact_manifest_path),
            "evaluation_report_sha256": _sha256(evaluation_report_path),
        },
        "development_validation": development_profile,
        "consumed_holdout": holdout_profile,
        "label_distribution_shift": {
            "development_hold_rate": _rate(
                development_treatments.get("HOLD", 0), development_profile["rows"]
            ),
            "holdout_hold_rate": _rate(
                holdout_treatments.get("HOLD", 0), holdout_profile["rows"]
            ),
            "development_approve_rate": _rate(
                development_treatments.get("APPROVE", 0),
                development_profile["rows"],
            ),
            "holdout_approve_rate": _rate(
                holdout_treatments.get("APPROVE", 0), holdout_profile["rows"]
            ),
        },
        "source_label_audit": source_audit,
        "fusion_audit": {
            "stacker_weights": stacker_weights,
            "negative_semantic_weights": {
                name: value
                for name, value in stacker_weights.items()
                if name in {"semantic_contradiction", "semantic_neutral"} and value < 0
            },
            "final_pr_auc": evaluation["metrics"]["pr_auc"],
            "pr_auc_delta_vs_catboost": evaluation["comparison"][
                "full_minus_catboost_pr_auc"
            ],
            "fixed_fpr_recall_delta_vs_catboost": evaluation["comparison"][
                "full_minus_catboost_fixed_fpr_recall"
            ],
        },
        "root_causes": [
            {
                "id": "label-policy-contract",
                "severity": "critical",
                "finding": "Expected treatments mix weak, deterministic, and LLM judgments that apply materially different HOLD/STEP_UP semantics.",
            },
            {
                "id": "llm-state-arithmetic",
                "severity": "critical",
                "finding": "Reviewers frequently ignored prior fulfilled amount and fulfillment count on deterministic cumulative-breach examples.",
            },
            {
                "id": "unrelated-item-semantics",
                "severity": "critical",
                "finding": "The generator labels an unrelated add-on as HOLD, while the reviewer rubric says semantic mismatch alone is STEP_UP and the rules cannot deterministically identify an unlisted unrelated item.",
            },
            {
                "id": "offline-runtime-rule-duplication",
                "severity": "high",
                "finding": "Offline features reimplement only a subset of live deterministic rules, allowing rule and feature semantics to drift.",
            },
            {
                "id": "fusion-non-degradation",
                "severity": "high",
                "finding": "The stacker assigns negative semantic weights and materially degrades both PR-AUC and fixed-FPR recall versus CatBoost alone.",
            },
            {
                "id": "split-role-overuse",
                "severity": "high",
                "finding": "The same validation split supports CatBoost early stopping, policy-threshold selection, and candidate selection, producing optimistic development estimates.",
            },
            {
                "id": "target-gate-mismatch",
                "severity": "medium",
                "finding": "Training targets policy intervention, while several ranking gates use binary deviation labels and omit ambiguous STEP_UP rows.",
            },
        ],
        "remediation_order": [
            "Freeze a versioned treatment contract before changing data or thresholds.",
            "Human-audit a stratified sample and separate deterministic rule truth from semantic judgment.",
            "Make offline features consume the same rule results/codes as the live API.",
            "Repair counterfactual invariants so every generated example has declared intended triggers.",
            "Build dataset v3 with non-overloaded train, calibration, policy-tuning, and candidate-selection partitions.",
            "Establish CatBoost-only and semantic-only baselines before allowing a fusion candidate.",
            "Require nested out-of-fold fusion and non-degradation tests if fusion is retained.",
            "Freeze and review a new group/source-disjoint holdout only after all development decisions are locked.",
        ],
        "prohibited_shortcuts": [
            "Do not lower the promotion criteria based on the consumed holdout.",
            "Do not tune thresholds, coefficients, or labels against the consumed holdout.",
            "Do not reuse the consumed holdout as an independent final gate.",
            "Do not promote the current artifact.",
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f"{output_path.name}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    temporary.replace(output_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--development",
        type=Path,
        default=Path("ml/data/generated/fast-track/features-v2.jsonl"),
    )
    parser.add_argument(
        "--holdout",
        type=Path,
        default=Path(
            "ml/data/generated/fast-track/replacement-holdout/features-v2.jsonl"
        ),
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("ml/data/generated/option1-en/ace-esci-en-hybrid.jsonl"),
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path("artifacts/models/fast-track-remediation-v3/with-semantic"),
    )
    parser.add_argument(
        "--evaluation-report",
        type=Path,
        default=Path("artifacts/reports/step23-replacement-holdout-evaluation.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/reports/step24-failure-diagnosis.json"),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            diagnose(
                args.development,
                args.holdout,
                args.source,
                args.artifacts,
                args.evaluation_report,
                args.output,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
