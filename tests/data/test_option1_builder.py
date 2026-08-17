from __future__ import annotations

from ml.data.adapters.esci import EsciAdapter
from ml.data.build_option1 import construct_option1

REVISION = "b" * 40


def source_record(index: int, locale: str) -> dict:
    return {
        "example_id": str(index),
        "query": f"product request {index}",
        "query_id": f"query_{index}",
        "product_id": f"product_{index}",
        "product_locale": locale,
        "esci_label": ("E", "S", "C", "I")[index % 4],
        "large_version": 1,
        "source_split": "train",
        "product_title": f"Real source product {index}",
        "product_description": f"Description {index}",
        "product_bullet_point": "Source-backed attribute",
        "product_brand": "Fixture",
        "product_color": "Black",
    }


def test_option1_builder_hits_component_and_split_targets_in_english() -> None:
    adapter = EsciAdapter(revision=REVISION)
    candidates = []
    for index in range(100):
        locale = "us" if index < 70 else "jp"
        candidates.extend(adapter.normalize(source_record(index, locale)))
    first = construct_option1(candidates, size=20)
    second = construct_option1(candidates, size=20)
    assert [value.model_dump_json() for value in first] == [
        value.model_dump_json() for value in second
    ]
    assert len(first) == 20
    assert sum(value.context.locale == "en-US" for value in first) == 20
    assert sum(value.context.locale == "ja-JP" for value in first) == 0
    assert {
        name: sum(value.split.name == name for value in first)
        for name in ("train", "validation", "calibration", "golden")
    } == {"train": 14, "validation": 2, "calibration": 2, "golden": 2}
    assert sum(value.labels.label_source == "unreviewed" for value in first) == 2


def test_parent_and_child_never_cross_splits() -> None:
    adapter = EsciAdapter(revision=REVISION)
    candidates = []
    for index in range(100):
        candidates.extend(
            adapter.normalize(source_record(index, "us" if index < 70 else "jp"))
        )
    values = construct_option1(candidates, size=20)
    by_id = {value.identity.example_id: value for value in values}
    for value in values:
        if value.identity.parent_example_id in by_id:
            assert (
                value.split.name == by_id[value.identity.parent_example_id].split.name
            )


def test_option1_builder_can_target_an_explicit_locale() -> None:
    adapter = EsciAdapter(revision=REVISION)
    candidates = [
        value
        for index in range(100)
        for value in adapter.normalize(source_record(index, "jp"))
    ]
    values = construct_option1(candidates, size=20, locale="ja-JP")
    assert {value.context.locale for value in values} == {"ja-JP"}
