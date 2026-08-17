from __future__ import annotations

from ml.evaluation.evaluate import predict_treatment


def test_attack_family_metadata_cannot_change_prediction() -> None:
    observable = {
        "critical_hold_count": 0,
        "hard_fail_count": 0,
        "semantic_contradiction": 0.1,
        "semantic_neutral": 0.1,
    }
    predictions = {
        predict_treatment({**observable, "attack_family": family}, 0.2, 0.8)
        for family in ("none", "unrelated_add_on", "cumulative_overspend")
    }
    assert predictions == {"APPROVE"}


def test_only_observable_critical_rules_can_hold() -> None:
    row = {
        "critical_hold_count": 1,
        "hard_fail_count": 1,
        "semantic_contradiction": 0.99,
        "semantic_neutral": 0.0,
        "attack_family": "none",
    }
    assert predict_treatment(row, 0.99, 0.8) == "HOLD"
    assert predict_treatment({**row, "critical_hold_count": 0}, 0.99, 0.8) == "STEP_UP"
