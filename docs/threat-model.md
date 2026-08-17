# Prototype Threat Model

## Protected assets and boundary

The protected decision inputs are the authenticated mandate, merchant-confirmed cart evidence, mandate
state, model/policy artifacts, and append-only audit trail. Agent text is an untrusted proposal and cannot
replace merchant evidence.

## Covered threats

- Prompt injection or agent malfunction that produces prohibited, unrelated, or semantically substituted
  items is caught at the transaction boundary.
- Expired, revoked, superseded, replayed, malformed, or unsupported-version mandates fail safely.
- Split fulfillments and cumulative overspend are checked against transactionally updated state.
- Duplicate mutations are controlled with scoped idempotency keys; conflicting payload reuse is rejected.
- Concurrent fulfillment updates use optimistic row versions. A stale writer receives a retryable conflict
  instead of silently overwriting the newer state.
- Missing trusted evidence is uncertainty and causes step-up; it is never silently imputed.
- Merchant text remains inert data in deterministic rules/NLI pairs and is never executed as an instruction.
- Model artifacts are local, versioned, checksum-verified, and unavailable artifacts trigger documented
  fallbacks.

## Prototype limitations

- Demo signing keys and claims are deterministic and must never be reused outside synthetic environments.
- No real payment credential, production ACE API, issuer/acquirer signal, authentication provider, HSM, or
  regional data platform is integrated.
- SQLite is appropriate for the local demo, not a production multi-region authorization workload.
- The deterministic interpreter intentionally supports a constrained English template set.
- Synthetic benchmark performance cannot establish production reliability, fairness, or attack coverage.
- Encryption at rest, network identity, rate limiting, operational key rotation, and retention enforcement
  belong to the production hosting environment and are not simulated here.

