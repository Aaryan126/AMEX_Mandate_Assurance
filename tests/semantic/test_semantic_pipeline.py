from __future__ import annotations

from ml.data.adapters.esci import EsciAdapter
from ml.semantic.dataset import fold_for_group, nli_inference_rows, nli_rows
from ml.semantic.train_multilingual import select_temperature
from tests.data.test_option1_builder import source_record


def test_esci_examples_become_nli_pairs() -> None:
    adapter = EsciAdapter(revision="c" * 40)
    english = next(iter(adapter.normalize(source_record(0, "us"))))
    japanese = next(iter(adapter.normalize(source_record(1, "jp"))))
    rows = [*nli_rows(english), *nli_rows(japanese)]
    assert [value.label for value in rows] == [2, 1]
    assert {value.example_id for value in rows} == {
        english.identity.example_id,
        japanese.identity.example_id,
    }
    assert all(value.premise and value.hypothesis for value in rows)


def test_cross_fit_assignment_is_deterministic_and_grouped() -> None:
    assert fold_for_group("query-1", 5) == fold_for_group("query-1", 5)
    assignments = {
        f"query-{index}": fold_for_group(f"query-{index}", 5) for index in range(100)
    }
    assert set(assignments.values()) == set(range(5))


def test_unlabeled_semantic_pair_is_inference_only() -> None:
    adapter = EsciAdapter(revision="c" * 40)
    value = next(iter(adapter.normalize(source_record(0, "us"))))
    value.labels.semantic = []
    assert nli_rows(value) == []
    inference = nli_inference_rows(value)
    assert len(inference) == 1
    assert inference[0].label == -1


def test_temperature_is_fit_from_heldout_logits() -> None:
    logits = [[5.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 5.0]]
    assert 0.5 <= select_temperature(logits, [0, 1, 2]) <= 3.0
