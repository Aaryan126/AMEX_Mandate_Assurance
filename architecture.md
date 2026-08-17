# ACE Mandate Assurance — System and Model Architecture

## 1. Purpose

This document defines the selected architecture for the ACE Mandate Assurance hackathon prototype and the intended path toward a production-grade Amex capability.

The system evaluates whether a proposed agent-initiated transaction—and the cumulative effect of transactions already performed under the same mandate—remains consistent with the Card Member's authenticated intent.

The architecture is designed around five principles:

1. **Trusted evidence over agent self-reporting.** The transaction must be evaluated using merchant-, PSP-, protocol-, or network-confirmed evidence where available.
2. **Deterministic guarantees for objective constraints.** Models should not decide arithmetic, expiry, replay, or exact policy checks.
3. **Specialized models for specialized evidence.** A semantic model interprets language; a tabular model evaluates structured and historical risk.
4. **Calibrated uncertainty and proportionate treatment.** Uncertain cases step up to the Card Member rather than being forced into approve or decline.
5. **An auditable policy owns the final action.** Models provide evidence and scores; a versioned policy produces approve, step-up, or hold/decline.

This is a simulated ACE-aligned prototype. It must not imply access to internal Amex APIs, models, data, or production authorization systems.

---

## 2. Architecture Decision

The selected architecture is a layered hybrid ensemble:

```text
Authenticated mandate + trusted cart evidence + mandate state
                              │
                              ▼
                  Validation and normalization
                              │
             ┌────────────────┼───────────────────┐
             ▼                ▼                   ▼
     Deterministic       Semantic NLI       Stateful/structured
     constraint engine   cross-encoder      feature computation
             │                │                   │
             │                │          ┌────────┴────────┐
             │                │          ▼                 ▼
             │                │      CatBoost          TabM (optional)
             │                │          │                 │
             └────────────────┴──────────┴─────────────────┘
                              │
                              ▼
                 Logistic stacker + calibration
                              │
                              ▼
                    Versioned policy engine
                              │
                  ┌───────────┼───────────┐
                  ▼           ▼           ▼
               Approve      Step up    Hold/decline
                  │           │           │
                  └───────────┴───────────┘
                              │
                              ▼
                 Evidence-backed explanation
                    + append-only audit event
```

### Selected components

| Capability | Selected component | Status |
|---|---|---|
| Objective constraint enforcement | Deterministic Python policy functions | Required |
| Semantic mandate/cart comparison | DeBERTa-v3 NLI cross-encoder | Required |
| Structured transaction risk | CatBoost binary classifier | Required and primary |
| Tabular deep-learning diversity | TabM parameter-efficient MLP ensemble | Challenger; conditional inclusion |
| Score fusion | Logistic-regression stacker | Required |
| Probability calibration | Temperature scaling plus logistic/Platt calibration | Required |
| Novelty detection | Isolation Forest or representation-distance score | Optional; step-up-only |
| Final treatment | Versioned deterministic policy engine | Required |
| Explanation | Reason templates; optional grounded LLM rewrite | Templates required; LLM optional |

---

## 3. System Context

### Upstream inputs

The prototype simulates four upstream sources:

1. **Card Member / mandate UI** — captures the request and confirms its structured interpretation.
2. **Agent platform** — initiates the shopping workflow and submits a transaction proposal.
3. **Trusted merchant/cart source** — provides the line items and transaction attributes used for validation.
4. **Mandate state store** — supplies prior fulfillments, remaining allowance, expiry, and supersession state.

In a future ACE integration, these inputs could align with authenticated intent, verified agent identity, Cart Context, tokenized payment credentials, and Amex authorization/risk signals. The prototype uses synthetic equivalents.

### Downstream consumers

- Card Member decision screen;
- authorization-treatment simulator;
- risk/compliance audit view;
- evaluation dashboard; and
- model and policy monitoring logs.

---

## 4. Prototype Technology Stack

The stack favors speed of implementation, transparent behavior, and a clean separation between UI, orchestration, and Python model inference.

