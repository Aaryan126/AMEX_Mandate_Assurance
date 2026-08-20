from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from joblib import load

from ml.data.build_dataset_v3 import _attack, _relationship_keys
from ml.data.build_dataset_v4 import _load_features, _read, _semantic_entropy, _sha256
from ml.data.schema import AceDatasetExample, DatasetLabels, DatasetSplit
from ml.features.schema import feature_vector

SELECTION_VERSION = "missed-intervention-semantic-review-v2"
BUILD_SEED = 2031
ROLE_STRATUM_TARGETS: dict[str, dict[str, int]] = {
    "train_fit": {"low": 245, "boundary": 210, "high": 245},
    "calibration": {"low": 70, "boundary": 60, "high": 70},
    "policy_tuning": {"low": 70, "boundary": 60, "high": 70},
    "candidate_selection": {"low": 105, "boundary": 90, "high": 105},
}
CHALLENGE_TARGET = 100
STRATUM_FRACTIONS = {"low": 0.35, "boundary": 0.30, "high": 0.35}


def _stable(value: str, namespace: str = "") -> str:
    return hashlib.sha256(f"{BUILD_SEED}:{namespace}:{value}".encode()).hexdigest()


def _manifest_path(path: Path) -> Path:
    return path.with_suffix(".manifest.json")


def _refuse_existing(*paths: Path) -> None:
    for path in paths:
        if path.exists() or _manifest_path(path).exists():
            raise FileExistsError(f"refusing to overwrite immutable output: {path}")


def freeze_unused_pool(
    stage_a_pool_path: Path,
    stage_a_dataset_path: Path,
    stage_a_features_path: Path,
    output_pool_path: Path,
    output_features_path: Path,
) -> dict[str, Any]:
    """Freeze relationships not consumed by Stage A and their existing v2 features."""
    _refuse_existing(output_pool_path, output_features_path)
    pool = _read(stage_a_pool_path)
    consumed = _read(stage_a_dataset_path)
    excluded = _relationship_keys(consumed)
    available = [
        value
        for value in pool
        if value.identity.example_id not in excluded["example"]
        and value.identity.group_id not in excluded["group"]
        and value.provenance.source_record_id not in excluded["source"]
        and (value.identity.parent_example_id or "") not in excluded["example"]
    ]
    features = _load_features(stage_a_features_path)
    available_ids = {value.identity.example_id for value in available}
    if not available_ids.issubset(features):
        raise ValueError("Stage A features do not cover the Stage B pool")
    if len(available) < sum(
        sum(strata.values()) for strata in ROLE_STRATUM_TARGETS.values()
    ) + CHALLENGE_TARGET:
        raise ValueError("unused relationship pool is too small for Stage B")

    available.sort(key=lambda value: value.identity.example_id)
    output_pool_path.parent.mkdir(parents=True, exist_ok=True)
    output_features_path.parent.mkdir(parents=True, exist_ok=True)
    with output_pool_path.open("x") as pool_output:
        for value in available:
            pool_output.write(value.model_dump_json() + "\n")
    with output_features_path.open("x") as feature_output:
        for example_id in sorted(available_ids):
            feature_output.write(json.dumps(features[example_id], sort_keys=True) + "\n")

    manifest = {
        "dataset_version": "ace-development-v4-semantic-unused-pool",
        "row_count": len(available),
        "group_count": len({value.identity.group_id for value in available}),
        "stage_a_pool_sha256": _sha256(stage_a_pool_path),
        "stage_a_dataset_sha256": _sha256(stage_a_dataset_path),
        "stage_a_features_sha256": _sha256(stage_a_features_path),
        "excluded_relationship_counts": {
            key: len(values) for key, values in sorted(excluded.items())
        },
        "pool_sha256": _sha256(output_pool_path),
        "features_sha256": _sha256(output_features_path),
        "production_claim_eligible": False,
    }
    _manifest_path(output_pool_path).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    _manifest_path(output_features_path).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def _calibrated_v3_probabilities(
    features: dict[str, dict[str, Any]], model_path: Path, calibrator_path: Path
) -> dict[str, float]:
    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:
        raise RuntimeError("Install services/api[ml] before Stage B selection") from exc
    model = CatBoostClassifier()
    model.load_model(model_path)
    ids = sorted(features)
    raw = model.predict_proba(
        [feature_vector(features[example_id]) for example_id in ids]
    )[:, 1]
    logits = [
        [math.log(min(max(float(value), 1e-6), 1 - 1e-6) /
                  (1 - min(max(float(value), 1e-6), 1 - 1e-6)))]
        for value in raw
    ]
    calibrated = load(calibrator_path).predict_proba(logits)[:, 1]
    return {
        example_id: float(probability)
        for example_id, probability in zip(ids, calibrated, strict=True)
    }


