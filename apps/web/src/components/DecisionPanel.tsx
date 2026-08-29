import type { Decision, ResolutionAction } from "@/lib/types";

type Props = {
  decision: Decision | null;
  onResolve: (action: ResolutionAction) => void;
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
        <div className="model-score-detail" aria-label="Model intervention score">
          <div>
            <strong>{(decision.structured_risk_probability * 100).toFixed(1)}%</strong>
            <span>{decision.model_versions.calibrator ? "calibrated model intervention score" : "risk signal"}</span>
          </div>
          {decision.model_versions.model_step_up_threshold != null && (
            <small>
              The model escalates at {(decision.model_versions.model_step_up_threshold * 100).toFixed(1)}%.
              Rules and semantic contradictions can independently require treatment.
            </small>
          )}
        </div>
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
        {decision.semantic_results.length > 0 && (
          <>
            <p className="evidence-subheading">Semantic NLI evidence</p>
            <div className="evidence-table" role="table" aria-label="Semantic model results">
              {decision.semantic_results.map((result) => (
                <div className="evidence-row" role="row" key={result.constraint_id}>
                  <span role="cell">{result.constraint_id.replaceAll("_", " ")}</span>
                  <span role="cell" className="semantic-scores">
                    <code>C {(result.contradiction * 100).toFixed(1)}%</code>
                    <code>E {(result.entailment * 100).toFixed(1)}%</code>
                    <code>N {(result.neutral * 100).toFixed(1)}%</code>
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
        <div className="runtime-contract" aria-label="Decision runtime contract">
          <span>Mode <code>{decision.model_versions.runtime_mode}</code></span>
          <span>Semantic <code>{decision.model_versions.semantic}</code></span>
          <span>Policy <code>{decision.model_versions.policy}</code></span>
          <span>
            CatBoost{" "}
            <code>{decision.model_versions.catboost ?? "deterministic fallback"}</code>
          </span>
          <span>Calibration <code>{decision.model_versions.calibrator ?? "not active"}</code></span>
          {decision.model_versions.model_step_up_threshold != null && (
            <span>
              Step-up threshold <code>{decision.model_versions.model_step_up_threshold.toFixed(4)}</code>
            </span>
          )}
          {decision.model_versions.candidate_status && (
            <span>Candidate gate <code>{decision.model_versions.candidate_status}</code></span>
          )}
          <span>
            Cart signature{" "}
            <code>
              {decision.rule_results.some(
                (rule) => rule.rule_id === "trusted_evidence" && rule.status === "PASS",
              )
                ? "Ed25519 verified"
                : "not verified"}
            </code>
          </span>
        </div>
      </details>

      {decision.treatment === "STEP_UP" && (
        <div className="button-row resolution-actions">
          <button className="button confirm" onClick={() => onResolve("APPROVE_ONCE")} disabled={busy}>
            Approve once
          </button>
          <button className="button secondary" onClick={() => onResolve("MODIFY_MANDATE")} disabled={busy}>
            Modify mandate
          </button>
          <button className="button secondary" onClick={() => onResolve("DECLINE")} disabled={busy}>
            Decline
          </button>
        </div>
      )}
    </section>
  );
}