| Layer | Technology | Why |
|---|---|---|
| Web UI | Next.js + TypeScript | Fast creation of a polished, typed multi-screen demo |
| Styling | Tailwind CSS or existing repo design system | Rapid, consistent interface work |
| API and orchestration | FastAPI + Pydantic | Python-native integration with ML libraries and explicit request validation |
| Prototype state | SQLite through SQLModel/SQLAlchemy | Simple local persistence with an easy path to PostgreSQL |
| Semantic model | Transformers or Sentence Transformers + PyTorch | Direct support for NLI cross-encoders and batching |
| Structured model | CatBoost | Strong mixed-type tabular baseline, low inference latency, explainability support |
| DL challenger | TabM + PyTorch | Efficient MLP ensembling and complementary tabular representation learning |
| Fusion/calibration | scikit-learn | Logistic stacking, calibration, evaluation, and optional Isolation Forest |
| Explanations | Deterministic reason templates | Reliable, evidence-bound demo behavior |
| Audit output | Append-only structured JSON events persisted in SQLite | Reproducible decisions and easy reviewer visualization |
| Testing | pytest | Unit, contract, scenario, and model-evaluation tests |

For a minimal prototype, the Next.js application and FastAPI service may run as separate local processes. Do not place Python model inference inside the browser or duplicate decision logic in TypeScript.

---

## 5. Core Data Contracts

All contracts should be versioned. Monetary values must use integer minor units or a decimal type—never binary floating point.

### 5.1 Authenticated mandate

```json
{
  "schema_version": "1.0",
  "mandate_id": "mdt_001",
  "mandate_version": 1,
  "principal_id": "cm_demo_001",
  "agent_id": "agent_demo_travel",
  "objective_text": "Book a refundable economy flight from Singapore to Tokyo...",
  "constraints": [
    {
      "constraint_id": "c_refundable",
      "type": "semantic_attribute",
      "operator": "required",
      "value": "refundable",
      "source_span": "refundable economy flight"
    },
    {
      "constraint_id": "c_budget",
      "type": "total_budget",
      "operator": "lte",
      "amount_minor": 90000,
      "currency": "SGD"
    }
  ],
  "valid_from": "2026-08-15T00:00:00Z",
  "expires_at": "2026-09-10T23:59:59Z",
  "max_fulfillments": 1,
  "approval_policy": {
    "allow_step_up": true,
    "allow_agent_override": false
  },
  "authorization_reference": "signed_demo_reference"
}
```

The natural-language-to-structured conversion may be LLM-assisted, but the structured result becomes authoritative only after Card Member confirmation.

### 5.2 Trusted cart evidence

```json
{
  "schema_version": "1.0",
  "cart_id": "cart_101",
  "merchant_id": "merchant_air_demo",
  "merchant_category": "AIRLINE",
  "evidence_source": "SIMULATED_MERCHANT_SIGNED_CART",
  "evidence_trust": "trusted",
  "currency": "SGD",
  "total_amount_minor": 84000,
  "line_items": [
    {
      "line_item_id": "li_001",
      "description": "Return economy airfare SIN to NRT",
      "quantity": 1,
      "amount_minor": 84000,
      "attributes": {
        "refundable": true,
        "cabin": "economy",
        "outbound_date": "2026-09-07",
        "return_date": "2026-09-10"
      }
    }
  ],
  "created_at": "2026-08-15T10:15:00Z",
  "evidence_reference": "cart_signature_demo"
}
```

### 5.3 Mandate state

```json
{
  "mandate_id": "mdt_001",
  "current_version": 1,
  "status": "active",
  "fulfilled_amount_minor": 0,
  "fulfillment_count": 0,
  "prior_transaction_ids": [],
  "last_updated_at": "2026-08-15T10:15:01Z"
}
```

### 5.4 Decision response

