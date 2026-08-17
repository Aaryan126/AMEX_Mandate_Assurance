from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable


def expected_calibration_error(
    labels: list[int], probabilities: list[float], bins: int = 10
) -> float:
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("labels and probabilities must be non-empty and the same length")
    error = 0.0
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        members = [
            position
            for position, probability in enumerate(probabilities)
            if lower <= probability < upper or (index == bins - 1 and probability == 1)
        ]
        if not members:
            continue
        accuracy = sum(labels[position] for position in members) / len(members)
        confidence = sum(probabilities[position] for position in members) / len(members)
        error += (len(members) / len(labels)) * abs(accuracy - confidence)
    return error


def treatment_metrics(expected: Iterable[str], predicted: Iterable[str]) -> dict[str, float]:
    pairs = list(zip(expected, predicted, strict=True))
    valid = [pair for pair in pairs if pair[0] == "APPROVE"]
    violations = [pair for pair in pairs if pair[0] == "HOLD"]
    false_step_up = sum(actual == "APPROVE" and result == "STEP_UP" for actual, result in pairs)
    false_decline = sum(actual == "APPROVE" and result == "HOLD" for actual, result in pairs)
    recalled = sum(actual == "HOLD" and result == "HOLD" for actual, result in pairs)
    return {
        "violation_recall": recalled / len(violations) if violations else 0.0,
        "false_step_up_rate": false_step_up / len(valid) if valid else 0.0,
        "false_decline_rate": false_decline / len(valid) if valid else 0.0,
    }


def by_attack_family(rows: list[dict], predicted: list[str]) -> dict[str, dict[str, float]]:
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row, treatment in zip(rows, predicted, strict=True):
        groups[row["attack_family"]].append((row["expected_treatment"], treatment))
    return {
        family: {
            "count": float(len(pairs)),
            "treatment_accuracy": sum(expected == actual for expected, actual in pairs) / len(pairs),
        }
        for family, pairs in sorted(groups.items())
    }
