"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type AnnotationItem, type AnnotationProgress, type AnnotationReview } from "@/lib/api";

const deviations: AnnotationReview["deviation"][] = ["MATCH", "AMBIGUOUS", "VIOLATION"];
const treatments: AnnotationReview["expected_treatment"][] = ["APPROVE", "STEP_UP", "HOLD"];
const semanticLabels: AnnotationReview["semantic_label"][] = ["ENTAILMENT", "NEUTRAL", "CONTRADICTION"];

export function AnnotationWorkspace() {
  const [reviewerId, setReviewerId] = useState("");
  const [item, setItem] = useState<AnnotationItem | null>(null);
  const [progress, setProgress] = useState<AnnotationProgress | null>(null);
  const [deviation, setDeviation] = useState<AnnotationReview["deviation"]>("MATCH");
  const [treatment, setTreatment] = useState<AnnotationReview["expected_treatment"]>("APPROVE");
  const [semanticLabel, setSemanticLabel] = useState<AnnotationReview["semantic_label"]>("ENTAILMENT");
  const [violationTypes, setViolationTypes] = useState("");
  const [confidence, setConfidence] = useState(0.8);
  const [notes, setNotes] = useState("");
  const [adjudicationMode, setAdjudicationMode] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refreshProgress = useCallback(async () => {
    try {
      setProgress(await api.annotationProgress());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load annotation progress");
    }
  }, []);

  useEffect(() => {
    void refreshProgress();
  }, [refreshProgress]);

  async function loadNext() {
    if (reviewerId.trim().length < 2) {
      setError("Enter a reviewer ID with at least two characters.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      setItem(await api.nextAnnotation(reviewerId.trim(), adjudicationMode));
      setDeviation("MATCH");
      setTreatment("APPROVE");
      setSemanticLabel("ENTAILMENT");
      setViolationTypes("");
      setConfidence(0.8);
      setNotes("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load the review queue");
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!item) return;
    setBusy(true);
    setError("");
    try {
      const review = {
        reviewer_id: reviewerId.trim(),
        deviation,
        semantic_label: semanticLabel,
        expected_treatment: treatment,
        violation_types: violationTypes.split(",").map((value) => value.trim()).filter(Boolean),
        confidence,
        notes,
      };
      if (item.needs_adjudication) {
        await api.adjudicateAnnotation(item.example.identity.example_id, review);
      } else {
        await api.submitAnnotation(item.example.identity.example_id, review);
      }
      await refreshProgress();
      setItem(await api.nextAnnotation(reviewerId.trim(), adjudicationMode));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save this review");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="annotation-shell">
      <header className="annotation-header">
        <div>
          <p className="eyebrow">Internal dataset operations</p>
          <h1>Human review queue</h1>
          <p>Two independent labels per example; disagreements are sent to expert adjudication.</p>
        </div>
        {progress && (
          <div className="annotation-progress" aria-label="Annotation progress">
            <strong>{progress.agreed + progress.adjudicated}</strong>
            <span>resolved of {progress.total}</span>
          </div>
        )}
      </header>

      <section className="annotation-toolbar" aria-label="Reviewer controls">
        <label htmlFor="reviewer-id">Reviewer ID</label>
        <input
          id="reviewer-id"
          value={reviewerId}
          onChange={(event) => setReviewerId(event.target.value)}
          placeholder="reviewer-name"
        />
        <label className="annotation-mode">
          <input
            type="checkbox"
            checked={adjudicationMode}
            onChange={(event) => setAdjudicationMode(event.target.checked)}
          />
          Adjudication queue
        </label>
        <button className="button primary" onClick={loadNext} disabled={busy}>Load next example</button>
      </section>

      {error && <p className="annotation-error" role="alert">{error}</p>}

      {item ? (
        <div className="annotation-grid">
          <article className="panel annotation-evidence">
            <p className="eyebrow">Mandate</p>
            <h2>{item.example.mandate.objective_text}</h2>
            <dl>
              <div><dt>Locale</dt><dd>{item.example.context.locale}</dd></div>
              <div><dt>Dataset</dt><dd>{item.example.provenance.source_dataset}</dd></div>
              <div><dt>Origin</dt><dd>{item.example.provenance.evidence_origin}</dd></div>
              <div><dt>Prior reviews</dt><dd>{item.completed_reviews}</dd></div>
            </dl>
            <h3>Proposed cart</h3>
            <ul>
              {item.example.cart.line_items.map((line, index) => (
                <li key={`${line.description}-${index}`}>
                  <strong>{line.description}</strong>
                  {line.evidence_text && <span>{line.evidence_text}</span>}
                </li>
              ))}
            </ul>
            <p className="annotation-total">
              Total: {item.example.cart.total_amount_minor} {item.example.cart.currency} minor units
            </p>
            <details>
              <summary>Structured constraints</summary>
              <pre>{JSON.stringify(item.example.mandate.constraints, null, 2)}</pre>
            </details>
            {item.example.audit_context && (
              <details open>
                <summary>Precomputed deterministic checks</summary>
                <p>{item.example.audit_context.review_scope}</p>
                <p><strong>Deterministic treatment:</strong> {item.example.audit_context.deterministic_treatment}</p>
                <pre>{JSON.stringify(item.example.audit_context.commercial_rule_results, null, 2)}</pre>
              </details>
            )}
          </article>

          <form className="panel annotation-form" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
            {item.needs_adjudication && (
              <div className="notice warning">
                <p>Two reviewers disagreed. This label will be the adjudicated result.</p>
                <details open>
                  <summary>Independent reviewer decisions</summary>
                  <pre>{JSON.stringify(item.prior_reviews, null, 2)}</pre>
                </details>
              </div>
            )}
            <fieldset>
              <legend>Semantic relationship: mandate to evidence</legend>
              <div className="annotation-options">
                {semanticLabels.map((value) => (
                  <label key={value}>
                    <input type="radio" name="semantic-label" checked={semanticLabel === value} onChange={() => setSemanticLabel(value)} />
                    {value}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend>Does the cart comply with the mandate?</legend>
              <div className="annotation-options">
                {deviations.map((value) => (
                  <label key={value}>
                    <input type="radio" name="deviation" checked={deviation === value} onChange={() => setDeviation(value)} />
                    {value}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend>Expected treatment</legend>
              <div className="annotation-options">
                {treatments.map((value) => (
                  <label key={value}>
                    <input type="radio" name="treatment" checked={treatment === value} onChange={() => setTreatment(value)} />
                    {value}
                  </label>
                ))}
              </div>
            </fieldset>
            <label htmlFor="violation-types">Violation reason codes (comma-separated)</label>
            <input
              id="violation-types"
              value={violationTypes}
              onChange={(event) => setViolationTypes(event.target.value)}
              placeholder="e.g. REQUIRED_ATTRIBUTE_EVIDENCE_MISSING"
            />
            <label htmlFor="confidence">Confidence: {confidence.toFixed(1)}</label>
            <input id="confidence" type="range" min="0" max="1" step="0.1" value={confidence} onChange={(event) => setConfidence(Number(event.target.value))} />
            <label htmlFor="notes">Reviewer notes</label>
            <textarea id="notes" rows={5} value={notes} onChange={(event) => setNotes(event.target.value)} />
            <button className="button confirm" type="submit" disabled={busy}>
              {item.needs_adjudication ? "Adjudicate and continue" : "Save and continue"}
            </button>
          </form>
        </div>
      ) : (
        <section className="panel annotation-empty">
          <h2>{reviewerId ? "No example loaded" : "Identify the reviewer to begin"}</h2>
          <p>The service is local-only and is disabled unless ACE_ANNOTATION_ENABLED is set.</p>
        </section>
      )}
    </main>
  );
}
