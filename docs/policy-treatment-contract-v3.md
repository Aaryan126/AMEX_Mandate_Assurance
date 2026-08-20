# Policy Treatment Contract v3

Version: `policy-treatment-contract-v3`

This contract is the authoritative mapping from observable evidence to prototype treatment. Labels,
offline evaluation, and the live API must use the same mapping.

## Precedence

1. Deterministic critical rule outcomes.
2. Audited semantic outcome.
3. Structured risk score.
4. Versioned treatment policy.

A critical deterministic outcome may produce HOLD. Semantic and learned-model evidence may produce
STEP_UP but never HOLD in this prototype.

## Treatments

| Signal | Treatment |
|---|---|
| Invalid, inactive, expired, replayed, or superseded mandate | HOLD |
| Confirmed cumulative-budget or fulfillment-limit breach | HOLD |
| Explicit prohibited item/category or unauthorized merchant | HOLD |
| Single-cart budget overspend | STEP_UP |
| Currency mismatch | STEP_UP |
| Semantic contradiction or unrelated item without an explicit prohibition | STEP_UP |
| Insufficient/missing evidence | STEP_UP |
| Elevated structured-model risk | STEP_UP |
| No critical, uncertain, failing, or elevated-risk signal | APPROVE |

The single-cart budget and currency decisions intentionally follow the current prototype API and the
PRD's proportionate-intervention principle. They avoid automatic decline when Card Member confirmation
can safely resolve the proposal.

`EXPLICIT_PROHIBITED_ITEM_OR_CATEGORY` and `SEMANTIC_UNRELATED_ITEM` are separate reason codes. The old
conflated `PROHIBITED_OR_UNRELATED_ITEM` code is not part of v3.

## Label fields for dataset v3

- `deterministic_outcome`: rule codes and their authoritative criticality.
- `semantic_outcome`: entailment, contradiction, or insufficient evidence.
- `policy_intervention_target`: APPROVE versus intervention under this contract.
- `binary_deviation`: optional research label; never substitutes for the operational target.

Arithmetic, state, currency, and explicit-list truth comes from the shared deterministic engine. Human
or assisted review judges semantic evidence only. The final expected treatment is derived from this
contract rather than independently invented by a reviewer.
