from __future__ import annotations

import math
from collections import Counter
from typing import Any

TARGET_MODES = {"binary_deviation", "policy_intervention"}


def target_value(row: dict[str, Any], mode: str) -> int | None:
    if mode not in TARGET_MODES:
        raise ValueError(f"unknown target mode: {mode}")
    if mode == "binary_deviation":
        label = row.get("label")
        return int(label) if label in (0, 1) else None
    treatment = row.get("expected_treatment")
    if treatment is None:
        return None
    if treatment not in {"APPROVE", "STEP_UP", "HOLD"}:
        raise ValueError(f"invalid expected treatment: {treatment}")
    return int(treatment != "APPROVE")


def target_rows(
    rows: list[dict[str, Any]], split: str, mode: str
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("split") == split and target_value(row, mode) is not None
    ]


def predict_policy_treatment(
    row: dict[str, Any], probability: float, threshold: float
) -> str:
    if row.get("critical_hold_count", 0):
        return "HOLD"
    if (
        row.get("hard_fail_count", 0)
        or float(row.get("semantic_contradiction", 0)) >= 0.8
        or float(row.get("semantic_neutral", 0)) >= 0.6
        or probability >= threshold
    ):
        return "STEP_UP"
    return "APPROVE"


def policy_metrics(
    rows: list[dict[str, Any]], probabilities: list[float], threshold: float
) -> dict[str, Any]:
    if len(rows) != len(probabilities) or not rows:
        raise ValueError("policy metrics require aligned, non-empty rows and probabilities")
    expected = [row.get("expected_treatment") for row in rows]
    if any(value not in {"APPROVE", "STEP_UP", "HOLD"} for value in expected):
        raise ValueError("policy metrics require a reviewed treatment for every row")
    predicted = [
        predict_policy_treatment(row, probability, threshold)
        for row, probability in zip(rows, probabilities, strict=True)
    ]
    legitimate = sum(value == "APPROVE" for value in expected)
    violations = len(rows) - legitimate
    false_step_ups = sum(
        actual == "APPROVE" and result == "STEP_UP"
        for actual, result in zip(expected, predicted, strict=True)
    )
    false_declines = sum(
        actual == "APPROVE" and result == "HOLD"
        for actual, result in zip(expected, predicted, strict=True)
    )
    recalled = sum(
        actual != "APPROVE" and result != "APPROVE"
        for actual, result in zip(expected, predicted, strict=True)
    )
    return {
        "threshold": threshold,
        "rows": len(rows),
        "legitimate_rows": legitimate,
        "violation_rows": violations,
        "false_step_up_count": false_step_ups,
        "false_step_up_rate": false_step_ups / legitimate if legitimate else 0.0,
        "false_decline_count": false_declines,
        "false_decline_rate": false_declines / legitimate if legitimate else 0.0,
        "violation_recall": recalled / violations if violations else 0.0,
        "expected_treatment_counts": dict(sorted(Counter(expected).items())),
        "predicted_treatment_counts": dict(sorted(Counter(predicted).items())),
    }


def select_policy_threshold(
    rows: list[dict[str, Any]],
    probabilities: list[float],
    false_step_up_target: float = 0.10,
) -> dict[str, Any]:
    """Choose a validation threshold against the complete serving policy.

    Rule and semantic overrides are evaluated for every candidate, so their false
    step-ups consume the same budget as model-triggered step-ups.
    """
    if not 0 <= false_step_up_target < 1:
        raise ValueError("false-step-up target must be in [0, 1)")
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities):
        raise ValueError("threshold selection probabilities must be finite and in [0, 1]")
    if len(rows) != len(probabilities) or not rows:
        raise ValueError("threshold selection requires aligned, non-empty inputs")
    legitimate = sum(row.get("expected_treatment") == "APPROVE" for row in rows)
    violations = sum(row.get("expected_treatment") in {"STEP_UP", "HOLD"} for row in rows)
    if legitimate == 0 or violations == 0 or legitimate + violations != len(rows):
        raise ValueError("threshold selection requires reviewed legitimate and violation rows")

    disabled_threshold = math.nextafter(1.0, math.inf)
    fixed = policy_metrics(rows, probabilities, disabled_threshold)
    budget = math.floor(legitimate * false_step_up_target)
    if fixed["false_step_up_count"] > budget:
        raise ValueError(
            "fixed rule/semantic overrides already exceed the false-step-up budget"
        )

    candidates = [disabled_threshold, *sorted(set(probabilities), reverse=True)]
    best: tuple[float, int, float, dict[str, Any]] | None = None
    for threshold in candidates:
        metrics = policy_metrics(rows, probabilities, threshold)
        if metrics["false_step_up_count"] > budget:
            continue
        rank = (
            float(metrics["violation_recall"]),
            -int(metrics["false_step_up_count"]),
            threshold,
            metrics,
        )
        if best is None or rank[:3] > best[:3]:
            best = rank
    if best is None:
        raise AssertionError("disabled model escalation must preserve the fixed-policy rate")
    result = best[3]
    return {
        **result,
        "selection_method": "complete-policy-validation-v1",
        "false_step_up_target": false_step_up_target,
        "false_step_up_budget": budget,
        "fixed_override_false_step_up_count": fixed["false_step_up_count"],
        "fixed_override_false_step_up_rate": fixed["false_step_up_rate"],
        "fixed_override_false_decline_count": fixed["false_decline_count"],
        "fixed_override_false_decline_rate": fixed["false_decline_rate"],
    }
