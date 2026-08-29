from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
os.chdir(REPOSITORY_ROOT)
os.environ["ACE_MODEL_MODE"] = "development_artifact"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ace-development-runtime-") as directory:
        os.environ["ACE_DATABASE_URL"] = f"sqlite:///{Path(directory) / 'verification.sqlite3'}"

        from fastapi.testclient import TestClient

        from app.main import app

        expected = {
            "valid": "APPROVE",
            "budget": "STEP_UP",
            "semantic": "STEP_UP",
            "injected": "HOLD",
            "stateful": "HOLD",
            "uncertain": "STEP_UP",
        }
        objective = (
            "Book a refundable economy flight from Singapore to Tokyo, departing 7 September "
            "and returning 10 September, nonstop if available, total fare under S$900. "
            "Do not purchase add-ons."
        )
        outcomes: dict[str, dict[str, object]] = {}

        with TestClient(app) as client:
            runtime = client.get("/v1/runtime/status").json()
            assert runtime["runtime_mode"] == "development_artifact"
            assert runtime["semantic"] == "english-nli-v3"
            assert runtime["catboost"] == "catboost-v1"
            assert runtime["calibrator"] == "platt-calibrator-v3"

            for scenario, expected_treatment in expected.items():
                proposal = client.post(
                    "/v1/mandates/interpret",
                    json={"objective_text": objective},
                ).json()["proposal"]
                proposal["max_fulfillments"] = 2
                mandate = client.post(
                    "/v1/mandates",
                    json={"proposal": proposal, "confirmed": True},
                    headers={"Idempotency-Key": f"confirm-{uuid4()}"},
                ).json()["mandate"]

                parts = (1, 2) if scenario == "stateful" else (1,)
                result = None
                for part in parts:
                    cart = client.get(
                        f"/v1/demo/carts/{scenario}",
                        params={"stateful_part": part},
                    ).json()
                    response = client.post(
                        "/v1/decisions/evaluate",
                        json={"mandate_id": mandate["mandate_id"], "cart": cart},
                        headers={"Idempotency-Key": f"evaluate-{uuid4()}"},
                    )
                    assert response.status_code == 200, response.text
                    result = response.json()
                assert result is not None
                assert result["treatment"] == expected_treatment, (
                    scenario,
                    result["treatment"],
                    result["reason_codes"],
                )
                trusted = next(
                    item for item in result["rule_results"] if item["rule_id"] == "trusted_evidence"
                )
                assert trusted["status"] == "PASS"
                outcomes[scenario] = {
                    "treatment": result["treatment"],
                    "calibrated_risk": result["structured_risk_probability"],
                    "reason_codes": result["reason_codes"],
                    "cart_signature": "verified",
                }

        print(json.dumps({"runtime": runtime, "scenarios": outcomes}, indent=2))


if __name__ == "__main__":
    main()
