import type {
  AuditEvent,
  CartEvidence,
  Decision,
  EvaluationSummary,
  MandateProposal,
  MandateView,
  ResolutionAction,
  ResolutionResponse,
  RuntimeStatus,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ApiError = { detail?: string; error?: { message?: string; code?: string } };

export type AnnotationItem = {
  example: {
    identity: { example_id: string };
    mandate: { objective_text: string; constraints: Array<Record<string, unknown>> };
    cart: {
      total_amount_minor: number;
      currency: string;
      line_items: Array<{ description: string; evidence_text?: string }>;
    };
    context: { locale: string; domain: string };
    provenance: { source_dataset: string; evidence_origin: string; transformation: string };
    audit_context?: {
      policy_version: string;
      deterministic_treatment: "APPROVE" | "STEP_UP" | "HOLD";
      review_scope: string;
      commercial_rule_results: Array<{
        rule_id: string;
        status: string;
        reason_code: string | null;
        observed_value: unknown;
        expected_value: unknown;
      }>;
    };
  };
  completed_reviews: number;
  needs_adjudication: boolean;
  prior_reviews: AnnotationReview[];
};

export type AnnotationProgress = {
  total: number;
  unreviewed: number;
  single_review: number;
  agreed: number;
  needs_adjudication: number;
  adjudicated: number;
};

export type AnnotationReview = {
  reviewer_id: string;
  deviation: "MATCH" | "VIOLATION" | "AMBIGUOUS";
  semantic_label: "ENTAILMENT" | "CONTRADICTION" | "NEUTRAL";
  expected_treatment: "APPROVE" | "STEP_UP" | "HOLD";
  violation_types: string[];
  confidence: number;
  notes: string;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiError;
    throw new Error(body.error?.message ?? body.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function idempotencyKey(scope: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  return `${scope}-${suffix}`;
}

export const api = {
  interpret(objectiveText: string) {
    return request<{ proposal: MandateProposal; warnings: string[] }>("/v1/mandates/interpret", {
      method: "POST",
      body: JSON.stringify({ objective_text: objectiveText }),
    });
  },
  confirm(proposal: MandateProposal) {
    return request<MandateView>("/v1/mandates", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("confirm") },
      body: JSON.stringify({ proposal, confirmed: true }),
    });
  },
  mandate(mandateId: string) {
    return request<MandateView>(`/v1/mandates/${encodeURIComponent(mandateId)}`);
  },
  evaluate(mandateId: string, cart: CartEvidence) {
    return request<Decision>("/v1/decisions/evaluate", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("evaluate") },
      body: JSON.stringify({ mandate_id: mandateId, cart }),
    });
  },
  resolve(decisionId: string, action: ResolutionAction, modifiedProposal?: MandateProposal) {
    return request<ResolutionResponse>(`/v1/decisions/${decisionId}/resolve`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("resolve") },
      body: JSON.stringify({ action, modified_proposal: modifiedProposal }),
    });
  },
  audit(sessionId: string) {
    return request<{ events: AuditEvent[] }>(`/v1/sessions/${sessionId}/audit`);
  },
  evaluationSummary() {
    return request<EvaluationSummary>("/v1/evaluation/summary");
  },
  runtimeStatus() {
    return request<RuntimeStatus>("/v1/runtime/status");
  },
  demoCart(scenario: string, statefulPart: 1 | 2 = 1) {
    return request<CartEvidence>(
      `/v1/demo/carts/${encodeURIComponent(scenario)}?stateful_part=${statefulPart}`,
    );
  },
  nextAnnotation(reviewerId: string, adjudicationOnly = false) {
    const query = new URLSearchParams({
      reviewer_id: reviewerId,
      adjudication_only: String(adjudicationOnly),
    });
    return request<AnnotationItem | null>(`/internal/annotations/next?${query}`);
  },
  annotationProgress() {
    return request<AnnotationProgress>("/internal/annotations/progress");
  },
  submitAnnotation(exampleId: string, review: AnnotationReview) {
    return request<{ status: string }>(
      `/internal/annotations/${encodeURIComponent(exampleId)}/reviews`,
      { method: "POST", body: JSON.stringify(review) },
    );
  },
  adjudicateAnnotation(exampleId: string, review: AnnotationReview) {
    return request<{ status: string }>(
      `/internal/annotations/${encodeURIComponent(exampleId)}/adjudicate`,
      {
        method: "POST",
        body: JSON.stringify({ ...review, adjudicator_id: review.reviewer_id }),
      },
    );
  },
};