def _score_strata(
    values: list[AceDatasetExample], probabilities: dict[str, float]
) -> tuple[dict[str, str], dict[str, float]]:
    """Assign deterministic 35/30/35 score quantiles and report numeric cut points."""
    ranked = sorted(
        values,
        key=lambda value: (
            probabilities[value.identity.example_id],
            _stable(value.identity.example_id, "score-quantile"),
        ),
    )
    low_count = math.floor(len(ranked) * STRATUM_FRACTIONS["low"])
    high_count = math.floor(len(ranked) * STRATUM_FRACTIONS["high"])
    high_start = len(ranked) - high_count
    strata: dict[str, str] = {}
    for index, value in enumerate(ranked):
        strata[value.identity.example_id] = (
            "low" if index < low_count else "high" if index >= high_start else "boundary"
        )
    bounds = {
        "low_max": probabilities[ranked[low_count - 1].identity.example_id],
        "boundary_min": probabilities[ranked[low_count].identity.example_id],
        "boundary_max": probabilities[ranked[high_start - 1].identity.example_id],
        "high_min": probabilities[ranked[high_start].identity.example_id],
    }
    return strata, bounds


def _fingerprint(value: AceDatasetExample) -> str:
    text = " ".join(
        [value.mandate.objective_text]
        + [item.evidence_text or item.description for item in value.cart.line_items]
    ).lower()
    tokens = sorted(set(text.split()))[:16]
    return hashlib.sha256(" ".join(tokens).encode()).hexdigest()[:12]


def _eligible_semantic(pool: list[AceDatasetExample]) -> list[AceDatasetExample]:
    return [
        value
        for value in pool
        if value.provenance.evidence_origin == "real_public" and _attack(value) == "none"
    ]


def _take_diverse(
    candidates: list[AceDatasetExample],
    count: int,
    *,
    namespace: str,
    used_groups: set[str],
    used_sources: set[str],
    ranking: dict[str, float] | None = None,
) -> list[AceDatasetExample]:
    def key(value: AceDatasetExample) -> tuple[float, str]:
        score = 0.0 if ranking is None else ranking[value.identity.example_id]
        return (-score, _stable(value.identity.example_id, namespace))

    ranked = sorted(candidates, key=key)
    selected: list[AceDatasetExample] = []
    fingerprints: Counter[str] = Counter()
    for enforce_cap in (True, False):
        for value in ranked:
            fingerprint = _fingerprint(value)
            if (
                value.identity.group_id in used_groups
                or value.provenance.source_record_id in used_sources
                or (enforce_cap and fingerprints[fingerprint] >= 2)
            ):
                continue
            selected.append(value)
            used_groups.add(value.identity.group_id)
            used_sources.add(value.provenance.source_record_id)
            fingerprints[fingerprint] += 1
            if len(selected) == count:
                return selected
    raise ValueError(f"could select only {len(selected)} of {count} rows for {namespace}")


