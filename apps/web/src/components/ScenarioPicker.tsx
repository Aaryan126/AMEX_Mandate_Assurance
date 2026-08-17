import { scenarioLabels, type ScenarioKey } from "@/lib/scenarios";

type Props = {
  onRun: (scenario: ScenarioKey) => void;
  busy: boolean;
  disabled: boolean;
};

export function ScenarioPicker({ onRun, busy, disabled }: Props) {
  return (
    <section className="panel" aria-labelledby="evidence-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">02 · Trusted cart evidence</p>
          <h2 id="evidence-title">Test an agent outcome</h2>
        </div>
        <span className={`status-chip ${disabled ? "idle" : "trusted"}`}>
          {disabled ? "Awaiting mandate" : "Merchant signed"}
        </span>
      </div>
      <p className="supporting-copy">
        Choose a reproducible transaction. The decision uses merchant-confirmed line items, not the
        agent&apos;s account of its own action.
      </p>
      <div className="scenario-grid">
        {(Object.entries(scenarioLabels) as [ScenarioKey, (typeof scenarioLabels)[ScenarioKey]][]).map(
          ([key, scenario], index) => (
            <button
              className="scenario-card"
              key={key}
              type="button"
              onClick={() => onRun(key)}
              disabled={disabled || busy}
            >
              <span className="scenario-index">{String(index + 1).padStart(2, "0")}</span>
              <strong>{scenario.title}</strong>
              <small>{scenario.description}</small>
            </button>
          ),
        )}
      </div>
    </section>
  );
}

