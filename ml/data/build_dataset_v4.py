from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from ml.data.build_dataset_v3 import (
    _assert_isolation,
    _assert_label_contract,
    _attack,
    _relationship_keys,
    _v3_labels,
)
from ml.data.schema import (
    AceDatasetExample,
    DatasetLabels,
    DatasetSplit,
    SemanticLabel,
)
from ml.features.schema import feature_vector

DATASET_VERSION = "ace-development-v4-data-policy"
BUILD_SEED = 2030
ROLE_TARGETS = {
    "train_fit": 10_000,
    "calibration": 1_500,
    "policy_tuning": 1_500,
    "candidate_selection": 1_500,
}
REVIEW_TARGETS = {
    "train_fit": 200,
    "calibration": 100,
    "policy_tuning": 100,
    "candidate_core_semantic": 500,
    "candidate_challenge": 300,
}
DETERMINISTIC_TARGETS = {
    "train_fit": 3_025,
    "calibration": 1_400,
    "policy_tuning": 1_400,
    "candidate_selection": 700,
}
WEAK_TRAIN_TARGET = 6_775
TARGET_REAL_PUBLIC = 7_975


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable(value: str, namespace: str = "") -> str:
    return hashlib.sha256(f"{BUILD_SEED}:{namespace}:{value}".encode()).hexdigest()


def _read(path: Path) -> list[AceDatasetExample]:
    with path.open() as source:
        return [
            AceDatasetExample.model_validate_json(line)
            for line in source
            if line.strip()
        ]


def _manifest_path(path: Path) -> Path:
    return path.with_suffix(".manifest.json")


def _refuse_existing(path: Path) -> None:
    if path.exists() or _manifest_path(path).exists():
        raise FileExistsError(f"refusing to overwrite immutable output: {path}")


