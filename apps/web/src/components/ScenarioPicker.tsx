import { scenarioLabels, type ScenarioKey } from "@/lib/scenarios";
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
}: Props) {
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
        Follow the numbered path or choose any example. Each scenario uses an isolated copy of the
        confirmed mandate; the cumulative example contains its own two-transaction history.
      </p>
      <div className="scenario-grid">
        {(Object.entries(scenarioLabels) as [ScenarioKey, (typeof scenarioLabels)[ScenarioKey]][]).map(
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