```json
{
  "decision_id": "dec_001",
  "treatment": "STEP_UP",
  "risk_probability": 0.71,
  "uncertainty_band": "moderate",
  "reason_codes": [
    "REFUNDABILITY_EVIDENCE_MISSING"
  ],
  "card_member_explanation": "The fare does not provide enough evidence that it is refundable.",
  "model_versions": {
    "semantic": "english-nli-v3",
    "catboost": "fusion-v2",
    "tabm": null,
    "stacker": "logistic-stacker-v2",
    "calibrator": "platt-calibrator-v2",
    "policy": "policy-v2-no-model-hold"
  },
  "evidence_references": ["signed_demo_reference", "cart_signature_demo"],
  "created_at": "2026-08-15T10:15:02Z"
}
```

---

## 6. Online Decision Flow

### Step 1 — Validate inputs

- Validate contract versions and required fields.
- Reject malformed monetary values, currencies, timestamps, or duplicate IDs.
- Verify that the mandate is active and the evidence source is recognized.
- Record missing evidence explicitly; do not silently impute security-critical attributes.

### Step 2 — Normalize

- Convert dates and timestamps to UTC while retaining market timezone metadata.
- Convert monetary values to comparable minor units after applying an approved FX reference where necessary.
- Normalize merchant categories, airports, locations, and product attributes.
- Split the mandate into independently testable constraints.

### Step 3 — Run deterministic constraints

Each rule returns:

```text
rule_id
status: PASS | WARN | FAIL | NOT_EVALUABLE
severity
observed_value
expected_value
evidence_reference
```

Severe failures such as expired mandate, invalid signature reference, explicit prohibited category, or confirmed cumulative-budget breach may go directly to policy treatment without waiting for model inference.

### Step 4 — Run semantic inference

For each fuzzy constraint, construct a premise/hypothesis pair:

```text
Premise:    Merchant-confirmed fare conditions state that the ticket is non-refundable.
Hypothesis: The proposed itinerary is refundable.
```

Run the pair through the NLI cross-encoder and retain all three probabilities:

```json
{
  "constraint_id": "c_refundable",
  "contradiction": 0.97,
  "entailment": 0.01,
  "neutral": 0.02
}
```

Do not reduce the result to cosine similarity. The neutral/insufficient-evidence class is operationally important because it should frequently produce step-up rather than decline.

Batch the constraint pairs for one cart to reduce latency. Cache embeddings or tokenization only when the cache key includes the normalized constraint, evidence, model version, and tokenizer version.

### Step 5 — Compute structured features

Feature groups include:

- absolute and percentage amount delta;
- currency mismatch and FX-reference age;
- unit and cumulative budget utilization;
- fulfillment count and remaining allowance;
- mandate age and time-to-expiry;
- merchant/category agreement;
- line-item count and unrelated-item indicators;
- missing trusted-evidence count;
- maximum and mean NLI contradiction;
- maximum and mean NLI neutral probability;
- split-transaction and velocity indicators; and
- prior step-up, decline, or override history.

Features must record their source and transformation version. Avoid protected characteristics and do not treat missing merchant history as adverse evidence.

### Step 6 — Run learned tabular models

CatBoost produces the primary structured deviation probability. TabM produces a second probability only when a validated TabM model has passed the inclusion gate.

The models must be trained on the same documented feature schema, but their preprocessing may differ. Store their raw scores separately for ablation and audit.

### Step 7 — Stack and calibrate

The logistic stacker consumes out-of-fold-compatible branch outputs, for example:

```text
semantic_max_contradiction
semantic_unsupported_rate
catboost_probability
tabm_probability_or_missing_indicator
hard_fail_count
soft_warning_count
```

Temperature-scale the NLI logits on a semantic calibration set. Calibrate the final ensemble with logistic/Platt scaling on a separate held-out calibration split. Do not fit either calibrator on the final test set.

### Step 8 — Apply policy

An illustrative policy is:

```text
IF mandate invalid or severe hard violation:
    HOLD
ELSE IF trusted evidence is insufficient for a required constraint:
    STEP_UP
ELSE IF semantic contradiction is high:
    STEP_UP
ELSE IF calibrated risk >= model_step_up_threshold:
    STEP_UP
ELSE:
    APPROVE
```

The current learned path is escalation-only: no semantic or fusion score may independently produce `HOLD`.
`HOLD` requires an observable critical deterministic failure. The model step-up threshold is selected from
the target false-step-up rate on validation data, not from a generic probability cutoff. Model-only hold
requires real pilot outcomes and a separately approved policy version.

