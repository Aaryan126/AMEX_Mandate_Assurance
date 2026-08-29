import { type ScenarioKey } from "@/lib/scenarios";

type Props = {
  active: boolean;
  busy: boolean;
  hasProposal: boolean;
  hasMandate: boolean;
  completedScenarios: ScenarioKey[];
  onStart: () => void;
  onConfirm: () => void;
  onRun: (scenario: ScenarioKey) => void;
  onExit: () => void;
};

const tourSteps = [
  { label: "Confirm intent", treatment: "AUTHENTICATE" },
  { label: "Matching outcome", treatment: "APPROVE" },
  { label: "Changed term", treatment: "STEP_UP" },
  { label: "Prohibited add-on", treatment: "HOLD" },
];

export function GuidedTour({
  active,
  busy,
  hasProposal,
  hasMandate,
  completedScenarios,
  onStart,
  onConfirm,
  onRun,
  onExit,
}: Props) {
  const validComplete = completedScenarios.includes("valid");
  const semanticComplete = completedScenarios.includes("semantic");
  const injectedComplete = completedScenarios.includes("injected");
  const progress = !hasMandate ? 0 : !validComplete ? 1 : !semanticComplete ? 2 : !injectedComplete ? 3 : 4;

  let actionLabel = "Start 90-second guided demo";
  let action = onStart;
  let instruction = "See how the same authenticated mandate produces approve, confirm, and hold outcomes.";

  if (active && !hasProposal) {
    actionLabel = busy ? "Interpreting mandate…" : "Interpret mandate";
    instruction = "First, turn the Card Member’s request into reviewable, structured constraints.";
  } else if (active && !hasMandate) {
    actionLabel = "Confirm authenticated mandate";
    action = onConfirm;
    instruction = "Review the interpreted terms, then make them authoritative for the agent.";
  } else if (active && !validComplete) {
    actionLabel = "1 · Run matching purchase";
    action = () => onRun("valid");
    instruction = "A matching, well-evidenced outcome should continue with low friction.";
  } else if (active && !semanticComplete) {
    actionLabel = "2 · Change refundability";
    action = () => onRun("semantic");
    instruction = "A cheaper fare changes a required term, so the Card Member stays in control.";
  } else if (active && !injectedComplete) {
    actionLabel = "3 · Inject prohibited add-on";
    action = () => onRun("injected");
    instruction = "A prohibited gift-card subscription requires the current action to stop.";
  } else if (active) {
    actionLabel = "Explore all six scenarios";
    action = onExit;
    instruction = "Tour complete: one mandate, three proportionate treatments, one reproducible audit trail.";
  }

  return (
    <section className={`guided-tour ${active ? "active" : ""}`} aria-label="Guided judge tour">
      <div className="guided-copy">
        <p className="eyebrow">Judge-ready walkthrough</p>
        <h2>{active ? "One mandate. Three proportionate outcomes." : "Understand the system in 90 seconds"}</h2>
        <p>{instruction}</p>
      </div>
      <ol className="guided-progress" aria-label="Guided demo progress">
        {tourSteps.map((step, index) => (
          <li key={step.treatment} data-state={index < progress ? "complete" : index === progress ? "active" : "pending"}>
            <span>{index < progress ? "✓" : index + 1}</span>
            <div>
              <strong>{step.label}</strong>
              <small>{step.treatment}</small>
            </div>
          </li>
        ))}
      </ol>
      <div className="guided-actions">
        <button className="button confirm" type="button" onClick={action} disabled={busy}>
          {actionLabel}
        </button>
        {active && (
          <button className="text-button" type="button" onClick={onExit} disabled={busy}>
            Exit guided mode
          </button>
        )}
      </div>
    </section>
  );
}
