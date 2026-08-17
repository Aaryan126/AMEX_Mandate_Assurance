import type { Decision } from "@/lib/types";

type Props = {
  decision: Decision | null;
  onResolve: (action: "APPROVE_ONCE" | "DECLINE") => void;
  busy: boolean;
};

const treatmentCopy = {
  APPROVE: { label: "Approved", symbol: "✓" },
  STEP_UP: { label: "Confirmation needed", symbol: "?" },
  HOLD: { label: "Held for protection", symbol: "!" },
};

export function DecisionPanel({ decision, onResolve, busy }: Props) {
  if (!decision) {
    return (
      <section className="panel decision-empty" aria-labelledby="decision-title">
        <p className="eyebrow">03 · Policy treatment</p>
        <h2 id="decision-title">Decision evidence will appear here</h2>
        <p>Rules, semantic evidence, model versions, and policy reasons remain visible and auditable.</p>
      </section>
    );
  }

  const treatment = treatmentCopy[decision.treatment];
  return (
    <section
      className={`panel decision-panel treatment-${decision.treatment.toLowerCase()}`}
      aria-labelledby="decision-title"
      aria-live="polite"
    >
      <div className="decision-lead">
        <span className="decision-symbol" aria-hidden="true">
          {treatment.symbol}
        </span>
        <div>
          <p className="eyebrow">03 · Policy treatment</p>
          <h2 id="decision-title">{treatment.label}</h2>
          <p>{decision.card_member_explanation}</p>
        </div>
        <div className="risk-score">
          <strong>{Math.round(decision.risk_probability * 100)}%</strong>
          <span>deviation risk</span>
        </div>
      </div>

      {decision.reason_codes.length > 0 && (
        <div className="reason-list" aria-label="Decision reasons">
          {decision.reason_codes.map((reason) => (
            <code key={reason}>{reason}</code>
          ))}
        </div>
      )}

      <details>
        <summary>Inspect decision evidence</summary>
        <div className="evidence-table" role="table" aria-label="Rule results">
          {decision.rule_results.map((rule) => (
            <div className="evidence-row" role="row" key={rule.rule_id}>
              <span role="cell">{rule.rule_id.replaceAll("_", " ")}</span>
              <strong role="cell" className={`rule-${rule.status.toLowerCase()}`}>
                {rule.status}
              </strong>
            </div>
          ))}
        </div>
      </details>

      {decision.treatment === "STEP_UP" && (
        <div className="button-row resolution-actions">
          <button className="button confirm" onClick={() => onResolve("APPROVE_ONCE")} disabled={busy}>
            Approve once
          </button>
          <button className="button secondary" onClick={() => onResolve("DECLINE")} disabled={busy}>
            Decline
          </button>
        </div>
      )}
    </section>
  );
}

