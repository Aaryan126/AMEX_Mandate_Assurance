from __future__ import annotations

import json

from ml.data.freeze_replacement_holdout import freeze_holdout
from ml.data.schema import AceDatasetExample
from ml.data.validate_dataset import validate
from tests.data.test_fast_track_selection import _dataset


def test_replacement_holdout_is_disjoint_blinded_and_idempotent(tmp_path) -> None:
    source_values = _dataset()
    for value in source_values:
        value.provenance.source_record_id = f"record-{value.identity.group_id}"
    source = tmp_path / "source.jsonl"
    source.write_text(
        "".join(value.model_dump_json() + "\n" for value in source_values)
    )
    excluded_values = [
        value
        for value in source_values
        if value.identity.group_id in {"group-0", "group-1", "paired-group"}
    ]
    exclusion = tmp_path / "excluded.jsonl"
    exclusion.write_text(
        "".join(value.model_dump_json() + "\n" for value in excluded_values)
    )

    manifest = freeze_holdout(
        source,
        exclusion,
        tmp_path / "replacement",
        rows=12,
        max_total_variation=1.0,
    )
    output = tmp_path / "replacement/replacement-holdout.blinded.jsonl"
    frozen = [
        AceDatasetExample.model_validate_json(line)
        for line in output.read_text().splitlines()
    ]

    assert manifest["skipped"] is False
    assert manifest["row_count"] == 12
    assert manifest["prior_group_overlap"] == 0
    assert {value.split.name for value in frozen} == {"golden"}
    assert {value.labels.label_source for value in frozen} == {"unreviewed"}
    assert all(value.labels.deviation is None for value in frozen)
    assert not {
        value.identity.group_id for value in frozen
    }.intersection(value.identity.group_id for value in excluded_values)
    assert validate(output, tmp_path / "replacement/manifest.json")["rows"] == 12

    repeated = freeze_holdout(
        source,
        exclusion,
        tmp_path / "replacement",
        rows=12,
        max_total_variation=1.0,
    )
    assert repeated["skipped"] is True
    assert json.loads((tmp_path / "replacement/manifest.json").read_text())[
        "dataset_sha256"
    ] == manifest["dataset_sha256"]


def test_replacement_holdout_refuses_partial_existing_lock(tmp_path) -> None:
    source_values = _dataset()
    for value in source_values:
        value.provenance.source_record_id = f"record-{value.identity.group_id}"
    source = tmp_path / "source.jsonl"
    exclusion = tmp_path / "excluded.jsonl"
    source.write_text(
        "".join(value.model_dump_json() + "\n" for value in source_values)
    )
    exclusion.write_text(source_values[0].model_dump_json() + "\n")
    output_dir = tmp_path / "replacement"
    output_dir.mkdir()
    (output_dir / "manifest.json").write_text("{}")

    try:
        freeze_holdout(
            source,
            exclusion,
            output_dir,
            rows=8,
            max_total_variation=1.0,
        )
    except ValueError as exc:
        assert "already frozen" in str(exc)
    else:
        raise AssertionError("partial lock should be rejected")
