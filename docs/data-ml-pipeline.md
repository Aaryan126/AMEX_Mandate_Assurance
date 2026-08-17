# Data and ML pipeline

This document is the operational contract for the public-data hybrid pipeline. It complements the product
overview in the README and describes what must be true before an artifact is allowed into the API.

## Pipeline stages

```mermaid
flowchart LR
    RAW[Immutable public sources] --> ADAPT[Source adapters]
    ADAPT --> CANON[Canonical schema v2]
    CANON --> MIX[Grounded counterfactual builder]
    MIX --> SPLIT[Grouped 70/10/10/10 splits]
    SPLIT --> REVIEW[Two LLM reviewers + adjudication + human audit]
    REVIEW --> NLI[English NLI cross-fitting]
    NLI --> FEATURES[Shared features-v2 contract]
    FEATURES --> CAT[CatBoost]
    CAT --> STACK[OOF logistic stacker]
    STACK --> CAL[Held-out Platt calibration]
    CAL --> GOLDEN[Frozen golden evaluation]
    GOLDEN --> BUNDLE[Checksum-locked serving bundle]
```

No stage overwrites its input. Every materialized dataset and artifact has a manifest containing upstream
hashes. Parent examples, transformed children, queries, invoices, and sequences use a shared `group_id` and
therefore cannot cross splits.

## Canonical row contract

`ml/data/schema.py` defines the strict Pydantic contract. Important fields include:

- `identity`: example, group, parent, and sequence identity;
- `provenance`: source/version/license/hash plus evidence and mandate origins;
- `provenance.field_origins`: distinguishes public observations from generated fields;
- `context`: domain, locale, and market;
- `mandate`, `cart`, and `state`: the exact objects needed to reconstruct features;
- `labels.semantic`: three-way entailment/contradiction/neutral judgments per constraint;
- `labels.deviation` and `expected_treatment`: integrity and policy targets;
- `split.grouping_keys`: leakage-control metadata.

Unreviewed examples may have no targets. Expert-reviewed or adjudicated rows may not omit a deviation label.
Cart arithmetic and currency exponents are validated at ingestion.

## Source contracts

Option 1 downloads ESCI directly from an immutable Git commit. The downloader uses GitHub's LFS media
endpoint, checks Parquet magic, and stores source checksums.

Option 2 accepts a `records.jsonl` in one directory per source. `ml.data.acquire_option2` directly
downloads UCI, DB1B, and USAspending. Amazon-M2 requires an authenticated AIcrowd download and is then
normalized locally because its publication terms must be accepted by the user.

| Directory | Required record keys |
|---|---|
| `amazon-m2` | `session_id`, `locale`, `previous_product_ids`, `previous_titles`, `next_product_id`, `next_title`; optional `next_description`, `next_price`, `currency` |
| `uci-online-retail-ii` | `invoice`, `stock_code`, `description`, `quantity`, `unit_price`; optional `country` |
| `bts-db1b` | `itinerary_id`, `origin`, `destination`, `market_fare`; optional `carrier` |
| `usaspending-awards` | `award_id`, `recipient`, `description`, `amount` |

`ml/data/raw/option2/source-lock.json` must record a version for each source. Checksums should be added at
raw extraction time; the canonical adapters preserve them in every row.

```json
{
  "sources": {
    "amazon-m2": {"version": "immutable-release", "sha256": "records-jsonl-sha256"},
    "uci-online-retail-ii": {"version": "2009-2011", "sha256": "records-jsonl-sha256"},
    "bts-db1b": {"version": "year-quarter", "sha256": "records-jsonl-sha256"},
    "usaspending-awards": {"version": "api-export-date", "sha256": "records-jsonl-sha256"}
  }
}
```

The Option 2 builder refuses a missing checksum or a `records.jsonl` whose bytes do not match the lock.

## Labels and synthetic-data rules

ESCI relevance is a weak semantic label, not a financial outcome. It is mapped as:

| Source label | Semantic target | Deviation | Initial treatment |
|---|---|---|---|
| Exact | Entailment | Match | Approve |
| Substitute | Neutral | Ambiguous | Step-up |
| Complement | Contradiction | Violation | Hold target for dataset analysis |
| Irrelevant | Contradiction | Violation | Hold target for dataset analysis |

Amazon-M2 has no query or ESCI relevance label. Its real evidence is an observed shopping-session
transition. We turn the prior English UK product sequence into an explicitly synthetic intent envelope and
treat the observed next product as a low-confidence (`0.55`) positive transition. This is useful only as
weak pretraining evidence; it is neither an explicit customer mandate nor a financial outcome.

The live policy does not blindly reproduce those treatment targets. Until real pilot outcomes exist, a
learned semantic or fusion score can trigger only `STEP_UP`. A live `HOLD` requires a critical deterministic
rule such as invalid authorization, replay, cumulative overspend, a prohibited item/category, unauthorized
merchant, or fulfillment-limit breach.

Synthetic transformations are allowed only when grounded in an existing public record. They preserve a
parent ID, generator version, transformation name, and field origins. Current transformations cover a
near-budget legitimate example, cumulative overspend, removed evidence, and a real-public-product add-on.

## Review protocol

The internal annotation service is off by default. When enabled, it imports only rows marked `unreviewed`
into a separate SQLite database. A reviewer cannot label the same example twice. Two matching independent
signatures resolve a row; mismatches enter an adjudication queue. Export creates a new dataset and leaves
both the source JSONL and review database unchanged.

Reviewers label three distinct concepts:

1. mandate/evidence semantic relationship;
2. overall match, violation, or ambiguity;
3. expected approve, step-up, or hold treatment.

Keeping these targets separate prevents an arithmetic breach from being incorrectly used as a semantic
contradiction label.

The automated path uses two pinned OpenAI model snapshots with different review prompts and a strict JSON
schema. A stronger pinned model adjudicates only disagreements. Export preserves `llm_consensus` and
`llm_adjudicated` provenance, so these labels cannot be mistaken for `expert_review`. A stratified human
audit is still required before using the set as a governance-owned golden benchmark.

## Training and serving invariants

- Training rows receive NLI predictions only from a model that did not train on their group.
- Validation selects the model step-up threshold; calibration fits probability calibration; golden is
  untouched until final evaluation.
- The evaluator cannot access `attack_family` while predicting.
- The API and offline pipeline import the same `features-v2` function.
- The serving loader verifies feature order and artifact checksums.
- The fusion manifest records the semantic model version and prediction hash; the API refuses a runtime
  semantic/fusion version mismatch.
- Training artifacts are unapproved by default; a separate hash-bound golden-report promotion creates the
  only manifest the Docker runtime will auto-load.
- Fusion uses data-only JSON coefficients; no pickle is loaded by the API.
- An artifact declaring `model_hold_enabled=true` is rejected by this API build.
- Missing artifacts fall back to the explicit heuristic path, never an unversioned partially loaded model.

## Promotion gate

An artifact can be copied to the serving artifact directory only if all unit/component tests pass, feature
parity passes, golden results meet the declared gate, latency is measured after warm-up, and the manifest
matches the exact dataset and semantic-prediction hashes. Passing a public benchmark is still not evidence
of production readiness; real pilot outcomes, drift monitoring, market-level analysis, and governance are
required before changing the escalation-only model policy.
