from __future__ import annotations

import json

from ml.data import acquire_option2


def test_usaspending_resume_appends_only_new_awards(tmp_path, monkeypatch):
    records = tmp_path / "usaspending-awards" / "records.jsonl"
    records.parent.mkdir(parents=True)
    existing = [
        {
            "award_id": "A-1",
            "recipient": "Recipient One",
            "description": "First award",
            "description_origin": "real_public",
            "amount": 100.0,
        },
        {
            "award_id": "A-2",
            "recipient": "Recipient Two",
            "description": "Second award",
            "description_origin": "real_public",
            "amount": 200.0,
        },
    ]
    records.write_text("".join(json.dumps(value) + "\n" for value in existing))

    def response(_url, payload):
        assert payload["filters"]["time_period"] == [
            {"start_date": "2020-01-01", "end_date": "2020-12-31"}
        ]
        return {
            "results": [
                {
                    "Award ID": "A-2",
                    "Recipient Name": "Recipient Two",
                    "Award Amount": 200,
                    "Description": "duplicate",
                },
                {
                    "Award ID": "A-3",
                    "Recipient Name": "Recipient Three",
                    "Award Amount": 300,
                    "Description": None,
                },
            ],
            "page_metadata": {"hasNext": False},
        }

    monkeypatch.setattr(acquire_option2, "_post_json", response)

    metadata = acquire_option2.acquire_usaspending(
        tmp_path, limit=3, resume_before_year=2021
    )
    values = [json.loads(line) for line in records.read_text().splitlines()]

    assert [value["award_id"] for value in values] == ["A-1", "A-2", "A-3"]
    assert values[-1]["description_origin"] == "derived_from_public_award_id"
    assert metadata["sha256"] == acquire_option2.file_sha256(records)


def test_amazon_normalizer_parses_numpy_style_session_arrays(tmp_path):
    source = tmp_path / "download"
    source.mkdir()
    (source / "products_train.csv").write_text(
        "id,locale,title,price,brand,color,size,model,material,author,desc\n"
        "P-1,UK,Laptop sleeve,20,,,,,,,Protective sleeve\n"
        "P-2,UK,Laptop bag,35,,,,,,,Protective bag\n"
    )
    (source / "sessions_train.csv").write_text(
        "prev_items,next_item,locale\n"
        "['P-1' 'P-2'],P-2,UK\n"
    )

    metadata = acquire_option2.normalize_amazon_m2(
        tmp_path / "normalized", source, limit=1
    )
    output = tmp_path / "normalized/amazon-m2/records.jsonl"
    record = json.loads(output.read_text())

    assert record["previous_product_ids"] == ["P-1", "P-2"]
    assert record["next_product_id"] == "P-2"
    assert metadata["sha256"] == acquire_option2.file_sha256(output)