def freeze_pool(
    source_path: Path, exclusion_paths: list[Path], output_path: Path
) -> dict[str, Any]:
    _refuse_existing(output_path)
    source = _read(source_path)
    exclusions: list[AceDatasetExample] = []
    for path in exclusion_paths:
        exclusions.extend(_read(path))
    excluded = _relationship_keys(exclusions)
    available = [
        value
        for value in source
        if value.split.name != "golden"
        and value.labels.label_source != "unreviewed"
        and value.identity.example_id not in excluded["example"]
        and value.identity.group_id not in excluded["group"]
        and value.provenance.source_record_id not in excluded["source"]
        and (value.identity.parent_example_id or "") not in excluded["example"]
    ]
    if len(available) < sum(ROLE_TARGETS.values()):
        raise ValueError("unused relationship pool is too small for development-v4")
    available.sort(key=lambda value: value.identity.example_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(value.model_dump_json() + "\n" for value in available)
    )
    manifest = {
        "dataset_version": "ace-development-v4-unused-pool",
        "row_count": len(available),
        "group_count": len({value.identity.group_id for value in available}),
        "evidence_origins": dict(
            sorted(Counter(value.provenance.evidence_origin for value in available).items())
        ),
        "transformations": dict(sorted(Counter(_attack(value) for value in available).items())),
        "source_path": str(source_path),
        "source_sha256": _sha256(source_path),
        "exclusions": [
            {"path": str(path), "sha256": _sha256(path)} for path in exclusion_paths
        ],
        "consumed_relationship_hashes": {
            key: hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()
            for key, values in excluded.items()
        },
        "dataset_sha256": _sha256(output_path),
        "production_claim_eligible": False,
    }
    _manifest_path(output_path).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def _load_features(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open() as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            example_id = str(row["example_id"])
            if example_id in rows:
                raise ValueError("pool features contain duplicate example IDs")
            rows[example_id] = row
    return rows


def _model_probabilities(
    features: dict[str, dict[str, Any]], model_path: Path
) -> dict[str, float]:
    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:
        raise RuntimeError("Install services/api[ml] before v4 selection") from exc
    model = CatBoostClassifier()
    model.load_model(model_path)
    ids = sorted(features)
    probabilities = model.predict_proba(
        [feature_vector(features[example_id]) for example_id in ids]
    )[:, 1]
    return {
        example_id: float(probability)
        for example_id, probability in zip(ids, probabilities, strict=True)
    }


def _semantic_entropy(row: dict[str, Any]) -> float:
    contradiction = float(row.get("semantic_contradiction", 0))
    neutral = float(row.get("semantic_neutral", 0))
    entailment = max(0.0, 1.0 - contradiction - neutral)
    values = [contradiction, neutral, entailment]
    return -sum(value * math.log(value) for value in values if value > 0) / math.log(3)


def _hard_score(row: dict[str, Any], probability: float, threshold: float) -> float:
    expected_intervention = row.get("expected_treatment") != "APPROVE"
    predicted_intervention = probability >= threshold
    disagreement = float(expected_intervention != predicted_intervention)
    scale = max(threshold, 1.0 - threshold)
    uncertainty = 1.0 - min(abs(probability - threshold) / scale, 1.0)
    semantic_risk = max(
        float(row.get("semantic_contradiction", 0)),
        float(row.get("semantic_neutral", 0)),
    )
    return 2.0 * disagreement + uncertainty + _semantic_entropy(row) + semantic_risk


def _diverse_hard_selection(
    candidates: list[AceDatasetExample],
    feature_rows: dict[str, dict[str, Any]],
    probabilities: dict[str, float],
    threshold: float,
    count: int,
    excluded_groups: set[str],
) -> list[AceDatasetExample]:
    ranked = sorted(
        (
            value
            for value in candidates
            if value.identity.group_id not in excluded_groups
        ),
        key=lambda value: (
            -_hard_score(
                feature_rows[value.identity.example_id],
                probabilities[value.identity.example_id],
                threshold,
            ),
            _stable(value.identity.example_id, "hard"),
        ),
    )
    selected: list[AceDatasetExample] = []
    seen_groups = set(excluded_groups)
    seen_fingerprints: Counter[str] = Counter()
    for enforce_fingerprint_cap in (True, False):
        for value in ranked:
            group = value.identity.group_id
            text = " ".join(
                item.description.lower() for item in value.cart.line_items
            )
            tokens = sorted(set(text.split()))[:12]
            fingerprint = hashlib.sha256(" ".join(tokens).encode()).hexdigest()[:10]
            if group in seen_groups or (
                enforce_fingerprint_cap and seen_fingerprints[fingerprint] >= 2
            ):
                continue
            selected.append(value)
            seen_groups.add(group)
            seen_fingerprints[fingerprint] += 1
            if len(selected) == count:
                return selected
    raise ValueError(f"could select only {len(selected)} of {count} hard examples")


def select_review_queue(
    pool_path: Path,
    features_path: Path,
    model_path: Path,
    model_manifest_path: Path,
    baseline_report_path: Path,
    output_path: Path,
    ledger_path: Path,
) -> dict[str, Any]:
    _refuse_existing(output_path)
    if ledger_path.exists():
        raise FileExistsError(f"refusing to overwrite review ledger: {ledger_path}")
    pool = _read(pool_path)
    features = _load_features(features_path)
    if set(features) != {value.identity.example_id for value in pool}:
        raise ValueError("pool features do not exactly cover the frozen pool")
    model_manifest = json.loads(model_manifest_path.read_text())
    if model_manifest.get("artifact_sha256") != _sha256(model_path):
        raise ValueError("v3 model does not match its manifest")
    baseline = json.loads(baseline_report_path.read_text())
    threshold = float(
        baseline["candidates"]["calibrated_catboost"]["threshold_selection"][
            "threshold"
        ]
    )
    probabilities = _model_probabilities(features, model_path)
    semantic = [
        value
        for value in pool
        if value.provenance.evidence_origin == "real_public"
        and _attack(value) == "none"
    ]
    if len(semantic) < sum(REVIEW_TARGETS.values()):
        raise ValueError("unused semantic pool is too small for the review design")
    representative = sorted(
        semantic,
        key=lambda value: _stable(value.identity.example_id, "representative"),
    )[: REVIEW_TARGETS["candidate_core_semantic"]]
    selected_groups = {value.identity.group_id for value in representative}
    hard = _diverse_hard_selection(
        semantic,
        features,
        probabilities,
        threshold,
        sum(REVIEW_TARGETS.values()) - len(representative),
        selected_groups,
    )
    assignments: list[tuple[AceDatasetExample, str, str]] = []
    assignments.extend(
        (value, "candidate_selection", "candidate_core_semantic")
        for value in representative
    )
    offsets = [
        (
            "candidate_selection",
            "candidate_challenge",
            REVIEW_TARGETS["candidate_challenge"],
        ),
        ("train_fit", "development_hard", REVIEW_TARGETS["train_fit"]),
        ("calibration", "development_hard", REVIEW_TARGETS["calibration"]),
        ("policy_tuning", "development_hard", REVIEW_TARGETS["policy_tuning"]),
    ]
    index = 0
    for role, cohort, size in offsets:
        assignments.extend((value, role, cohort) for value in hard[index : index + size])
        index += size
    assignments.sort(key=lambda item: item[0].identity.example_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x") as output, ledger_path.open("x") as ledger:
        for value, role, cohort in assignments:
            queue_value = value.model_copy(
                deep=True,
                update={
                    "labels": DatasetLabels(label_source="unreviewed"),
                    "split": DatasetSplit(
                        name=role,
                        grouping_keys=[
                            value.identity.group_id,
                            value.provenance.source_record_id,
                        ],
                    ),
                },
            )
            output.write(queue_value.model_dump_json() + "\n")
            feature_row = features[value.identity.example_id]
            ledger.write(
                json.dumps(
                    {
                        "example_id": value.identity.example_id,
                        "group_id": value.identity.group_id,
                        "source_record_id": value.provenance.source_record_id,
                        "role": role,
                        "cohort": cohort,
                        "v3_probability": probabilities[value.identity.example_id],
                        "v3_threshold": threshold,
                        "semantic_contradiction": feature_row["semantic_contradiction"],
                        "semantic_neutral": feature_row["semantic_neutral"],
                        "selection_score": _hard_score(
                            feature_row,
                            probabilities[value.identity.example_id],
                            threshold,
                        ),
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    manifest = {
        "selection_version": "missed-intervention-active-review-v1",
        "selection_method": "representative-plus-uncertainty-disagreement-diversity",
        "rows": len(assignments),
        "roles": dict(sorted(Counter(role for _, role, _ in assignments).items())),
        "cohorts": dict(sorted(Counter(cohort for _, _, cohort in assignments).items())),
        "pool_sha256": _sha256(pool_path),
        "features_sha256": _sha256(features_path),
        "model_sha256": _sha256(model_path),
        "baseline_report_sha256": _sha256(baseline_report_path),
        "v3_threshold": threshold,
        "review_queue_sha256": _sha256(output_path),
        "selection_ledger_sha256": _sha256(ledger_path),
        "production_claim_eligible": False,
    }
    _manifest_path(output_path).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def _review_labels(value: AceDatasetExample) -> DatasetLabels:
    source = value.labels
    semantic_values = {item.label for item in source.semantic}
    semantic = (
        SemanticLabel.CONTRADICTION
        if SemanticLabel.CONTRADICTION in semantic_values
        else SemanticLabel.NEUTRAL
        if SemanticLabel.NEUTRAL in semantic_values
        else SemanticLabel.ENTAILMENT
        if SemanticLabel.ENTAILMENT in semantic_values
        else None
    )
    if source.expected_treatment is None or source.deviation is None:
        raise ValueError("reviewed v4 row lacks resolved targets")
    return DatasetLabels(
        deviation=source.deviation,
        semantic=source.semantic,
        violation_types=source.violation_types,
        expected_treatment=source.expected_treatment,
        label_source="llm_assisted_v4",
        reviewer_confidence=source.reviewer_confidence,
        deterministic_outcome=[],
        semantic_outcome=semantic,
        policy_intervention_target=source.expected_treatment,
        binary_deviation=source.deviation,
    )


def _choose(
    candidates: Iterable[AceDatasetExample],
    count: int,
    namespace: str,
    blocked: dict[str, set[str]],
) -> list[AceDatasetExample]:
    selected: list[AceDatasetExample] = []
    for value in sorted(
        candidates,
        key=lambda item: _stable(item.identity.example_id, namespace),
    ):
        identity = value.identity
        source_id = value.provenance.source_record_id
        parent_id = identity.parent_example_id or ""
        if (
            identity.example_id in blocked["example"]
            or identity.group_id in blocked["group"]
            or source_id in blocked["source"]
            or parent_id in blocked["example"]
            or identity.example_id in blocked["parent"]
        ):
            continue
        selected.append(value)
        blocked["example"].add(identity.example_id)
        blocked["group"].add(identity.group_id)
        blocked["source"].add(source_id)
        if parent_id:
            blocked["parent"].add(parent_id)
        if len(selected) == count:
            return selected
    raise ValueError(f"could select only {len(selected)} of {count} rows for {namespace}")


def build_development_v4(
    pool_path: Path,
    reviewed_path: Path,
    selection_ledger_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite development-v4: {output_dir}")
    pool = _read(pool_path)
    reviewed = {value.identity.example_id: value for value in _read(reviewed_path)}
    ledger_rows = [
        json.loads(line)
        for line in selection_ledger_path.read_text().splitlines()
        if line.strip()
    ]
    assignments = {str(row["example_id"]): str(row["role"]) for row in ledger_rows}
    if set(reviewed) != set(assignments) or len(reviewed) != sum(REVIEW_TARGETS.values()):
        raise ValueError("reviewed rows do not exactly cover the frozen v4 review queue")
    selected: list[AceDatasetExample] = []
    blocked = {key: set() for key in ("example", "group", "source", "parent")}
    for example_id in sorted(reviewed):
        value = reviewed[example_id]
        role = assignments[example_id]
        keys = _relationship_keys([value])
        if any(blocked[key].intersection(values) for key, values in keys.items()):
            raise ValueError("review queue contains cross-role relationship leakage")
        for key, values in keys.items():
            blocked[key].update(values)
        selected.append(
            value.model_copy(
                deep=True,
                update={
                    "labels": _review_labels(value),
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
    deterministic = [
        value
        for value in pool
        if value.labels.label_source == "deterministic_counterfactual"
    ]
    weak = [
        value
        for value in pool
        if value.provenance.evidence_origin == "real_public"
        and value.labels.label_source == "weak_esci_mapping"
    ]
    for role, target in DETERMINISTIC_TARGETS.items():
        for value in _choose(deterministic, target, f"{role}:deterministic", blocked):
            labels = _v3_labels(value, None).model_copy(
                update={"label_source": "deterministic_policy_v4"}
            )
            selected.append(
                value.model_copy(
                    deep=True,
                    update={
                        "labels": labels,
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
    for value in _choose(weak, WEAK_TRAIN_TARGET, "train_fit:weak", blocked):
        labels = _v3_labels(value, None).model_copy(
            update={"label_source": "weak_policy_v4"}
        )
        selected.append(
            value.model_copy(
                deep=True,
                update={
                    "labels": labels,
                    "split": DatasetSplit(
                        name="train_fit",
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
    _assert_label_contract(
        [value for value in selected if value.labels.label_source != "llm_assisted_v4"]
    )
    roles = Counter(value.split.name for value in selected)
    if roles != Counter(ROLE_TARGETS):
        raise ValueError(f"development-v4 role mismatch: {dict(roles)}")
    real_public = sum(
        value.provenance.evidence_origin == "real_public" for value in selected
    )
    if real_public != TARGET_REAL_PUBLIC:
        raise ValueError("development-v4 evidence-origin target drift")
    candidate = [
        value for value in selected if value.split.name == "candidate_selection"
    ]
    if any(value.labels.label_source == "weak_policy_v4" for value in candidate):
        raise ValueError("weak labels are forbidden from candidate selection")
    output_dir.mkdir(parents=True, exist_ok=False)
    dataset_path = output_dir / "ace-development-v4.jsonl"
    dataset_path.write_text(
        "".join(value.model_dump_json() + "\n" for value in selected)
    )
    manifest = {
        "dataset_version": DATASET_VERSION,
        "schema_version": "2.0",
        "split_version": "single-purpose-splits-v2",
        "seed": BUILD_SEED,
        "row_count": len(selected),
        "roles": dict(sorted(roles.items())),
        "label_sources": dict(
            sorted(Counter(value.labels.label_source for value in selected).items())
        ),
        "treatments": dict(
            sorted(Counter(str(value.labels.expected_treatment) for value in selected).items())
        ),
        "attack_families": dict(sorted(Counter(_attack(value) for value in selected).items())),
        "evidence_origins": dict(
            sorted(Counter(value.provenance.evidence_origin for value in selected).items())
        ),
        "review_cohorts": dict(
            sorted(Counter(str(row["cohort"]) for row in ledger_rows).items())
        ),
        "pool_sha256": _sha256(pool_path),
        "reviewed_sha256": _sha256(reviewed_path),
        "selection_ledger_sha256": _sha256(selection_ledger_path),
        "consumed_relationship_hashes": {
            key: hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()
            for key, values in blocked.items()
        },
        "dataset_sha256": _sha256(dataset_path),
        "production_claim_eligible": False,
        "limitation": "semantic supervision is LLM-assisted, not human",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze-pool")
    freeze.add_argument("--source", type=Path, required=True)
    freeze.add_argument("--exclude", type=Path, action="append", required=True)
    freeze.add_argument("--output", type=Path, required=True)
    select = subparsers.add_parser("select-review")
    select.add_argument("--pool", type=Path, required=True)
    select.add_argument("--features", type=Path, required=True)
    select.add_argument("--model", type=Path, required=True)
    select.add_argument("--model-manifest", type=Path, required=True)
    select.add_argument("--baseline-report", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    select.add_argument("--ledger", type=Path, required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--pool", type=Path, required=True)
    build.add_argument("--reviewed", type=Path, required=True)
    build.add_argument("--selection-ledger", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "freeze-pool":
        result = freeze_pool(args.source, args.exclude, args.output)
    elif args.command == "select-review":
        result = select_review_queue(
            args.pool,
            args.features,
            args.model,
            args.model_manifest,
            args.baseline_report,
            args.output,
            args.ledger,
        )
    else:
        result = build_development_v4(
            args.pool, args.reviewed, args.selection_ledger, args.output
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
