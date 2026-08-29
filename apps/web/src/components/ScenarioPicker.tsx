import { guidedScenarioKeys, scenarioLabels, type ScenarioKey } from "@/lib/scenarios";
import type { Decision } from "@/lib/types";

export type ScenarioStep = {
  label: string;
  amountMinor: number;
  treatment: Decision["treatment"];
};

type Props = {
  onRun: (scenario: ScenarioKey) => void;
  busy: boolean;
  disabled: boolean;
  activeScenario: ScenarioKey | null;
  completedScenarios: ScenarioKey[];
  steps: ScenarioStep[];
  onReset: () => void;
  guidedMode: boolean;
  onExitGuided: () => void;
};

function amount(value: number) {
  return `S$${(value / 100).toLocaleString("en-SG", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function ScenarioPicker({
  onRun,
  busy,
  disabled,
  activeScenario,
  completedScenarios,
  steps,
  onReset,
  guidedMode,
  onExitGuided,
}: Props) {
  const visibleScenarios = guidedMode
    ? guidedScenarioKeys.map((key) => [key, scenarioLabels[key]] as const)
    : (Object.entries(scenarioLabels) as [ScenarioKey, (typeof scenarioLabels)[ScenarioKey]][]);
  return (
    <section className="panel" aria-labelledby="evidence-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">02 · Trusted cart evidence</p>
          <h2 id="evidence-title">Test an agent outcome</h2>
        </div>
        <div className="panel-actions">
          <span className={`status-chip ${disabled ? "idle" : "trusted"}`}>
            {disabled ? "Awaiting mandate" : "Merchant signed"}
          </span>
          <button className="text-button" type="button" onClick={onReset} disabled={busy}>
            Reset demo
          </button>
        </div>
      </div>
      <p className="supporting-copy">
        {guidedMode
          ? "The judge tour focuses on the three outcomes: approve a match, confirm a changed term, and hold a prohibition."
          : "Choose any example. Each scenario uses an isolated copy of the confirmed mandate; the cumulative example contains its own two-transaction history."}
      </p>
      <div className="scenario-grid">
        {visibleScenarios.map(
          ([key, scenario], index) => (
            <button
              className="scenario-card"
              data-active={activeScenario === key || undefined}
              data-complete={completedScenarios.includes(key) || undefined}
              key={key}
              type="button"
              onClick={() => onRun(key)}
              disabled={disabled || busy}
            >
              <span className="scenario-index">
                {completedScenarios.includes(key) ? "✓" : String(index + 1).padStart(2, "0")}
              </span>
              <strong>{scenario.title}</strong>
              <small>{scenario.description}</small>
            </button>
          ),
        )}
      </div>
      {guidedMode && (
        <button className="text-button scenario-explore" type="button" onClick={onExitGuided} disabled={busy}>
          Show all six scenarios
        </button>
      )}
      {steps.length > 0 && (
        <div className="scenario-trace" aria-label="Scenario transaction sequence" aria-live="polite">
          <span>Transaction sequence</span>
          <ol>
            {steps.map((step, index) => (
              <li key={`${step.label}-${index}`}>
                <span>{step.label}</span>
                <strong>{amount(step.amountMinor)}</strong>
                <code data-treatment={step.treatment}>{step.treatment}</code>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
