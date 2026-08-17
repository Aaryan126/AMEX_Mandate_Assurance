from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from ml.features.schema import (
    CATEGORICAL_FEATURES,
    FEATURE_NAMES,
    FEATURE_VERSION,
    feature_vector,
)


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def labeled(rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    return [row for row in rows if row["split"] == split and row["label"] is not None]


def matrix(rows: list[dict[str, Any]]) -> list[list[float | str]]:
    return [feature_vector(row) for row in rows]


def train(dataset_path: Path, artifact_dir: Path, iterations: int = 120) -> dict[str, Any]:
    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:
        raise RuntimeError("Install services/api[ml] before training CatBoost") from exc

    rows = load_rows(dataset_path)
    training = labeled(rows, "train")
    validation = labeled(rows, "validation")
    if not training or not validation:
        raise ValueError("dataset must contain labeled train and validation groups")
    category_indexes = [FEATURE_NAMES.index(name) for name in CATEGORICAL_FEATURES]
    model = CatBoostClassifier(
        iterations=iterations,
        depth=5,
        learning_rate=0.05,
        loss_function="Logloss",
        eval_metric="PRAUC",
        random_seed=2026,
        verbose=False,
        allow_writing_files=False,
        auto_class_weights="Balanced",
    )
    model.fit(
        matrix(training),
        [row["label"] for row in training],
        cat_features=category_indexes,
        eval_set=(matrix(validation), [row["label"] for row in validation]),
        early_stopping_rounds=25,
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "catboost-v1.cbm"
    model.save_model(model_path)
    manifest = {
        "model_version": "catboost-v1",
        "kind": "catboost_binary_classifier",
        "feature_version": FEATURE_VERSION,
        "feature_names": FEATURE_NAMES,
        "categorical_features": CATEGORICAL_FEATURES,
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "artifact_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "training_rows": len(training),
        "validation_rows": len(validation),
        "random_seed": 2026,
    }
    (artifact_dir / "catboost-v1.manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("ml/data/generated/mandate-cart-pairs.jsonl"))
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--iterations", type=int, default=120)
    args = parser.parse_args()
    print(json.dumps(train(args.dataset, args.artifacts, args.iterations), indent=2))


if __name__ == "__main__":
    main()

