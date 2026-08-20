from __future__ import annotations

from ml.fusion.diagnose_step24 import profile_rows


def _row(
    treatment: str,
    *,
    attack: str = "none",
    critical: int = 0,
    hard: int = 0,
    contradiction: float = 0.0,
    neutral: float = 0.0,
    source: str = "llm_consensus",
) -> dict:
    return {
        "expected_treatment": treatment,
        "attack_family": attack,
        "critical_hold_count": critical,
        "hard_fail_count": hard,
        "semantic_contradiction": contradiction,
        "semantic_neutral": neutral,
        "label_source": source,
    }


def test_profile_exposes_fixed_policy_label_conflicts() -> None:
    rows = [
        _row("APPROVE", attack="cumulative_overspend", critical=1, hard=1),
        _row("STEP_UP", attack="none", contradiction=0.9),
        _row("HOLD", attack="unrelated_add_on"),
    ]

    profile = profile_rows(rows)

    assert profile["fixed_policy_confusion"] == {
        "APPROVE->HOLD": 1,
        "HOLD->APPROVE": 1,
        "STEP_UP->STEP_UP": 1,
    }
    assert profile["by_attack_family"]["cumulative_overspend"][
        "fixed_policy_confusion"
    ] == {"APPROVE->HOLD": 1}
    assert profile["fixed_policy_metrics"]["false_decline_rate"] == 1.0


def test_profile_reports_adjudication_and_trigger_rates() -> None:
    rows = [
        _row("APPROVE"),
        _row(
            "STEP_UP",
            attack="missing_required_evidence",
            neutral=0.7,
            source="llm_adjudicated",
        ),
    ]

    profile = profile_rows(rows)

    assert profile["trigger_rates"]["semantic_override"] == 0.5
    assert profile["by_attack_family"]["missing_required_evidence"][
        "adjudication_rate"
    ] == 1.0
