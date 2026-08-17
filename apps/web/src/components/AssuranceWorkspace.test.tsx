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

const decision = {
  decision_id: "dec_test",
  treatment: "STEP_UP",
  risk_probability: 0.55,
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
  model_versions: { semantic: "heuristic-v1", policy: "policy-v1" },
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
  });

  it("interprets, confirms, evaluates, and resolves a step-up", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockImplementationOnce(() => jsonResponse({ proposal, warnings: [] }))
      .mockImplementationOnce(() => jsonResponse(mandateView, 201))
      .mockImplementationOnce(() => jsonResponse({ events: [{ event_id: "evt_1", event_type: "MANDATE_AUTHENTICATED", payload: {}, created_at: "2026-08-15T00:00:00Z" }] }))
      .mockImplementationOnce(() => jsonResponse(decision))
      .mockImplementationOnce(() => jsonResponse({ events: [] }))
      .mockImplementationOnce(() => jsonResponse({ status: "resolved" }))
      .mockImplementationOnce(() => jsonResponse({ events: [] }));

    const user = userEvent.setup();
    render(<AssuranceWorkspace />);
    await user.click(screen.getByRole("button", { name: /interpret mandate/i }));
    expect(await screen.findByText(/total budget/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /confirm & authenticate/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /budget breach/i })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /budget breach/i }));
    expect(await screen.findByRole("heading", { name: /confirmation needed/i })).toBeInTheDocument();
    expect(screen.getByText("SINGLE_CART_BUDGET_EXCEEDED")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /approve once/i }));
    expect(await screen.findByText(/approved once by the card member/i)).toBeInTheDocument();
  });

  it("surfaces API failures accessibly", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementationOnce(() =>
      jsonResponse({ error: { message: "Service unavailable" } }, 503),
    );
    const user = userEvent.setup();
    render(<AssuranceWorkspace />);
    await user.click(screen.getByRole("button", { name: /interpret mandate/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Service unavailable");
  });

  it("loads frozen benchmark evidence on demand", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementationOnce(() =>
      jsonResponse({
        dataset_version: "synthetic-v1",
        model_version: "stacker-calibrator-v1",
        status: "passed",
        metrics: {
          violation_recall: 1,
          false_step_up_rate: 0,
          false_decline_rate: 0,
          pr_auc: 1,
          expected_calibration_error: 0.19,
        },
        attack_families: { valid: { treatment_accuracy: 1 } },
        latency_ms: { p95: 1.72 },
        generated_at: "2026-08-15T00:00:00Z",
      }),
    );
    const user = userEvent.setup();
    render(<AssuranceWorkspace />);
    await user.click(screen.getByRole("button", { name: /load benchmark results/i }));
    expect(await screen.findByText("stacker-calibrator-v1")).toBeInTheDocument();
    expect(screen.getByText("1.72 ms")).toBeInTheDocument();
  });
});