def select_review_queue(
    pool_path: Path,
    features_path: Path,
    model_path: Path,
    model_manifest_path: Path,
    calibrator_path: Path,
    output_path: Path,
    ledger_path: Path,
) -> dict[str, Any]:
    _refuse_existing(output_path, ledger_path)
    pool = _read(pool_path)
    features = _load_features(features_path)
    pool_ids = {value.identity.example_id for value in pool}
    if set(features) != pool_ids:
        raise ValueError("Stage B features do not exactly cover the frozen pool")
    model_manifest = json.loads(model_manifest_path.read_text())
    if model_manifest.get("artifact_sha256") != _sha256(model_path):
        raise ValueError("v3 model does not match its manifest")
    probabilities = _calibrated_v3_probabilities(features, model_path, calibrator_path)
    semantic = _eligible_semantic(pool)
    strata, stratum_bounds = _score_strata(semantic, probabilities)
    by_stratum = {
        name: [value for value in semantic if strata[value.identity.example_id] == name]
        for name in ("low", "boundary", "high")
    }
    required = Counter()
    for targets in ROLE_STRATUM_TARGETS.values():
        required.update(targets)
    for name, count in required.items():
        if len(by_stratum[name]) < count:
            raise ValueError(f"only {len(by_stratum[name])} semantic rows in {name}; need {count}")

    assignments: list[tuple[AceDatasetExample, str, str, str]] = []
    used_groups: set[str] = set()
    used_sources: set[str] = set()
    for role, targets in ROLE_STRATUM_TARGETS.items():
        for name, count in targets.items():
            selected = _take_diverse(
                by_stratum[name], count,
                namespace=f"{role}:{name}",
                used_groups=used_groups,
                used_sources=used_sources,
            )
            assignments.extend((value, role, "score_stratified", name) for value in selected)

    remaining = [
        value
        for value in semantic
        if value.identity.group_id not in used_groups
        and value.provenance.source_record_id not in used_sources
    ]
    challenge_ranking: dict[str, float] = {}
    for value in remaining:
        row = features[value.identity.example_id]
        probability = probabilities[value.identity.example_id]
        uncertainty = 1.0 - abs(probability - 0.5) * 2
        semantic_risk = max(
            float(row.get("semantic_contradiction", 0)),
            float(row.get("semantic_neutral", 0)),
        )
        challenge_ranking[value.identity.example_id] = (
            uncertainty + _semantic_entropy(row) + abs(probability - semantic_risk)
        )
    challenge = _take_diverse(
        remaining,
        CHALLENGE_TARGET,
        namespace="candidate:challenge",
        used_groups=used_groups,
        used_sources=used_sources,
        ranking=challenge_ranking,
    )
    assignments.extend(
        (value, "candidate_selection", "challenge", strata[value.identity.example_id])
        for value in challenge
    )
    assignments.sort(key=lambda item: item[0].identity.example_id)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x") as output, ledger_path.open("x") as ledger:
        for value, role, cohort, stratum in assignments:
            queue_value = value.model_copy(
                deep=True,
                update={
                    "labels": DatasetLabels(label_source="unreviewed"),
                    "split": DatasetSplit(
                        name=role,
                        grouping_keys=[value.identity.group_id, value.provenance.source_record_id],
                    ),
                },
            )
            output.write(queue_value.model_dump_json() + "\n")
            row = features[value.identity.example_id]
            ledger.write(json.dumps({
                "example_id": value.identity.example_id,
                "group_id": value.identity.group_id,
                "source_record_id": value.provenance.source_record_id,
                "role": role,
                "cohort": cohort,
                "score_stratum": stratum,
                "v3_probability": probabilities[value.identity.example_id],
                "semantic_contradiction": row["semantic_contradiction"],
                "semantic_neutral": row["semantic_neutral"],
                "challenge_score": challenge_ranking.get(value.identity.example_id),
            }, sort_keys=True) + "\n")

    role_strata = Counter(
        f"{role}:{stratum}" for _, role, cohort, stratum in assignments if cohort == "score_stratified"
    )
    expected_role_strata = Counter(
        {f"{role}:{stratum}": count for role, targets in ROLE_STRATUM_TARGETS.items() for stratum, count in targets.items()}
    )
    if role_strata != expected_role_strata:
        raise AssertionError("Stage B role-stratum contract was not satisfied")
    manifest = {
        "selection_version": SELECTION_VERSION,
        "selection_method": "calibrated-v3-score-strata-plus-fresh-diverse-challenge",
        "rows": len(assignments),
        "roles": dict(sorted(Counter(role for _, role, _, _ in assignments).items())),
        "cohorts": dict(sorted(Counter(cohort for _, _, cohort, _ in assignments).items())),
        "role_strata": dict(sorted(role_strata.items())),
        "stratum_fractions": STRATUM_FRACTIONS,
        "stratum_bounds": stratum_bounds,
        "pool_sha256": _sha256(pool_path),
        "features_sha256": _sha256(features_path),
        "model_sha256": _sha256(model_path),
        "calibrator_sha256": _sha256(calibrator_path),
        "review_queue_sha256": _sha256(output_path),
        "selection_ledger_sha256": _sha256(ledger_path),
        "candidate_is_single_use": True,
        "production_claim_eligible": False,
    }
    _manifest_path(output_path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the revised Stage B review cohort")
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze = subparsers.add_parser("freeze-pool")
    freeze.add_argument("--stage-a-pool", type=Path, required=True)
    freeze.add_argument("--stage-a-dataset", type=Path, required=True)
    freeze.add_argument("--stage-a-features", type=Path, required=True)
    freeze.add_argument("--output-pool", type=Path, required=True)
    freeze.add_argument("--output-features", type=Path, required=True)
    select = subparsers.add_parser("select-review")
    select.add_argument("--pool", type=Path, required=True)
    select.add_argument("--features", type=Path, required=True)
    select.add_argument("--model", type=Path, required=True)
    select.add_argument("--model-manifest", type=Path, required=True)
    select.add_argument("--calibrator", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    select.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "freeze-pool":
        result = freeze_unused_pool(args.stage_a_pool, args.stage_a_dataset, args.stage_a_features, args.output_pool, args.output_features)
    else:
        result = select_review_queue(args.pool, args.features, args.model, args.model_manifest, args.calibrator, args.output, args.ledger)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