### Step 9 — Explain and audit

Generate explanations from reason-code templates. A generative LLM may improve wording only after the reason payload has been constructed, and its output must be checked against the payload before display.

Persist the input references, feature schema, raw branch scores, calibrated score, thresholds, policy version, treatment, and explanation reason codes.

---

## 7. Model Details and Justification

### 7.1 Deterministic constraint engine

**Why it exists:** Exact policy constraints should be reproducible and testable. A model adds no value when comparing a timestamp with an expiry or summing cumulative spend.

**How to use it:** Implement each constraint as a pure function with table-driven tests. Return evidence rather than a bare Boolean. Keep rule evaluation separate from UI code and model preprocessing.

**Failure behavior:** Invalid or absent security-critical evidence returns `NOT_EVALUABLE` or `FAIL` according to the constraint—not a guessed value.

### 7.2 English fine-tuned mDeBERTa-v3 NLI cross-encoder

**Starting checkpoint:** [`MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli`](https://huggingface.co/MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli), pinned to commit `6f5cf0a2b59cabb106aca4c287eed12e357e90eb`.

**Why it exists:** Natural-language inference maps closely to the decision we need: cart evidence can support, contradict, or fail to establish a mandate constraint. A cross-encoder jointly attends to both texts and is more appropriate than standalone embedding distance for fine-grained contradiction.

**Prototype use:**

1. Establish zero-shot performance on the golden semantic set.
2. Fine-tune on grouped English Option 1 constraint/evidence pairs.
3. Train on individual constraint/evidence pairs, not entire unstructured sessions.
4. Preserve the three-class logits.
5. Temperature-calibrate on held-out semantic examples.
6. Benchmark the small and base checkpoints, including batched p95 latency.

The published checkpoint was trained on real MultiNLI, FEVER-NLI, and ANLI data and reports contradiction,
entailment, and neutral outputs. Option 1 adds public ESCI evidence, weak labels, grounded counterfactuals,
and a 6,000-example independent-review queue. The first automated pass is explicitly provisional LLM
consensus followed by disagreement adjudication and a human audit. Generic NLI benchmark performance does not establish
authorization-domain reliability, so domain evaluation remains mandatory.

**Initial language scope:** The first corpus is 100% English. Other languages remain out of scope until a
separately reviewed corpus and per-language evaluation exist. Do not translate silently in the
authorization path without measuring translation-induced errors.

### 7.3 CatBoost

**Source:** [CatBoost documentation](https://catboost.ai/en/docs/)

**Why it exists:** Structured payment and mandate features are heterogeneous, nonlinear, and likely limited in labeled volume during the prototype. Gradient-boosted trees remain strong on industry-style tabular data and are fast enough for a real-time path.

**Prototype use:**

- Objective: binary deviation probability, with ambiguity handled through calibration/policy rather than mislabeled as safe or unsafe.
- Use class weights or an appropriate imbalance strategy; do not optimize raw accuracy.
- Tune on group-aware validation.
- Apply early stopping.
- Record feature importance and SHAP values for analysis, while using explicit reason codes for customer-facing explanations.
- Export and version the fitted model with its exact feature order and category mappings.

CatBoost is the primary learned model even if TabM is evaluated.

### 7.4 TabM

**Sources:** [ICLR 2025 paper](https://openreview.net/forum?id=Sd4wYYOhmY) and [official implementation](https://github.com/yandex-research/tabm)

**Why it exists:** TabM efficiently imitates an ensemble of MLPs through shared parameters and provides a credible, modern tabular-DL comparison. Its different inductive bias may catch interactions that CatBoost misses.

**Prototype use:**

- Use the official `tabm` package rather than copying the deprecated reference file.
- Train with the same grouped splits and target definition as CatBoost.
- Average probabilities across TabM members as instructed by the implementation.
- Use early stopping and repeat across several seeds.
- Measure incremental performance after stacking, not only standalone AUC.

**Inclusion gate:** Add TabM to the online ensemble only when it improves at least one agreed primary metric or attack-family result, does not materially degrade calibration, and remains inside the latency budget. Otherwise report it as a negative or neutral experimental result.

### 7.5 TabPFN

**Source:** [Nature 2025 paper](https://www.nature.com/articles/s41586-024-08328-6)

**Use:** Offline small-data benchmark only.

The paper reports strong performance on datasets up to 10,000 samples and 500 features, but also reports much slower per-sample inference than CatBoost. It is useful for understanding whether the structured dataset is learnable, not as the prototype's authorization-path default.

### 7.6 Logistic stacker and calibration

**Why they exist:** Branch scores are correlated and may operate on different probability scales. A small linear stacker is easier to inspect and less likely to overfit than a deep fusion network.

**How to use them:**

- Produce branch predictions out of fold for every stacker-training row.
- Fit the stacker only on those predictions.
- Fit the final calibrator on a later, untouched calibration split.
- Evaluate reliability diagrams, expected calibration error, and threshold behavior.
- Refit base models only after the complete evaluation procedure is locked.

### 7.7 Novelty detector

**Status:** Optional.

Use Isolation Forest or a simple representation-distance score to detect unfamiliar feature combinations. It may raise a step-up signal but must never independently cause a decline because novelty is not evidence of mandate violation.

---

## 8. Training and Evaluation Pipeline

### Dataset construction

1. Acquire ESCI at an immutable Git revision and verify the Git LFS checksums.
2. Build Option 1 as 60,000 English rows: 50% source-backed singles, 20% source-grounded
   composites, 20% grounded counterfactuals, and a 10% review queue.
3. Review 6,000 Option 1 rows with two independent LLM passes, adjudicate disagreements, and perform a
   stratified human audit before treating any golden result as human-owned evidence.
4. Build Option 2 as a 150,000-row public benchmark from Amazon-M2, UCI Online Retail II, BTS DB1B, and
   USAspending: 70% public-record-backed examples and 30% grounded counterfactuals.
5. Review 4,000 Option 2 rows and freeze the resolved golden labels.

All synthetic fields carry field-level provenance. Every counterfactual retains its parent and generator
version. Parents, queries, invoices, and sequences may not appear across multiple splits.

### Split order

```text
Grouped training split
    ├── base-model fitting folds
    └── out-of-fold predictions for stacker

Grouped validation split
    └── model selection and threshold exploration

Calibration split
    └── temperature and final probability calibration

Golden/time-forward test split
    └── one-time final reporting
```

### Required experiments

| Experiment | Purpose |
|---|---|
| Rules only | Establish deterministic baseline |
| NLI only | Measure semantic contribution |
| CatBoost without semantic features | Measure structured baseline |
| CatBoost with semantic features | Test cross-modal enrichment |
| TabM | Test tabular-DL alternative |
| Rules + NLI + CatBoost | Expected core champion |
| Full stack with TabM | Test incremental ensemble value |
| Optional novelty signal | Test unseen-pattern step-up behavior |

### Primary selection criteria

1. Violation recall at the agreed false-step-up rate.
2. False decline rate.
3. Calibration error and reliability by risk band.
4. Attack-family minimum performance, not only aggregate performance.
5. p95 inference latency.

PR-AUC, precision, coverage, and explanations remain important secondary results.

---

## 9. Explainability Design

There are three explanation layers:

1. **Rule evidence:** exact observed-versus-expected values.
2. **Model analysis:** NLI constraint scores and CatBoost/TabM feature contributions.
3. **Policy reason:** the reason code that actually caused the selected treatment.

The Card Member sees the policy reason in plain language:

> You required a refundable ticket, but the merchant's fare conditions say this ticket is non-refundable.

The reviewer sees additional evidence:

```text
Constraint: c_refundable
Trusted source: cart_signature_demo
NLI contradiction: 0.97
Policy reason: REQUIRED_ATTRIBUTE_CONTRADICTED
Treatment: HOLD
```

SHAP values are useful for model debugging and reviewer analysis, but should not be presented as a causal explanation or used to invent a Card Member-facing reason.

---

## 10. API Surface

Suggested prototype endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/v1/mandates/interpret` | Convert request into a proposed structured mandate |
| `POST` | `/v1/mandates` | Confirm and create an authenticated simulated mandate |
| `GET` | `/v1/mandates/{id}` | Read mandate and current state |
| `POST` | `/v1/decisions/evaluate` | Evaluate trusted cart evidence against a mandate |
| `POST` | `/v1/decisions/{id}/resolve` | Approve once, modify mandate, or decline after step-up |
| `GET` | `/v1/sessions/{id}/audit` | Retrieve the audit timeline |
| `GET` | `/v1/evaluation/summary` | Return frozen benchmark results for the demo dashboard |

Every mutation should accept an idempotency key. The decision endpoint must return model and policy versions.

---

## 11. Persistence Model

Minimum tables:

- `mandates` — immutable mandate versions;
- `mandate_constraints` — normalized constraints and source spans;
- `mandate_state` — current cumulative state;
- `carts` and `cart_line_items` — trusted simulated evidence;
- `decisions` — final score and treatment;
- `decision_signals` — rules, semantic outputs, model scores, and feature references;
- `resolutions` — Card Member response to step-up;
- `audit_events` — append-only event timeline; and
- `model_registry` — model, feature, calibration, and policy versions.

The prototype can use SQLite. A production design would use an approved transactional store, feature platform, and append-only audit infrastructure with appropriate regional data controls.

---

## 12. Security, Privacy, and Compliance Controls

- Do not store real PANs, credentials, or real Card Member data.
- Use synthetic identifiers and transactions in the prototype.
- Authenticate and version mandate consent.
- Minimize raw natural-language retention when structured constraints are sufficient.
- Encrypt sensitive data in transit and at rest in any hosted demo.
- Separate agent-supplied proposals from trusted evidence in both schema and UI.
- Prevent model inputs from executing instructions contained in merchant text.
- Treat merchant text as data, not as system instructions.
- Redact logs and keep explanation prompts free of secrets.
- Record model and policy versions for every treatment.
- Support mandate revocation and supersession.
- Test outcomes by merchant-data availability and region.
- Never use protected characteristics as risk features.
- Treat lack of merchant history as uncertainty rather than adverse evidence.

---

## 13. Reliability and Failure Modes

| Failure | Required behavior |
|---|---|
| Semantic model unavailable | Continue hard-rule checks; step up fuzzy required constraints |
| CatBoost unavailable | Do not silently substitute a stale score; use rules plus semantic policy or step up |
| TabM unavailable | Continue without it; the stacker must support a missing-branch indicator or use the core stack |
| State store unavailable | Do not approve a cumulative mandate autonomously; step up or fail safely |
| Trusted cart evidence missing | Step up required attributes; never trust the agent's replacement narrative automatically |
| Calibration artifact missing | Do not interpret raw scores using calibrated thresholds |
| Unsupported contract version | Reject evaluation with a clear compatibility error |
| Explanation service unavailable | Use deterministic reason templates |

For the hackathon demo, preload all model artifacts and provide deterministic scenario fixtures so the workflow does not depend on an external API.

---

## 14. Latency Strategy

The prototype should measure rather than assume latency. Report p50 and p95 for:

- input validation and rule evaluation;
- semantic batching;
- feature computation;
- CatBoost inference;
- TabM inference when enabled;
- stacking/calibration; and
- end-to-end decision time.

Optimization order:

1. Batch NLI constraint pairs.
2. Use the smaller DeBERTa checkpoint if its accuracy tradeoff is acceptable.
3. Export or quantize the semantic model only after parity testing.
4. Keep CatBoost and deterministic rules in the fast path.
5. Exclude TabM if it breaks the latency budget without enough model lift.
6. Cache only immutable, version-keyed semantic computations.

---

## 15. Prototype Repository Shape

Recommended structure when implementation begins:

```text
apps/
  web/                  # Next.js Card Member and reviewer UI
services/
  api/                  # FastAPI orchestration and contracts
    routes/
    schemas/
    policies/
    rules/
    explanations/
ml/
  data/                 # schema, public adapters, review export, validation, and split manifests
  features/             # versioned feature computation
  semantic/             # NLI inference and fine-tuning
  tabular/              # CatBoost, TabM, optional TabPFN experiments
  fusion/               # stacking and calibration
  evaluation/           # metrics, ablations, reports
artifacts/
  manifests/            # model metadata, not large binaries in source by default
tests/
  unit/
  contracts/
  scenarios/
  evaluation/
docs/
  threat-model.md
  demo-script.md
```

Model binaries and generated datasets should be reproducible from scripts and manifests. Do not commit secrets or real payment information.

---

## 16. Research Sources and What They Support

| Source | Architectural implication |
|---|---|
| [American Express ACE](https://www.americanexpress.com/en-us/company/agentic-commerce/) | Aligns the module with authenticated intent, Cart Context, real-time risk signals, and authorization rather than claiming ACE lacks intent capabilities |
| [American Express ACE launch announcement](https://www.americanexpress.com/en-us/newsroom/articles/innovation/american-express-debuts-agentic-commerce-experiences--ace--devel.html) | Supports positioning as an ACE extension within an intent-driven commerce lifecycle |
| [Google AP2 developer overview](https://developers.googleblog.com/en/developers-guide-to-ai-agent-protocols/) | Supports interoperable signed mandates, guardrails, cart-bound payment evidence, and approval flows |
| [NIST AI 100-2e2025](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-2e2025.pdf) | Supports the threat model for indirect prompt injection and agent integrity failures |
| [TabReD, ICLR 2025](https://arxiv.org/abs/2406.19380) | Supports time/group-aware evaluation and retaining GBDT/simple MLP baselines under industrial distribution shift |
| [TabM, ICLR 2025](https://openreview.net/forum?id=Sd4wYYOhmY) | Supports a parameter-efficient tabular-DL challenger rather than an unnecessarily complex transformer |
| [TabPFN, Nature 2025](https://www.nature.com/articles/s41586-024-08328-6) | Supports an offline small-data benchmark while documenting real-time inference limitations |
| [Booking.com fraud research](https://arxiv.org/abs/2405.13692) | Supports a longer-term self-supervised tabular-transformer roadmap when abundant unlabeled transaction history becomes available |
| [Contextual embeddings with ensemble classifiers](https://arxiv.org/abs/2411.01645) | Supports enriching structured models with language-derived semantic features |
| [English DeBERTa-v3 NLI checkpoint](https://huggingface.co/MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli) | Provides the pinned English three-way semantic starting point trained on MNLI, FEVER-NLI, and ANLI |
| [CatBoost documentation](https://catboost.ai/en/docs/) | Provides the primary structured model implementation and model-analysis tooling |
| [Official TabM implementation](https://github.com/yandex-research/tabm) | Provides the supported package and correct training/inference guidance |

---

## 17. Decision Log

### Accepted

- Use a hybrid of deterministic rules, semantic NLI, and structured ML.
- Use CatBoost as the primary learned tabular model.
- Evaluate TabM as the DL challenger and include it only with measured lift.
- Use logistic stacking and held-out calibration.
- Use a three-outcome policy: approve, step up, hold/decline.
- Permit learned models to trigger step-up but reserve hold for deterministic critical evidence until real pilot data exists.
- Generate final explanations from structured evidence and reason codes.
- Use trusted simulated cart evidence in the prototype.

### Rejected for the initial live path

- Generative LLM as authorization decision-maker.
- Pure embedding cosine similarity.
- Pure rules without semantic modeling.
- TabPFN as the default online model.
- Novelty detection as an automatic-decline reason.
- Agent-supplied transaction descriptions as the sole evidence source.
- Random row-level train/test splits.

### Revisit after the prototype

- Self-supervised tabular pretraining on large unlabeled transaction history.
- Graph features connecting agents, merchants, mandates, and fulfillment chains.
- Market-specific multilingual semantic models.
- Online drift detection and champion/challenger deployment.
- Privacy-preserving partner learning and region-specific production topology.
