import type { EvaluationSummary } from "@/lib/types";

type Props = {
  summary: EvaluationSummary | null;
  onLoad: () => void;
  busy: boolean;
};

function percent(value: number | undefined) {
  return value === undefined ? "—" : `${(value * 100).toFixed(2)}%`;
}

function decimal(value: number | undefined) {
  return value === undefined ? "—" : value.toFixed(4);
}

export function EvaluationDashboard({ summary, onLoad, busy }: Props) {
  const statusLabel = summary?.status === "LOCKED_NON_PROMOTABLE"
    ? "Not promotable"
    : summary?.status.replaceAll("_", " ") ?? "Not loaded";
  return (
    <section className="panel evaluation-panel" aria-labelledby="evaluation-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">05 · Development v3 evidence</p>
          <h2 id="evaluation-title">Model and policy evidence</h2>
        </div>
        <span className={`status-chip ${summary ? "warning" : "idle"}`}>
          {statusLabel}
        </span>
      </div>
      {!summary ? (
        <div className="evaluation-empty">
          <p className="supporting-copy">
            Load the locked 1,000-row candidate-selection result. It remains offline development
            evidence; the active runtime contract is shown above and with every decision.
          </p>
          <button className="button secondary" type="button" onClick={onLoad} disabled={busy}>
            Load benchmark results
          </button>
        </div>
      ) : (
        <>
          <div className="metric-grid">
            <article data-gate="failed"><span>Operational recall</span><strong>{percent(summary.metrics.violation_recall)}</strong><small>Goal ≥ 90% · not met</small></article>
            <article data-gate="passed"><span>False step-up</span><strong>{percent(summary.metrics.false_step_up_rate)}</strong><small>Goal ≤ 10% · passed</small></article>
            <article data-gate="passed"><span>False decline</span><strong>{percent(summary.metrics.false_decline_rate)}</strong><small>Goal ≤ 2% · passed</small></article>
            <article><span>PR-AUC</span><strong>{decimal(summary.metrics.pr_auc)}</strong><small>Ranking diagnostic</small></article>
            <article><span>Brier score</span><strong>{decimal(summary.metrics.brier_score)}</strong><small>Lower is better</small></article>
            <article data-gate="passed"><span>Calibration error</span><strong>{decimal(summary.metrics.expected_calibration_error)}</strong><small>Goal ≤ 0.08 · passed</small></article>
            <article data-gate="failed"><span>Supported-family recall</span><strong>{percent(summary.metrics.supported_family_recall)}</strong><small>Goal ≥ 80% · not met</small></article>
          </div>
          <p className="evaluation-caveat">
            Strong ranking and calibration are encouraging, but the two recall gates prevent promotion.
            No real Amex Card Member or transaction data is used.
          </p>
          <div className="benchmark-meta">
            <code>{summary.dataset_version}</code>
            <span>→</span>
            <code>{summary.model_version}</code>
            <span>{Object.keys(summary.attack_families).length} evaluated families · {summary.status}</span>
          </div>
        </>
      )}
    </section>
  );
}
