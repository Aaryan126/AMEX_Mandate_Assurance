from __future__ import annotations

import json
from collections import Counter

import pytest

from ml.data.schema import DatasetLabels, DatasetSplit, Identity
from ml.data.select_fast_track import select_examples, select_file
from ml.data.validate_dataset import validate
from tests.data.test_schema_v2 import example


def _value(
    index: int,
    split: str,
    *,
    group_id: str | None = None,
    rare: bool = False,
    unreviewed: bool = False,
):
    value = example().model_copy(deep=True)
    value.identity = Identity(
        example_id=f"example-{index}", group_id=group_id or f"group-{index}"
    )
    value.split = DatasetSplit(name=split, grouping_keys=["identity.group_id"])
    if unreviewed:
        value.labels = DatasetLabels(label_source="unreviewed")
    if rare:
        value.provenance.transformation = "rare_missing_evidence"
        value.cart.evidence_sufficiency = "missing"
        value.labels = DatasetLabels(
            deviation="AMBIGUOUS",
            expected_treatment="STEP_UP",
            label_source="deterministic_counterfactual",
        )
    value.mandate.objective_text = f"Representative request family {index % 7}"
    value.cart.line_items[0].evidence_text = (
        f"Evidence cluster {index % 11} with product variation {index}"
    )
    return value


def _dataset():
    values = []
    for index in range(36):
        values.append(
            _value(
                index,
                "train",
                rare=index in {0, 1},
                unreviewed=index % 5 == 0 and index not in {0, 1},
            )
        )
    values.extend(
        [
            _value(100, "train", group_id="paired-group"),
            _value(101, "train", group_id="paired-group"),
        ]
    )
    for split, offset in (("validation", 200), ("calibration", 300), ("golden", 400)):
        values.extend(_value(offset + index, split) for index in range(4))
    return values


def test_selection_is_deterministic_group_safe_and_retains_held_out_rows() -> None:
    values = _dataset()
    first, first_report = select_examples(
        values, train_rows=20, max_total_variation=1.0
    )
    second, second_report = select_examples(
        values, train_rows=20, max_total_variation=1.0
    )

    assert [value.identity.example_id for value in first] == [
        value.identity.example_id for value in second
    ]
    assert first_report == second_report
    assert Counter(value.split.name for value in first) == {
        "train": 20,
        "validation": 4,
        "calibration": 4,
        "golden": 4,
    }
    selected_pair = [
        value for value in first if value.identity.group_id == "paired-group"
    ]
    assert len(selected_pair) in {0, 2}
    assert first_report["retained_held_out_rows"] == 12


def test_selection_preserves_rare_and_unreviewed_categories() -> None:
    selected, report = select_examples(
        _dataset(), train_rows=20, max_total_variation=1.0
    )
    training = [value for value in selected if value.split.name == "train"]

    assert any(
        value.provenance.transformation == "rare_missing_evidence"
        for value in training
    )
    assert any(value.labels.label_source == "unreviewed" for value in training)
    assert report["representation"]["missing_categories"] == []


def test_selection_rejects_groups_that_cross_splits() -> None:
    values = [
        _value(1, "train", group_id="leaking-group"),
        _value(2, "golden", group_id="leaking-group"),
    ]
    with pytest.raises(ValueError, match="crosses"):
        select_examples(values, train_rows=1, max_total_variation=1.0)


def test_selection_enforces_distribution_drift_gate() -> None:
    with pytest.raises(ValueError, match="total-variation gate"):
        select_examples(
            _dataset(),
            train_rows=20,
            max_total_variation=0.0,
            require_category_coverage=False,
        )


def test_file_selection_binds_source_and_output_checksums(tmp_path) -> None:
    dataset = tmp_path / "source.jsonl"
    values = _dataset()
    dataset.write_text("".join(value.model_dump_json() + "\n" for value in values))
    from ml.data.adapters.base import file_sha256

    source_manifest = tmp_path / "source-manifest.json"
    source_manifest.write_text(
        json.dumps(
            {"row_count": len(values), "dataset_sha256": file_sha256(dataset)}
        )
    )

    manifest = select_file(
        dataset,
        tmp_path / "output",
        train_rows=20,
        max_total_variation=1.0,
        source_manifest_path=source_manifest,
    )

    output = tmp_path / "output/ace-fast-track.jsonl"
    output_manifest = tmp_path / "output/manifest.json"
    assert manifest["source_dataset_sha256"] == file_sha256(dataset)
    assert manifest["dataset_sha256"] == file_sha256(output)
    assert manifest["row_count"] == manifest["output_rows"] == 32
    assert validate(output, output_manifest)["rows"] == 32
    assert json.loads(output_manifest.read_text()) == manifest
