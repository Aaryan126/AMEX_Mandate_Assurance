from __future__ import annotations

import pytest

from ml.evaluation.evaluate_stage_c1 import reviewed_semantic_recall, semantic_metrics


def test_semantic_metrics_reports_minority_recall() -> None:
    rows = [
        {"split": "validation", "label": 0, "contradiction": 0.8, "neutral": 0.1, "entailment": 0.1},
        {"split": "validation", "label": 1, "contradiction": 0.1, "neutral": 0.8, "entailment": 0.1},
        {"split": "validation", "label": 2, "contradiction": 0.1, "neutral": 0.1, "entailment": 0.8},
    ]
    result = semantic_metrics(rows, "validation")
    assert result["macro_f1"] == 1.0
    assert result["minority_mean_recall"] == 1.0


def test_reviewed_semantic_recall_ignores_non_reviewed_rows() -> None:
    rows = [
        {"label_source": "llm_assisted_v4", "expected_treatment": "STEP_UP", "hard_fail_count": 0, "critical_hold_count": 0},
        {"label_source": "llm_assisted_v4", "expected_treatment": "APPROVE", "hard_fail_count": 0, "critical_hold_count": 0},
        {"label_source": "weak_policy_v3", "expected_treatment": "STEP_UP", "hard_fail_count": 0, "critical_hold_count": 0},
    ]
    policy = {"threshold": 0.5, "semantic_contradiction_threshold": None, "semantic_neutral_threshold": None}
    result = reviewed_semantic_recall(rows, [0.8, 0.1, 0.1], policy)
    assert result == {"rows": 2, "violation_rows": 1, "recall": 1.0}


def test_reviewed_semantic_recall_requires_reviewed_violations() -> None:
    with pytest.raises(ValueError, match="reviewed semantic"):
        reviewed_semantic_recall(
            [{"label_source": "llm_assisted_v4", "expected_treatment": "APPROVE"}],
            [0.1],
            {"threshold": 0.5},
        )
