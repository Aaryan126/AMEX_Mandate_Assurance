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
};

export function MandateBuilder({
  objective,
  onObjectiveChange,
  onInterpret,
  onConfirm,
  proposal,
  warnings,
  busy,
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
              Confirm & authenticate
            </button>
          )}
        </div>
      </form>

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
              <strong>
                {constraint.amount_minor != null
                  ? `${constraint.currency} ${(constraint.amount_minor / 100).toLocaleString()}`
                  : Array.isArray(constraint.value)
                    ? constraint.value.join(", ")
                    : String(constraint.value ?? constraint.operator)}
              </strong>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
