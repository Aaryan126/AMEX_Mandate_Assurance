import type { ScenarioKey } from "@/lib/scenarios";
import type { CartEvidence, Decision, MandateProposal } from "@/lib/types";

type Props = {
  scenario: ScenarioKey | null;
  proposal: MandateProposal | null;
  cart: CartEvidence | null;
  decision: Decision | null;
};

type ComparisonRow = {
  term: string;
  confirmed: string;
  proposed: string;
  changed: boolean;
};

const scenarioMeaning: Record<ScenarioKey, string> = {
  valid: "No material term changed; trusted evidence supports the requested outcome.",
  budget: "The itinerary matches, but the proposed price exceeds the confirmed limit.",
  semantic: "Refundability changed from a required term to an explicitly prohibited refund outcome.",
  injected: "The flight matches, but a prohibited gift-card subscription was inserted into the cart.",
  stateful: "The second purchase takes cumulative spend beyond the mandate’s total budget.",
  uncertain: "Trusted evidence does not establish whether the required refundability term is satisfied.",
};

function money(value: unknown, currency = "SGD") {
  if (typeof value !== "number") return "Not established";
  return new Intl.NumberFormat("en-SG", { style: "currency", currency }).format(value / 100);
}

function displayRefundability(cart: CartEvidence) {
  const value = cart.line_items[0]?.attributes?.refundable;
  if (value === true) return "Refundable";
  if (value === false) return "Non-refundable";
  return "Not established";
}

function buildRows(proposal: MandateProposal, cart: CartEvidence, decision: Decision): ComparisonRow[] {
  const budget = proposal.constraints.find((constraint) => constraint.type === "total_budget");
  const singleBudget = decision.rule_results.find((result) => result.rule_id === "single_cart_budget");
  const cumulativeBudget = decision.rule_results.find((result) => result.rule_id === "cumulative_budget");
  const route = proposal.constraints.find((constraint) => constraint.type === "route")?.value as
    | { origin?: string; destination?: string }
    | undefined;
  const attributes = cart.line_items[0]?.attributes ?? {};
  const extras = cart.line_items.slice(1).map((item) => item.description);
  const rows: ComparisonRow[] = [
    {
      term: "Route",
      confirmed: `${route?.origin ?? "SIN"} → ${route?.destination ?? "TYO"}`,
      proposed: `${String(attributes.origin ?? "Not established")} → ${String(attributes.destination ?? "Not established")}`,
      changed: decision.reason_codes.some((reason) => reason.includes("ROUTE")),
    },
    {
      term: "Refundability",
      confirmed: "Refundable required",
      proposed: displayRefundability(cart),
      changed: decision.reason_codes.some((reason) => reason.includes("ATTRIBUTE")),
    },
    {
      term: "Transaction budget",
      confirmed: money(budget?.amount_minor, budget?.currency ?? cart.currency),
      proposed: money(singleBudget?.observed_value ?? cart.total_amount_minor, cart.currency),
      changed: singleBudget?.status === "FAIL",
    },
    {
      term: "Add-ons",
      confirmed: "None permitted",
      proposed: extras.length ? extras.join(", ") : "None",
      changed: decision.reason_codes.includes("EXPLICIT_PROHIBITED_ITEM_OR_CATEGORY"),
    },
  ];
  if (decision.reason_codes.includes("CUMULATIVE_BUDGET_EXCEEDED")) {
    rows.splice(3, 0, {
      term: "Cumulative spend",
      confirmed: money(cumulativeBudget?.expected_value ?? budget?.amount_minor, cart.currency),
      proposed: money(cumulativeBudget?.observed_value, cart.currency),
      changed: true,
    });
  }
  return rows;
}

export function OutcomeComparison({ scenario, proposal, cart, decision }: Props) {
  if (!scenario || !proposal || !cart || !decision) return null;
  const rows = buildRows(proposal, cart, decision);
  return (
    <section className="panel comparison-panel" aria-labelledby="comparison-title">
      <div className="panel-heading comparison-heading">
        <div>
          <p className="eyebrow">What changed?</p>
          <h2 id="comparison-title">Confirmed mandate vs proposed outcome</h2>
        </div>
        <span className={`comparison-treatment treatment-${decision.treatment.toLowerCase()}`}>
          {decision.treatment === "STEP_UP" ? "ASK CARD MEMBER" : decision.treatment}
        </span>
      </div>
      <p className="comparison-summary">{scenarioMeaning[scenario]}</p>
      <div className="comparison-table" role="table" aria-label="Mandate and outcome comparison">
        <div className="comparison-row comparison-header" role="row">
          <span role="columnheader">Term</span>
          <span role="columnheader">Confirmed mandate</span>
          <span role="columnheader">Proposed outcome</span>
        </div>
        {rows.map((row) => (
          <div className="comparison-row" data-changed={row.changed || undefined} role="row" key={row.term}>
            <strong role="cell">{row.term}</strong>
            <span role="cell">{row.confirmed}</span>
            <span role="cell">{row.changed ? "⚠ " : "✓ "}{row.proposed}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
