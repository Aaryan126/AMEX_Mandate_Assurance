from __future__ import annotations

from ml.evaluation.evaluate_v4 import gate_report


def _quality(pr_auc: float = 0.96, ece: float = 0.03) -> dict[str, float]:
    return {"pr_auc": pr_auc, "brier": 0.08, "expected_calibration_error": ece}


def _policy(recall: float = 0.91, false_step_up: float = 0.09) -> dict[str, float]:
    return {
        "violation_recall": recall,
        "false_step_up_rate": false_step_up,
        "false_decline_rate": 0.0,
    }


def test_v4_gate_requires_every_operational_and_family_check() -> None:
    families = {
        "none": {"violation_rows": 100, "violation_recall": 0.85},
        "small": {"violation_rows": 20, "violation_recall": 0.1},
    }
    passed = gate_report(_quality(), _policy(), families, 0.82, 0.965)
    assert passed["all_passed"] is True
    assert passed["supported_families"] == ["none"]

    failed = gate_report(
        _quality(),
        _policy(recall=0.89),
        {"none": {"violation_rows": 100, "violation_recall": 0.79}},
        0.79,
        0.965,
    )
    assert failed["all_passed"] is False
    assert failed["checks"]["operational_recall"] is False
    assert failed["checks"]["supported_families"] is False
    assert failed["checks"]["reviewed_none"] is False


def test_v4_gate_compares_pr_auc_on_the_same_candidate() -> None:
    families = {"none": {"violation_rows": 100, "violation_recall": 0.9}}
    result = gate_report(_quality(pr_auc=0.94), _policy(), families, 0.9, 0.96)
    assert result["checks"]["pr_auc_regression"] is False
