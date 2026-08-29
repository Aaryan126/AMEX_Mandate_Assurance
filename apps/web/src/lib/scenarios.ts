export type ScenarioKey = "valid" | "budget" | "semantic" | "injected" | "stateful" | "uncertain";

export const guidedScenarioKeys: ScenarioKey[] = ["valid", "semantic", "injected"];

export const scenarioLabels: Record<ScenarioKey, { title: string; description: string }> = {
  valid: { title: "Valid itinerary", description: "Refundable, economy, nonstop, S$840" },
  budget: { title: "Budget breach", description: "Matching itinerary at S$960" },
  semantic: { title: "Semantic substitution", description: "Cheaper, but explicitly non-refundable" },
  injected: { title: "Injected add-on", description: "Flight plus an unrelated gift card subscription" },
  stateful: { title: "Cumulative breach", description: "Two S$500 fulfillments against S$900 total" },
  uncertain: { title: "Missing evidence", description: "Refundability is not established" },
};
