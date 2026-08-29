"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ScenarioKey } from "@/lib/scenarios";
import type {
  AuditEvent,
  CartEvidence,
  Decision,
  EvaluationSummary,
  MandateProposal,
  MandateView,
  ResolutionAction,
  RuntimeStatus,
} from "@/lib/types";
import { AuditTimeline } from "./AuditTimeline";
import { DecisionPanel } from "./DecisionPanel";
import { EvaluationDashboard } from "./EvaluationDashboard";
import { GuidedTour } from "./GuidedTour";
import { MandateBuilder } from "./MandateBuilder";
import { OutcomeComparison } from "./OutcomeComparison";
import { ScenarioPicker, type ScenarioStep } from "./ScenarioPicker";

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
  const [activeScenario, setActiveScenario] = useState<ScenarioKey | null>(null);
  const [completedScenarios, setCompletedScenarios] = useState<ScenarioKey[]>([]);
  const [scenarioSteps, setScenarioSteps] = useState<ScenarioStep[]>([]);
  const [modifyingDecisionId, setModifyingDecisionId] = useState<string | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [guidedMode, setGuidedMode] = useState(false);
  const [activeCart, setActiveCart] = useState<CartEvidence | null>(null);

  useEffect(() => {
    api.runtimeStatus().then(setRuntime).catch(() => setRuntime(null));
  }, []);

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
    setScenarioSteps([]);
    setActiveCart(null);
    if (!modifyingDecisionId) {
      setActiveScenario(null);
      setCompletedScenarios([]);
    }
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
      if (modifyingDecisionId) {
        const result = await api.resolve(modifyingDecisionId, "MODIFY_MANDATE", proposal);
        if (!result.new_mandate_id) throw new Error("The modified mandate was not created.");
        const view = await api.mandate(result.new_mandate_id);
        setMandate(view);
        setDecision(null);
        setModifyingDecisionId(null);
        setResolution("Modified mandate confirmed and authenticated.");
        await refreshAudit(view.mandate.mandate_id);
        return;
      }
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
    if (!mandate || !proposal) return;
    setBusy(true);
    setError(null);
    setResolution(null);
    setActiveScenario(scenario);
    setScenarioSteps([]);
    try {
      const suffix = globalThis.crypto?.randomUUID?.().replaceAll("-", "").slice(0, 12) ?? `${Date.now()}`;
      const isolatedProposal: MandateProposal = {
        ...proposal,
        mandate_id: `mdt_demo_${suffix}`,
        mandate_version: 1,
      };
      const scenarioMandate = await api.confirm(isolatedProposal);
      setMandate(scenarioMandate);

      let result: Decision;
      if (scenario === "stateful") {
        const firstCart = await api.demoCart("stateful", 1);
        const first = await api.evaluate(scenarioMandate.mandate.mandate_id, firstCart);
        if (first.treatment !== "APPROVE") throw new Error("The first stateful fulfillment did not approve.");
        const secondCart = await api.demoCart("stateful", 2);
        result = await api.evaluate(scenarioMandate.mandate.mandate_id, secondCart);
        setActiveCart(secondCart);
        setScenarioSteps([
          { label: "First fulfillment", amountMinor: firstCart.total_amount_minor, treatment: first.treatment },
          { label: "Second fulfillment", amountMinor: secondCart.total_amount_minor, treatment: result.treatment },
        ]);
      } else {
        const scenarioEvidence = await api.demoCart(scenario);
        result = await api.evaluate(scenarioMandate.mandate.mandate_id, scenarioEvidence);
        setActiveCart(scenarioEvidence);
        setScenarioSteps([
          { label: "Proposed transaction", amountMinor: scenarioEvidence.total_amount_minor, treatment: result.treatment },
        ]);
      }
      setDecision(result);
      setCompletedScenarios((current) => current.includes(scenario) ? current : [...current, scenario]);
      await refreshAudit(scenarioMandate.mandate.mandate_id);
    } catch (value) {
      setError(value instanceof Error ? value.message : "Decision evaluation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleResolve(action: ResolutionAction) {
    if (!decision || !mandate) return;
    if (action === "MODIFY_MANDATE") {
      setModifyingDecisionId(decision.decision_id);
      setProposal(null);
      setMandate(null);
      setDecision(null);
      setEvents([]);
      setScenarioSteps([]);
      setActiveCart(null);
      setResolution("Revise the objective, interpret it again, then confirm the modified mandate.");
      return;
    }
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

  function handleReset() {
    setObjective(DEFAULT_OBJECTIVE);
    setProposal(null);
    setMandate(null);
    setWarnings([]);
    setDecision(null);
    setEvents([]);
    setBusy(false);
    setError(null);
    setResolution(null);
    setEvaluation(null);
    setActiveScenario(null);
    setCompletedScenarios([]);
    setScenarioSteps([]);
    setModifyingDecisionId(null);
    setGuidedMode(false);
    setActiveCart(null);
  }

  function handleStartGuided() {
    setGuidedMode(true);
    if (!proposal && !busy) void handleInterpret();
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
          <span className="prototype-label">
            {runtime?.ready
              ? `${runtime.runtime_mode.replaceAll("_", " ")} · verified runtime`
              : "Development v3 · simulated prototype"}
          </span>
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
        {runtime && (
          <div className="runtime-strip" aria-label="Active runtime contract">
            <span>Semantic <code>{runtime.semantic}</code></span>
            <span>Structured <code>{runtime.catboost ?? "deterministic fallback"}</code></span>
            <span>Calibration <code>{runtime.calibrator ?? "not active"}</code></span>
            <span>Evidence <code>Ed25519 required</code></span>
          </div>
        )}
      </header>

      <section className="theme-value-strip" aria-label="Business value">
        <article>
          <strong>Protection</strong>
          <span>Stops prohibited, manipulated, and cumulative mandate violations.</span>
        </article>
        <article>
          <strong>Growth</strong>
          <span>Recovers uncertain purchases through confirmation instead of blanket blocking.</span>
        </article>
        <article>
          <strong>Productivity</strong>
          <span>Automates evidence comparison and produces an audit-ready decision trail.</span>
        </article>
      </section>

      {error && <div className="global-message error" role="alert">{error}</div>}
      {resolution && <div className="global-message success" role="status">{resolution}</div>}

      <GuidedTour
        active={guidedMode}
        busy={busy}
        hasProposal={proposal != null}
        hasMandate={mandate != null}
        completedScenarios={completedScenarios}
        onStart={handleStartGuided}
        onConfirm={handleConfirm}
        onRun={handleRun}
        onExit={() => setGuidedMode(false)}
      />

      <div className="workspace-grid">
        <MandateBuilder
          objective={objective}
          onObjectiveChange={setObjective}
          onInterpret={handleInterpret}
          onConfirm={handleConfirm}
          proposal={proposal}
          warnings={warnings}
          busy={busy}
          confirmLabel={modifyingDecisionId ? "Confirm modified mandate" : "Confirm & authenticate"}
          modificationNotice={modifyingDecisionId ? "You are replacing the stepped-up mandate. Update the objective before confirming." : null}
        />
        <ScenarioPicker
          onRun={handleRun}
          busy={busy}
          disabled={!mandate}
          activeScenario={activeScenario}
          completedScenarios={completedScenarios}
          steps={scenarioSteps}
          onReset={handleReset}
          guidedMode={guidedMode}
          onExitGuided={() => setGuidedMode(false)}
        />
        <OutcomeComparison
          scenario={activeScenario}
          proposal={proposal}
          cart={activeCart}
          decision={decision}
        />
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
