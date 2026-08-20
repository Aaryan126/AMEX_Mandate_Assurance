from __future__ import annotations

import pytest

from ml.fusion.select_remediation import (
    _candidate_eligibility,
    _validate_candidate_contract,
    choose_candidate,
)


def _candidate(
    name: str, recall: float, false_step_up: float, false_decline: float = 0.0
) -> dict:
    metrics = {
        "violation_recall": recall,
        "false_step_up_rate": false_step_up,
        "false_decline_rate": false_decline,
    }
    return {
        "name": name,
        "validation_policy_metrics": metrics,
        "eligibility": _candidate_eligibility(metrics, 0.10),
    }


def test_candidate_selection_maximizes_recall_within_policy_limits() -> None:
    lower_recall = _candidate("no-semantic", 0.70, 0.05)
    higher_recall = _candidate("with-semantic", 0.75, 0.10)

    assert choose_candidate([lower_recall, higher_recall]) == higher_recall


def test_candidate_selection_rejects_constraint_violations() -> None:
    eligible = _candidate("no-semantic", 0.70, 0.05)
    excessive_step_up = _candidate("with-semantic", 0.99, 0.11)

    assert choose_candidate([eligible, excessive_step_up]) == eligible
    assert choose_candidate([excessive_step_up]) is None


def test_candidate_selection_uses_lower_false_step_up_as_tie_break() -> None:
    conservative = _candidate("no-semantic", 0.75, 0.05)
    aggressive = _candidate("with-semantic", 0.75, 0.10)

    assert choose_candidate([aggressive, conservative]) == conservative


def test_candidate_contract_rejects_wrong_target_mode() -> None:
    manifest = {
        "feature_profile": "shortcut-safe-v2",
        "target_mode": "binary_deviation",
        "threshold_selection_method": "complete-policy-validation-v1",
        "model_hold_enabled": False,
        "serving_approved": False,
        "threshold_selection_rows": 10,
        "false_step_up_target": 0.10,
        "model_step_up_threshold": 0.5,
    }

    with pytest.raises(ValueError, match="target_mode"):
        _validate_candidate_contract("with-semantic", manifest, 10)
