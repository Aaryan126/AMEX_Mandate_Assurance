from ml.tabular.train_stage_b import _confidence_weights, _selection_rank


def test_stage_b_confidence_weights_only_weak_sources() -> None:
    rows = [{"label_source": "weak_policy_v3"}, {"label_source": "llm_assisted_v4"}, {"label_source": "deterministic_policy_v3"}]
    assert _confidence_weights(rows) == [0.5, 1.0, 1.0]


def test_stage_b_selection_prioritizes_recall_then_false_step_up() -> None:
    strong = {"policy": {"violation_recall": 0.9, "false_step_up_rate": 0.1}, "quality": {"pr_auc": 0.8, "brier": 0.2}}
    precise = {"policy": {"violation_recall": 0.89, "false_step_up_rate": 0.01}, "quality": {"pr_auc": 0.99, "brier": 0.01}}
    assert _selection_rank(strong) > _selection_rank(precise)
