from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def build_jtt_weights(
    predictions_path: Path,
    output_path: Path,
    *,
    error_weight: float = 4.0,
) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite JTT weights: {output_path}")
    if error_weight <= 1:
        raise ValueError("JTT error weight must exceed 1")
    weights: dict[str, float] = {}
    errors: Counter[str] = Counter()
    train_rows = 0
    with predictions_path.open() as source:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["split"] != "train":
                continue
            train_rows += 1
            probabilities = [row["contradiction"], row["neutral"], row["entailment"]]
            predicted = max(range(3), key=probabilities.__getitem__)
            label = int(row["label"])
            if predicted != label:
                key = f"{row['example_id']}\x1f{row['constraint_id']}"
                if key in weights:
                    raise ValueError("semantic predictions contain duplicate training keys")
                weights[key] = error_weight
                errors[f"{label}->{predicted}"] += 1
    if not weights:
        raise ValueError("JTT requires at least one out-of-fold training error")
    payload = {
        "method": "jtt-oof-error-upweighting-v1",
        "source_predictions": str(predictions_path),
        "source_predictions_sha256": hashlib.sha256(predictions_path.read_bytes()).hexdigest(),
        "train_rows": train_rows,
        "weighted_rows": len(weights),
        "default_weight": 1.0,
        "error_weight": error_weight,
        "errors": dict(sorted(errors.items())),
        "weights": dict(sorted(weights.items())),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return {key: value for key, value in payload.items() if key != "weights"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build leakage-safe JTT weights from OOF errors")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--error-weight", type=float, default=4.0)
    args = parser.parse_args()
    print(json.dumps(build_jtt_weights(args.predictions, args.output, error_weight=args.error_weight), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
