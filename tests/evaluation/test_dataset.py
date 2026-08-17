from __future__ import annotations

import json

from ml.data.generate_dataset import (
    generate_rows,
    seed_mandates,
    split_for,
    write_dataset,
)


def test_dataset_has_fifty_seeds_and_six_outcomes_each() -> None:
    seeds = seed_mandates()
    rows = generate_rows()
    assert len(seeds) == 50
    assert len(rows) == 300
    assert {row["attack_family"] for row in rows} == {
        "valid",
        "amount_violation",
        "semantic_substitution",
        "unrelated_add_on",
        "missing_evidence",
        "cumulative_overspend",
    }


def test_seed_variants_never_cross_splits() -> None:
    rows = generate_rows()
    for seed in seed_mandates():
        assert {row["split"] for row in rows if row["seed_id"] == seed.seed_id} == {
            split_for(seed.seed_id)
        }


def test_dataset_manifest_is_reproducible(tmp_path) -> None:
    first = write_dataset(tmp_path / "first")
    second = write_dataset(tmp_path / "second")
    assert first["sha256"] == second["sha256"]
    assert first["row_count"] == 300
    assert first["ambiguous_row_count"] == 50
    stored = json.loads((tmp_path / "first" / "manifest.json").read_text())
    assert stored == first
