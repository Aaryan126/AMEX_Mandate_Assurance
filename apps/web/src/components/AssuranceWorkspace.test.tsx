import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AssuranceWorkspace } from "./AssuranceWorkspace";

const proposal = {
  schema_version: "1.0",
  mandate_id: "mdt_test",
  mandate_version: 1,
  principal_id: "cm_test",
  agent_id: "agent_test",
  objective_text: "Book a refundable economy flight under S$900",
  constraints: [
    {
      constraint_id: "c_budget",
      type: "total_budget",
      operator: "lte",
      amount_minor: 90000,
      currency: "SGD",
    },
    {
      constraint_id: "c_route",
      type: "route",
      operator: "eq",
      value: { origin: "SIN", destination: "TYO" },
    },
    {
      constraint_id: "c_dates",
      type: "travel_dates",
      operator: "eq",
      value: { outbound_date: "2026-09-07", return_date: "2026-09-10" },
    },
  ],
  valid_from: "2026-08-15T00:00:00Z",
  expires_at: "2026-09-15T00:00:00Z",
  max_fulfillments: 1,
  approval_policy: { allow_step_up: true, allow_agent_override: false },
};

const mandateView = {
  mandate: { ...proposal, authorization_reference: "signed.demo", status: "active" },
  state: { fulfilled_amount_minor: 0, fulfillment_count: 0, prior_transaction_ids: [] },
};

const runtimeStatus = {
  runtime_mode: "heuristic",
  ready: true,
  semantic: "heuristic-nli-v1",
  catboost: null,
  calibrator: null,
  policy: "policy-treatment-contract-v3",
  features: "features-v2",
  candidate_status: null,
  model_step_up_threshold: null,
  evidence_verification: "Ed25519 verification required",
};

const signedCart = {
  schema_version: "1.0",
  cart_id: "cart_budget_test",
  merchant_id: "merchant_air_demo",
  merchant_category: "AIRLINE",
  evidence_source: "SIMULATED_MERCHANT_SIGNED_CART",
  evidence_trust: "trusted",
  evidence_sufficiency: "sufficient",
  currency: "SGD",
  total_amount_minor: 96000,
  line_items: [{
    line_item_id: "li_budget_flight",
    description: "Refundable economy flight",
    evidence_text: "This fare is refundable.",
    quantity: 1,
    amount_minor: 96000,
    attributes: { refundable: true },
  }],
  created_at: "2026-08-15T00:00:01Z",
  evidence_reference: "payload.signature",
};

const decision = {
  decision_id: "dec_test",
  treatment: "STEP_UP",
  risk_probability: 0.55,
  structured_risk_probability: 0.55,
  uncertainty_band: "moderate",
  reason_codes: ["SINGLE_CART_BUDGET_EXCEEDED"],
  card_member_explanation: "The proposed purchase exceeds the authorized transaction budget.",
  reviewer_explanation: "Budget evidence",
  rule_results: [
    {
      rule_id: "single_cart_budget",
      status: "FAIL",
      observed_value: 96000,
      expected_value: 90000,
      reason_code: "SINGLE_CART_BUDGET_EXCEEDED",
    },
  ],
  semantic_results: [],
  model_versions: {
    semantic: "heuristic-v1",
    policy: "policy-v1",
    features: "features-v2",
    runtime_mode: "heuristic",
  },
  created_at: "2026-08-15T00:00:01Z",
};

function jsonResponse(value: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }));
}

