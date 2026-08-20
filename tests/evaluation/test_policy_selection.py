from __future__ import annotations

import pytest

from ml.features.schema import (
    FEATURE_NAMES,
    feature_names_for_profile,
    feature_profile_for_names,
)
from ml.fusion.diagnose_remediation import shortcut_summary
from ml.fusion.policy_selection import (
    select_policy_configuration,
    select_policy_threshold,
    target_value,
)


def _row(
    treatment: str,
    *,
    contradiction: float = 0.0,
    neutral: float = 0.0,
    hard_fail_count: int = 0,
) -> dict:
    return {
        "expected_treatment": treatment,
        "critical_hold_count": 0,
        "hard_fail_count": hard_fail_count,
        "semantic_contradiction": contradiction,
        "semantic_neutral": neutral,
    }


def test_policy_target_includes_ambiguous_step_up_rows() -> None:
    ambiguous = {"label": None, "expected_treatment": "STEP_UP"}
    assert target_value(ambiguous, "binary_deviation") is None
    assert target_value(ambiguous, "policy_intervention") == 1
    assert target_value(
        {"label": 0, "expected_treatment": "APPROVE"}, "policy_intervention"
    ) == 0


def test_threshold_selection_budgets_fixed_semantic_overrides() -> None:
    rows = [_row("APPROVE", contradiction=0.9)]
    rows.extend(_row("APPROVE") for _ in range(9))
    rows.extend([_row("STEP_UP"), _row("HOLD")])
    probabilities = [0.95, 0.55, *([0.05] * 8), 0.70, 0.60]

    selected = select_policy_threshold(rows, probabilities, 0.10)

    assert selected["threshold"] == pytest.approx(0.60)
    assert selected["fixed_override_false_step_up_count"] == 1
    assert selected["false_step_up_count"] == 1
    assert selected["false_step_up_rate"] == pytest.approx(0.10)
    assert selected["violation_recall"] == pytest.approx(1.0)


def test_threshold_selection_rejects_impossible_override_budget() -> None:
    rows = [
        _row("APPROVE", contradiction=0.9),
        _row("APPROVE", neutral=0.8),
        *[_row("APPROVE") for _ in range(8)],
        _row("STEP_UP"),
    ]
    with pytest.raises(ValueError, match="fixed rule/semantic overrides"):
        select_policy_threshold(rows, [0.1] * len(rows), 0.10)


def test_configuration_selection_can_disable_harmful_semantic_override() -> None:
    rows = [_row("APPROVE", contradiction=0.9)]
    rows.extend(_row("APPROVE") for _ in range(9))
    rows.extend([_row("STEP_UP"), _row("STEP_UP")])
    probabilities = [0.05, *([0.05] * 9), 0.9, 0.8]

    selected = select_policy_configuration(
        rows,
        probabilities,
        contradiction_thresholds=(None, 0.8),
        neutral_thresholds=(None,),
    )

    assert selected["semantic_contradiction_threshold"] is None
    assert selected["violation_recall"] == pytest.approx(1.0)
    assert selected["false_step_up_count"] == 0


def test_only_declared_feature_profiles_are_accepted() -> None:
    shortcut_safe = feature_names_for_profile("shortcut-safe-v2")
    assert "line_item_count" not in shortcut_safe
    assert feature_profile_for_names(shortcut_safe) == "shortcut-safe-v2"
    assert feature_profile_for_names(FEATURE_NAMES) == "full-v2"
    with pytest.raises(ValueError, match="declared feature profile"):
        feature_profile_for_names(["amount_ratio"])


def test_shortcut_summary_exposes_perfect_construction_proxy() -> None:
    rows = [
        {
            "line_item_count": 1,
            "attack_family": "none",
            "expected_treatment": "APPROVE",
        },
        {
            "line_item_count": 2,
            "attack_family": "unrelated_add_on",
            "expected_treatment": "HOLD",
        },
    ]
    summary = shortcut_summary(rows)
    assert summary["unrelated_add_on_multi_item_fraction"] == 1.0
    assert summary["multi_item_unrelated_add_on_fraction"] == 1.0
    assert summary["by_line_item_count"]["2"]["intervention_rate"] == 1.0
