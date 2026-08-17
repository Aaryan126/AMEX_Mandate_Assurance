from __future__ import annotations

import pytest

from ml.evaluation.metrics import expected_calibration_error, treatment_metrics
from ml.tabular.tabm_challenger import inclusion_gate


def test_balanced_quality_gate_metrics() -> None:
    metrics = treatment_metrics(
        ["APPROVE", "APPROVE", "HOLD", "HOLD"],
        ["APPROVE", "APPROVE", "HOLD", "HOLD"],
    )
    assert metrics == {
        "violation_recall": 1.0,
        "false_step_up_rate": 0.0,
        "false_decline_rate": 0.0,
    }


def test_calibration_error() -> None:
    assert expected_calibration_error([0, 1], [0.0, 1.0]) == pytest.approx(0.0)


def test_tabm_requires_lift_calibration_and_latency() -> None:
    result = inclusion_gate(
        {"violation_recall": 0.9, "pr_auc": 0.8, "expected_calibration_error": 0.04},
        {"violation_recall": 0.92, "pr_auc": 0.81, "expected_calibration_error": 0.04},
        core_p95_ms=800,
        challenger_p95_ms=1100,
    )
    assert result["include_online"] is True
    too_slow = inclusion_gate(
        {"violation_recall": 0.9, "pr_auc": 0.8, "expected_calibration_error": 0.04},
        {"violation_recall": 0.92, "pr_auc": 0.81, "expected_calibration_error": 0.04},
        core_p95_ms=800,
        challenger_p95_ms=2500,
    )
    assert too_slow["include_online"] is False