describe("AssuranceWorkspace", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps transaction scenarios disabled until a mandate is authenticated", () => {
    render(<AssuranceWorkspace />);
    expect(screen.getByRole("button", { name: /valid itinerary/i })).toBeDisabled();
    expect(screen.getByRole("heading", { name: /decision evidence will appear here/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Business value")).toHaveTextContent("Protection");
    expect(screen.getByLabelText("Business value")).toHaveTextContent("Growth");
    expect(screen.getByLabelText("Business value")).toHaveTextContent("Productivity");
    expect(screen.getByRole("button", { name: /start 90-second guided demo/i })).toBeEnabled();
  });

  it("interprets, confirms, evaluates, and resolves a step-up", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockImplementationOnce(() => jsonResponse(runtimeStatus))
      .mockImplementationOnce(() => jsonResponse({ proposal, warnings: [] }))
      .mockImplementationOnce(() => jsonResponse(mandateView, 201))
      .mockImplementationOnce(() => jsonResponse({ events: [{ event_id: "evt_1", event_type: "MANDATE_AUTHENTICATED", payload: {}, created_at: "2026-08-15T00:00:00Z" }] }))
      .mockImplementationOnce(() => jsonResponse(mandateView, 201))
      .mockImplementationOnce(() => jsonResponse(signedCart))
      .mockImplementationOnce(() => jsonResponse(decision))
      .mockImplementationOnce(() => jsonResponse({ events: [] }))
      .mockImplementationOnce(() => jsonResponse({ status: "resolved" }))
      .mockImplementationOnce(() => jsonResponse({ events: [] }));

    const user = userEvent.setup();
    render(<AssuranceWorkspace />);
    await user.click(screen.getByRole("button", { name: /interpret mandate/i }));
    expect(await screen.findByText(/total budget/i)).toBeInTheDocument();
    expect(screen.getByText("SIN → TYO")).toBeInTheDocument();
    expect(screen.getByText("7 Sept 2026 → 10 Sept 2026")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /confirm & authenticate/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /budget breach/i })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /budget breach/i }));
    expect(await screen.findByRole("heading", { name: /confirmation needed/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /confirmed mandate vs proposed outcome/i })).toBeInTheDocument();
    expect(screen.getByText(/proposed price exceeds the confirmed limit/i)).toBeInTheDocument();
    expect(screen.getByText("SINGLE_CART_BUDGET_EXCEEDED")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /approve once/i }));
    expect(await screen.findByText(/approved once by the card member/i)).toBeInTheDocument();
  });

  it("surfaces API failures accessibly", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => jsonResponse(runtimeStatus))
      .mockImplementationOnce(() => jsonResponse({ error: { message: "Service unavailable" } }, 503));
    const user = userEvent.setup();
    render(<AssuranceWorkspace />);
    await user.click(screen.getByRole("button", { name: /interpret mandate/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Service unavailable");
  });

  it("loads frozen benchmark evidence on demand", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockImplementationOnce(() => jsonResponse(runtimeStatus))
      .mockImplementationOnce(() => jsonResponse({
        dataset_version: "development-v3-candidate-selection-1000",
        model_version: "catboost-v1 + platt-calibrator-v3",
        status: "LOCKED_NON_PROMOTABLE",
        metrics: {
          violation_recall: 0.7992957746478874,
          false_step_up_rate: 0.09027777777777778,
          false_decline_rate: 0,
          pr_auc: 0.9666836280994382,
          brier_score: 0.08719374688125632,
          expected_calibration_error: 0.025228743103273766,
          supported_family_recall: 0.4146341463414634,
        },
        attack_families: { cumulative_overspend: { violation_recall: 1 } },
        latency_ms: {},
        generated_at: "2026-08-20T06:48:58Z",
      }));
    const user = userEvent.setup();
    render(<AssuranceWorkspace />);
    await user.click(screen.getByRole("button", { name: /load benchmark results/i }));
    expect(await screen.findByText("catboost-v1 + platt-calibrator-v3")).toBeInTheDocument();
    expect(screen.getByText("0.9667")).toBeInTheDocument();
    expect(screen.getByText("79.93%")).toBeInTheDocument();
    expect(screen.getByText(/strong ranking and calibration/i)).toBeInTheDocument();
  });

  it("moves a stepped-up decision into the mandate modification flow", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockImplementationOnce(() => jsonResponse(runtimeStatus))
      .mockImplementationOnce(() => jsonResponse({ proposal, warnings: [] }))
      .mockImplementationOnce(() => jsonResponse(mandateView, 201))
      .mockImplementationOnce(() => jsonResponse({ events: [] }))
      .mockImplementationOnce(() => jsonResponse(mandateView, 201))
      .mockImplementationOnce(() => jsonResponse(signedCart))
      .mockImplementationOnce(() => jsonResponse(decision))
      .mockImplementationOnce(() => jsonResponse({ events: [] }));

    const user = userEvent.setup();
    render(<AssuranceWorkspace />);
    await user.click(screen.getByRole("button", { name: /interpret mandate/i }));
    await user.click(await screen.findByRole("button", { name: /confirm & authenticate/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /budget breach/i })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /budget breach/i }));
    await user.click(await screen.findByRole("button", { name: /modify mandate/i }));

    expect(screen.getByText(/revise the objective/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /budget breach/i })).toBeDisabled();
  });
});
