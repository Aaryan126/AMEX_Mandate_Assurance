"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { scenarioCart, type ScenarioKey } from "@/lib/scenarios";
import type {
  AuditEvent,
  Decision,
  EvaluationSummary,
  MandateProposal,
  MandateView,
} from "@/lib/types";
import { AuditTimeline } from "./AuditTimeline";
import { DecisionPanel } from "./DecisionPanel";
import { EvaluationDashboard } from "./EvaluationDashboard";
import { MandateBuilder } from "./MandateBuilder";
import { ScenarioPicker } from "./ScenarioPicker";

export const DEFAULT_OBJECTIVE =
  "Book a refundable economy flight from Singapore to Tokyo, departing 7 September and returning 10 September, nonstop if available, total fare under S$900. Do not purchase add-ons.";

export function AssuranceWorkspace() {
  const [objective, setObjective] = useState(DEFAULT_OBJECTIVE);
  const [proposal, setProposal] = useState<MandateProposal | null>(null);
  const [mandate, setMandate] = useState<MandateView | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolution, setResolution] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationSummary | null>(null);

  async function refreshAudit(mandateId: string) {
    const timeline = await api.audit(mandateId);
    setEvents(timeline.events);
  }

  async function handleInterpret() {
    setBusy(true);
    setError(null);
    setMandate(null);
    setDecision(null);
    setEvents([]);
    setResolution(null);
    try {
      const response = await api.interpret(objective);
      setProposal({ ...response.proposal, max_fulfillments: 2 });
      setWarnings(response.warnings);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Interpretation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    try {
      const view = await api.confirm(proposal);
      setMandate(view);
      await refreshAudit(view.mandate.mandate_id);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRun(scenario: ScenarioKey) {
    if (!mandate) return;
    setBusy(true);
    setError(null);
    setResolution(null);
    try {
      let result: Decision;
      if (scenario === "stateful") {
        const first = await api.evaluate(mandate.mandate.mandate_id, scenarioCart("stateful", 1));
        if (first.treatment !== "APPROVE") throw new Error("The first stateful fulfillment did not approve.");
        result = await api.evaluate(mandate.mandate.mandate_id, scenarioCart("stateful", 2));
      } else {
        result = await api.evaluate(mandate.mandate.mandate_id, scenarioCart(scenario));
      }
      setDecision(result);
      await refreshAudit(mandate.mandate.mandate_id);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Decision evaluation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleResolve(action: "APPROVE_ONCE" | "DECLINE") {
    if (!decision || !mandate) return;
    setBusy(true);
    setError(null);
    try {
      await api.resolve(decision.decision_id, action);
      setResolution(action === "APPROVE_ONCE" ? "Approved once by the Card Member." : "Declined by the Card Member.");
      await refreshAudit(mandate.mandate.mandate_id);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Resolution failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleLoadEvaluation() {
    setBusy(true);
    setError(null);
    try {
      setEvaluation(await api.evaluationSummary());
    } catch (value) {
      setError(value instanceof Error ? value.message : "Evaluation results could not be loaded.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <header className="hero">
        <nav aria-label="Product">
          <div className="brand-mark" aria-hidden="true">A</div>
          <div className="brand-copy">
            <strong>ACE</strong>
            <span>Mandate Assurance</span>
          </div>
          <span className="prototype-label">Simulated prototype</span>
        </nav>
        <div className="hero-content">
          <div>
            <p className="eyebrow">Action-boundary protection</p>
            <h1>Authenticate the agent.<br /><em>Verify the outcome.</em></h1>
          </div>
          <p className="hero-summary">
            Every proposed cart—and its cumulative effect—is checked against the Card Member&apos;s
            confirmed intent before payment treatment.
          </p>
        </div>
        <div className="trust-strip" aria-label="Assurance layers">
          <span><i /> Authenticated intent</span>
          <span><i /> Merchant-signed evidence</span>
          <span><i /> Stateful policy</span>
          <span><i /> Versioned audit</span>
        </div>
      </header>

      {error && <div className="global-message error" role="alert">{error}</div>}
      {resolution && <div className="global-message success" role="status">{resolution}</div>}

      <div className="workspace-grid">
        <MandateBuilder
          objective={objective}
          onObjectiveChange={setObjective}
          onInterpret={handleInterpret}
          onConfirm={handleConfirm}
          proposal={proposal}
          warnings={warnings}
          busy={busy}
        />
        <ScenarioPicker onRun={handleRun} busy={busy} disabled={!mandate} />
        <DecisionPanel decision={decision} onResolve={handleResolve} busy={busy} />
        <AuditTimeline events={events} />
        <EvaluationDashboard summary={evaluation} onLoad={handleLoadEvaluation} busy={busy} />
      </div>

      <footer>
        <span>ACE Mandate Assurance · APAC-ready design</span>
        <span>No real Card Member, merchant, or Amex production data</span>
      </footer>
    </main>
  );
}
