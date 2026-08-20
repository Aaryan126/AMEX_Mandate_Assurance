from __future__ import annotations

import pytest

from ml.evaluation.diagnose_stage_c import oracle_routing


def _row(treatment: str, *, source: str, contradiction: float = 0.0, neutral: float = 0.0):
    return {
        "expected_treatment": treatment,
        "label_source": source,
        "critical_hold_count": 0,
        "hard_fail_count": 0,
        "semantic_contradiction": contradiction,
        "semantic_neutral": neutral,
    }


def test_oracle_routing_finds_fixed_grid_semantic_headroom() -> None:
    rows = [
        _row("APPROVE", source="llm_assisted_v4", neutral=0.1),
        _row("APPROVE", source="llm_assisted_v4", neutral=0.2),
        _row("STEP_UP", source="llm_assisted_v4", neutral=0.8),
        _row("STEP_UP", source="llm_assisted_v4", contradiction=0.8),
        _row("HOLD", source="deterministic_policy_v4"),
    ]
    result = oracle_routing(rows, [0.1, 0.2, 0.2, 0.2, 0.9])

    assert result["semantic_recall"] == 1.0
    assert result["operational_recall"] == 1.0
    assert result["false_step_up_rate"] == 0.0


def test_oracle_routing_requires_all_cohorts() -> None:
    with pytest.raises(ValueError, match="legitimate, violation, and reviewed"):
        oracle_routing([_row("APPROVE", source="llm_assisted_v4")], [0.1])
