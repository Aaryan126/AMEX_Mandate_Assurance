from __future__ import annotations

from fastapi.testclient import TestClient

from .fixtures import OBJECTIVE, cart


def create_mandate(client: TestClient, *, max_fulfillments: int = 1):
    interpretation = client.post(
        "/v1/mandates/interpret", json={"objective_text": OBJECTIVE}
    ).json()
    interpretation["proposal"]["max_fulfillments"] = max_fulfillments
    response = client.post(
        "/v1/mandates",
        json={"proposal": interpretation["proposal"], "confirmed": True},
        headers={"Idempotency-Key": "create-mandate-001"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_complete_valid_journey_and_audit(client: TestClient) -> None:
    view = create_mandate(client)
    mandate_id = view["mandate"]["mandate_id"]
    evidence = cart()
    response = client.post(
        "/v1/decisions/evaluate",
        json={"mandate_id": mandate_id, "cart": evidence.model_dump(mode="json")},
        headers={"Idempotency-Key": "evaluate-valid-001"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["treatment"] == "APPROVE"
    assert response.json()["model_versions"]["policy"] == "policy-treatment-contract-v3"

    state = client.get(f"/v1/mandates/{mandate_id}").json()["state"]
    assert state["fulfilled_amount_minor"] == 84000
    assert state["fulfillment_count"] == 1

    audit = client.get(f"/v1/sessions/{mandate_id}/audit")
    assert [event["event_type"] for event in audit.json()["events"]] == [
        "MANDATE_AUTHENTICATED",
        "DECISION_EVALUATED",
    ]


def test_idempotent_evaluation_does_not_double_fulfill(client: TestClient) -> None:
    view = create_mandate(client)
    mandate_id = view["mandate"]["mandate_id"]
    payload = {"mandate_id": mandate_id, "cart": cart().model_dump(mode="json")}
    headers = {"Idempotency-Key": "evaluate-repeat-001"}
    first = client.post("/v1/decisions/evaluate", json=payload, headers=headers)
    second = client.post("/v1/decisions/evaluate", json=payload, headers=headers)
    assert first.json() == second.json()
    state = client.get(f"/v1/mandates/{mandate_id}").json()["state"]
    assert state["fulfillment_count"] == 1


def test_idempotency_conflict_uses_standard_error(client: TestClient) -> None:
    create_mandate(client)
    response = client.post(
        "/v1/mandates/interpret", json={"objective_text": OBJECTIVE + " Extra context."}
    )
    proposal = response.json()["proposal"]
    conflict = client.post(
        "/v1/mandates",
        json={"proposal": proposal, "confirmed": True},
        headers={"Idempotency-Key": "create-mandate-001"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_step_up_can_be_approved_once(client: TestClient) -> None:
    view = create_mandate(client)
    mandate_id = view["mandate"]["mandate_id"]
    decision = client.post(
        "/v1/decisions/evaluate",
        json={"mandate_id": mandate_id, "cart": cart(amount_minor=96000).model_dump(mode="json")},
        headers={"Idempotency-Key": "evaluate-budget-001"},
    ).json()
    assert decision["treatment"] == "STEP_UP"
    resolution = client.post(
        f"/v1/decisions/{decision['decision_id']}/resolve",
        json={"action": "APPROVE_ONCE"},
        headers={"Idempotency-Key": "resolve-budget-001"},
    )
    assert resolution.status_code == 200, resolution.text
    state = client.get(f"/v1/mandates/{mandate_id}").json()["state"]
    assert state["fulfilled_amount_minor"] == 96000


def test_step_up_can_replace_the_mandate(client: TestClient) -> None:
    view = create_mandate(client)
    mandate_id = view["mandate"]["mandate_id"]
    decision = client.post(
        "/v1/decisions/evaluate",
        json={"mandate_id": mandate_id, "cart": cart(amount_minor=96000).model_dump(mode="json")},
        headers={"Idempotency-Key": "evaluate-modify-001"},
    ).json()
    assert decision["treatment"] == "STEP_UP"

    modified = client.post(
        "/v1/mandates/interpret",
        json={"objective_text": OBJECTIVE.replace("S$900", "S$1,000")},
    ).json()["proposal"]
    resolution = client.post(
        f"/v1/decisions/{decision['decision_id']}/resolve",
        json={"action": "MODIFY_MANDATE", "modified_proposal": modified},
        headers={"Idempotency-Key": "resolve-modify-001"},
    )
    assert resolution.status_code == 200, resolution.text
    new_mandate_id = resolution.json()["new_mandate_id"]
    assert new_mandate_id == modified["mandate_id"]
    assert client.get(f"/v1/mandates/{mandate_id}").json()["state"]["status"] == "superseded"
    assert client.get(f"/v1/mandates/{new_mandate_id}").json()["state"]["status"] == "active"


def test_evaluation_summary_reports_locked_development_v3(client: TestClient) -> None:
    response = client.get("/v1/evaluation/summary")
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["dataset_version"] == "development-v3-candidate-selection-1000"
    assert summary["status"] == "LOCKED_NON_PROMOTABLE"
    assert summary["metrics"]["pr_auc"] == 0.9666836280994382
    assert summary["metrics"]["violation_recall"] == 0.7992957746478874


def test_validation_errors_are_versioned(client: TestClient) -> None:
    response = client.post("/v1/mandates/interpret", json={"objective_text": "short"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.headers["x-correlation-id"].startswith("cor_")


def test_unsupported_contract_version_is_rejected(client: TestClient) -> None:
    view = create_mandate(client)
    evidence = cart().model_dump(mode="json")
    evidence["schema_version"] = "2.0"
    response = client.post(
        "/v1/decisions/evaluate",
        json={"mandate_id": view["mandate"]["mandate_id"], "cart": evidence},
        headers={"Idempotency-Key": "unsupported-version-001"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_revoked_mandate_cannot_approve(client: TestClient) -> None:
    view = create_mandate(client)
    mandate_id = view["mandate"]["mandate_id"]
    revoked = client.post(
        f"/v1/mandates/{mandate_id}/revoke",
        headers={"Idempotency-Key": "revoke-mandate-001"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    decision = client.post(
        "/v1/decisions/evaluate",
        json={"mandate_id": mandate_id, "cart": cart().model_dump(mode="json")},
        headers={"Idempotency-Key": "evaluate-revoked-001"},
    )
    assert decision.status_code == 200
    assert decision.json()["treatment"] == "HOLD"
    assert "MANDATE_NOT_ACTIVE" in decision.json()["reason_codes"]
