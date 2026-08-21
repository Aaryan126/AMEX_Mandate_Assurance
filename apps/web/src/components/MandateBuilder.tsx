import type { FormEvent } from "react";
import type { MandateProposal } from "@/lib/types";

type Props = {
  objective: string;
  onObjectiveChange: (value: string) => void;
  onInterpret: () => void;
  onConfirm: () => void;
  proposal: MandateProposal | null;
  warnings: string[];
  busy: boolean;
  confirmLabel?: string;
  modificationNotice?: string | null;
};

function formatDate(value: unknown) {
  if (typeof value !== "string") return String(value);
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en-SG", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function formatConstraintValue(constraint: MandateProposal["constraints"][number]) {
  if (constraint.amount_minor != null) {
    return `${constraint.currency} ${(constraint.amount_minor / 100).toLocaleString("en-SG")}`;
  }
  if (Array.isArray(constraint.value)) return constraint.value.join(", ");
  if (constraint.value && typeof constraint.value === "object") {
    const value = constraint.value as Record<string, unknown>;
    if (constraint.type === "route") return `${String(value.origin)} → ${String(value.destination)}`;
    if (constraint.type === "travel_dates") {
      return `${formatDate(value.outbound_date)} → ${formatDate(value.return_date)}`;
    }
    return Object.entries(value)
      .map(([key, item]) => `${key.replaceAll("_", " ")}: ${String(item)}`)
      .join(", ");
  }
  return String(constraint.value ?? constraint.operator);
}

export function MandateBuilder({
  objective,
  onObjectiveChange,
  onInterpret,
  onConfirm,
  proposal,
  warnings,
  busy,
  confirmLabel = "Confirm & authenticate",
  modificationNotice = null,
}: Props) {
  function submit(event: FormEvent) {
    event.preventDefault();
    onInterpret();
  }

  return (
    <section className="panel mandate-panel" aria-labelledby="mandate-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">01 · Authenticated intent</p>
          <h2 id="mandate-title">Define the mandate</h2>
        </div>
        <span className={`status-chip ${proposal ? "ready" : "idle"}`}>
          {proposal ? "Ready to confirm" : "Draft"}
        </span>
      </div>

      <form onSubmit={submit}>
        <label htmlFor="objective">What should the agent purchase?</label>
        <textarea
          id="objective"
          value={objective}
          onChange={(event) => onObjectiveChange(event.target.value)}
          rows={5}
          disabled={busy}
        />
        <div className="button-row">
          <button className="button primary" type="submit" disabled={busy || objective.length < 10}>
            {busy ? "Working…" : "Interpret mandate"}
          </button>
          {proposal && (
            <button className="button confirm" type="button" onClick={onConfirm} disabled={busy}>
              {confirmLabel}
            </button>
          )}
        </div>
      </form>

      {modificationNotice && (
        <div className="notice modification" role="status">
          {modificationNotice}
        </div>
      )}

      {warnings.length > 0 && (
        <div className="notice warning" role="status">
          {warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}

      {proposal && (
        <div className="constraint-list" aria-label="Interpreted constraints">
          {proposal.constraints.map((constraint) => (
            <article className="constraint" key={constraint.constraint_id}>
              <span>{constraint.type.replaceAll("_", " ")}</span>
              <strong>{formatConstraintValue(constraint)}</strong>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
