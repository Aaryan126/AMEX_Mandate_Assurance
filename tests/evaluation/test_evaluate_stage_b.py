from ml.evaluation.evaluate_v4 import gate_report


def test_stage_b_gate_requires_reviewed_semantic_recall() -> None:
    quality = {"pr_auc": 0.95, "expected_calibration_error": 0.05}
    policy = {"violation_recall": 0.91, "false_step_up_rate": 0.09, "false_decline_rate": 0.0}
    families = {"none": {"violation_rows": 60, "violation_recall": 0.85}}
    assert gate_report(quality, policy, families, 0.79, 0.95)["all_passed"] is False
    assert gate_report(quality, policy, families, 0.81, 0.95)["all_passed"] is True
