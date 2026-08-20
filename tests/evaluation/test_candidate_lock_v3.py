from __future__ import annotations

from ml.fusion.lock_candidate_v3 import evaluate_gates


def _report(recall: float, family_recall: float = 0.9) -> dict:
    return {
        "selected_candidate": "calibrated_catboost",
        "candidates": {
            "calibrated_catboost": {
                "candidate_selection_quality": {
                    "expected_calibration_error": 0.04
                },
                "candidate_selection_policy": {
                    "violation_recall": recall,
                    "false_step_up_rate": 0.09,
                    "false_decline_rate": 0.0,
                },
                "by_attack_family": {
                    "supported": {
                        "violation_rows": 60,
                        "violation_recall": family_recall,
                    },
                    "small": {"violation_rows": 10, "violation_recall": 0.0},
                },
            }
        },
    }


def test_candidate_lock_requires_every_development_gate() -> None:
    assert evaluate_gates(_report(0.91))["all_passed"] is True
    result = evaluate_gates(_report(0.79, family_recall=0.4))
    assert result["all_passed"] is False
    assert result["checks"]["operational_recall"]["passed"] is False
    assert result["checks"]["supported_families"]["failures"] == {
        "supported": 0.4
    }
