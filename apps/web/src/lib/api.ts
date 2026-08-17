import type {
  AuditEvent,
  CartEvidence,
  Decision,
  EvaluationSummary,
  MandateProposal,
  MandateView,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ApiError = { error?: { message?: string; code?: string } };

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
    throw new Error(body.error?.message ?? `Request failed with status ${response.status}`);
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
  evaluate(mandateId: string, cart: CartEvidence) {
    return request<Decision>("/v1/decisions/evaluate", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("evaluate") },
      body: JSON.stringify({ mandate_id: mandateId, cart }),
    });
  },
  resolve(decisionId: string, action: "APPROVE_ONCE" | "DECLINE") {
    return request(`/v1/decisions/${decisionId}/resolve`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey("resolve") },
      body: JSON.stringify({ action }),
    });
  },
  audit(sessionId: string) {
    return request<{ events: AuditEvent[] }>(`/v1/sessions/${sessionId}/audit`);
  },
  evaluationSummary() {
    return request<EvaluationSummary>("/v1/evaluation/summary");
  },
};
