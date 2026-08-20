from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import Any


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
    violations = [pair for pair in pairs if pair[0] != "APPROVE"]
    false_step_up = sum(actual == "APPROVE" and result == "STEP_UP" for actual, result in pairs)
    false_decline = sum(actual == "APPROVE" and result == "HOLD" for actual, result in pairs)
    recalled = sum(actual != "APPROVE" and result != "APPROVE" for actual, result in pairs)
    return {
        "violation_recall": recalled / len(violations) if violations else 0.0,
        "false_step_up_rate": false_step_up / len(valid) if valid else 0.0,
        "false_decline_rate": false_decline / len(valid) if valid else 0.0,
    }


def by_attack_family(
    rows: list[dict[str, Any]], predicted: list[str]
) -> dict[str, dict[str, float | int]]:
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row, treatment in zip(rows, predicted, strict=True):
        groups[row["attack_family"]].append((row["expected_treatment"], treatment))
    return {
        family: {
            "count": len(pairs),
            "violation_rows": sum(expected != "APPROVE" for expected, _ in pairs),
            "legitimate_rows": sum(expected == "APPROVE" for expected, _ in pairs),
            "treatment_accuracy": sum(
                expected == actual for expected, actual in pairs
            )
            / len(pairs),
            **treatment_metrics(
                [expected for expected, _ in pairs],
                [actual for _, actual in pairs],
            ),
        }
        for family, pairs in sorted(groups.items())
    }


def by_cohort(
    rows: list[dict[str, Any]],
    predicted: list[str],
    key: Callable[[dict[str, Any]], str],
) -> dict[str, dict[str, float | int]]:
    """Return policy metrics for a declared observable or evaluation-only cohort."""
    groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row, treatment in zip(rows, predicted, strict=True):
        groups[key(row)].append((str(row["expected_treatment"]), treatment))
    return {
        name: {
            "count": len(pairs),
            "violation_rows": sum(expected != "APPROVE" for expected, _ in pairs),
            "legitimate_rows": sum(expected == "APPROVE" for expected, _ in pairs),
            "treatment_accuracy": sum(expected == actual for expected, actual in pairs)
            / len(pairs),
            **treatment_metrics(
                [expected for expected, _ in pairs],
                [actual for _, actual in pairs],
            ),
        }
        for name, pairs in sorted(groups.items())
    }
