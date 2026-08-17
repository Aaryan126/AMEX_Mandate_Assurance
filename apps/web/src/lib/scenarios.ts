import type { CartEvidence } from "./types";

export type ScenarioKey = "valid" | "budget" | "semantic" | "injected" | "stateful" | "uncertain";

export const scenarioLabels: Record<ScenarioKey, { title: string; description: string }> = {
  valid: { title: "Valid itinerary", description: "Refundable, economy, nonstop, S$840" },
  budget: { title: "Budget breach", description: "Matching itinerary at S$960" },
  semantic: { title: "Semantic substitution", description: "Cheaper, but explicitly non-refundable" },
  injected: { title: "Injected add-on", description: "Flight plus an unrelated gift card subscription" },
  stateful: { title: "Cumulative breach", description: "Two S$500 fulfillments against S$900 total" },
  uncertain: { title: "Missing evidence", description: "Refundability is not established" },
};

function cart(
  key: string,
  amountMinor: number,
  refundable: boolean | undefined,
  extra?: string,
): CartEvidence {
  const flightAmount = amountMinor - (extra ? 1000 : 0);
  const attributes: Record<string, unknown> = {
    cabin: "economy",
    stops: 0,
    origin: "SIN",
    destination: "TYO",
    outbound_date: "2026-09-07",
    return_date: "2026-09-10",
  };
  if (refundable !== undefined) attributes.refundable = refundable;
  const label = refundable === true ? "Refundable" : refundable === false ? "Non-refundable" : "Return";
  const lineItems = [
    {
      line_item_id: `li_${key}_flight`,
      description: `${label} economy airfare SIN to TYO`,
      quantity: 1,
      amount_minor: flightAmount,
      attributes,
    },
  ];
  if (extra) {
    lineItems.push({
      line_item_id: `li_${key}_extra`,
      description: extra,
      quantity: 1,
      amount_minor: 1000,
      attributes: {},
    });
  }
  return {
    schema_version: "1.0",
    cart_id: `cart_${key}_${Date.now()}`,
    merchant_id: "merchant_air_demo",
    merchant_category: "AIRLINE",
    evidence_source: "SIMULATED_MERCHANT_SIGNED_CART",
    evidence_trust: "trusted",
    currency: "SGD",
    total_amount_minor: amountMinor,
    line_items: lineItems,
    created_at: new Date().toISOString(),
    evidence_reference: `merchant_signature_${key}_${Date.now()}`,
  };
}

export function scenarioCart(key: ScenarioKey, statefulPart: 1 | 2 = 1): CartEvidence {
  switch (key) {
    case "valid":
      return cart("valid", 84000, true);
    case "budget":
      return cart("budget", 96000, true);
    case "semantic":
      return cart("semantic", 78000, false);
    case "injected":
      return cart("injected", 85000, true, "Unrelated gift card subscription");
    case "stateful":
      return cart(`stateful_${statefulPart}`, 50000, true);
    case "uncertain":
      return cart("uncertain", 81000, undefined);
  }
}
