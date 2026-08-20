from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.annotations import AnnotationDecision, AnnotationReview, AnnotationStore


def _example(example_id: str) -> dict:
    return {
        "identity": {"example_id": example_id, "group_id": f"group-{example_id}"},
        "split": {"name": "train"},
        "labels": {"label_source": "unreviewed"},
        "mandate": {"objective_text": "Buy the requested item"},
        "cart": {"line_items": [{"description": "Requested item"}]},
    }


@pytest.fixture
def annotation_store(tmp_path) -> AnnotationStore:
    dataset = tmp_path / "queue.jsonl"
    dataset.write_text("".join(json.dumps(_example(value)) + "\n" for value in ("ex-1", "ex-2")))
    store = AnnotationStore(dataset, tmp_path / "annotations.sqlite3")
    store.initialize()
    return store


def _review(reviewer: str, deviation: str = "MATCH") -> AnnotationReview:
    treatment = "APPROVE" if deviation == "MATCH" else "STEP_UP"
    return AnnotationReview(
        reviewer_id=reviewer,
        deviation=deviation,
        semantic_label="ENTAILMENT" if deviation == "MATCH" else "CONTRADICTION",
        expected_treatment=treatment,
        confidence=0.9,
    )


def test_queue_requires_two_independent_reviews(annotation_store: AnnotationStore) -> None:
    item = annotation_store.next_item("reviewer-a")
    assert item is not None
    example_id = item.example["identity"]["example_id"]
    annotation_store.submit_review(example_id, _review("reviewer-a"))

    second_id = annotation_store.next_item("reviewer-a").example["identity"]["example_id"]
    assert second_id != example_id
    annotation_store.submit_review(second_id, _review("reviewer-b"))
    assert annotation_store.next_item("reviewer-b").example["identity"]["example_id"] == example_id
    annotation_store.submit_review(example_id, _review("reviewer-b"))

    progress = annotation_store.progress()
    assert progress.agreed == 1
    assert progress.single_review == 1


def test_disagreement_enters_adjudication_queue(annotation_store: AnnotationStore) -> None:
    example_id = annotation_store.next_item("reviewer-a").example["identity"]["example_id"]
    annotation_store.submit_review(example_id, _review("reviewer-a"))
    annotation_store.submit_review(example_id, _review("reviewer-b", "VIOLATION"))

    item = annotation_store.next_item("expert", adjudication_only=True)
    assert item is not None
    assert item.needs_adjudication is True
    assert {value["reviewer_id"] for value in item.prior_reviews} == {
        "reviewer-a",
        "reviewer-b",
    }
    annotation_store.adjudicate(
        example_id,
        AnnotationDecision(
            reviewer_id="expert",
            adjudicator_id="expert",
            deviation="AMBIGUOUS",
            semantic_label="NEUTRAL",
            expected_treatment="STEP_UP",
            confidence=0.8,
        ),
    )
    assert annotation_store.progress().adjudicated == 1


def test_reviewer_cannot_submit_twice(annotation_store: AnnotationStore) -> None:
    example_id = annotation_store.next_item("reviewer-a").example["identity"]["example_id"]
    annotation_store.submit_review(example_id, _review("reviewer-a"))
    with pytest.raises(ValueError, match="already submitted"):
        annotation_store.submit_review(example_id, _review("reviewer-a"))


def test_annotation_routes_are_disabled_by_default(client: TestClient) -> None:
    response = client.get("/internal/annotations/next", params={"reviewer_id": "reviewer-a"})
    assert response.status_code == 404
    assert response.json()["detail"] == "annotation service is disabled"
