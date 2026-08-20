# Step 24 Failure Analysis and Remediation Plan

Status: proposed remediation sequence; no remediation training or relabeling has started.

## Outcome

The Step 23 result is a genuine failed promotion gate, not an evaluation-pipeline failure. The current
artifact must remain unpromoted. Changing only its threshold cannot repair the result because the
deterministic policy exceeds both false-step-up and false-decline limits, and the learned fusion ranking
is worse than CatBoost alone.

The consumed replacement holdout may be used to understand failure modes, but it must never again be
used for threshold selection, model selection, or an independent final gate.

## What failed

| Area | Development evidence | Consumed-holdout evidence | Conclusion |
|---|---:|---:|---|
| HOLD label prevalence | 32.58% | 3.38% | Training and evaluation treatments follow different label contracts |
| Operational recall | 73.93% during selection | 56.27% | Development selection was optimistic |
| False step-up | 9.96% during selection | 28.39% | Threshold and fixed-policy behavior do not transfer |
| False decline | 0% during selection | 4.91% | LLM-reviewed labels disagree with deterministic HOLD triggers |
| PR-AUC | Not a selection constraint | 0.529 | Ranking is not promotion quality |
| Calibration error | Calibrator fitted on calibration split | 0.194 | Final probabilities do not transfer |
| Fusion versus CatBoost | Chosen through operational validation | -0.080 PR-AUC | Stacker should not have been eligible |
| Minimum attack recall | Not enforced during candidate selection | 13.97% | Near-budget coverage is unacceptable |

The locked holdout contains only LLM-reviewed labels: 2,715 consensus and 1,285 adjudicated. Development
validation mixes 2,822 weak mappings, 2,178 deterministic counterfactuals, and only 608 LLM-resolved
rows. This difference is the dominant distribution shift.

## Confirmed root causes

### 1. There is no single treatment contract

Three definitions disagree:

- The review rubric says total/cumulative overspend and currency mismatch are HOLD, while semantic
  mismatch and missing evidence are STEP_UP.
- The generator labels every unrelated add-on as HOLD even when there is no explicit prohibited-item
  constraint and no deterministic rule capable of proving it is prohibited.
- The API currently makes confirmed cumulative breach, fulfillment breach, explicit prohibition, and
  unauthorized merchant critical HOLDs, but ordinary single-cart overspend and currency mismatch fall
  through as STEP_UP.

Consequently, `expected_treatment` currently mixes product policy, synthetic construction intent, weak
mapping, and reviewer judgment. It is not a stable supervised target.

### 2. LLM reviewers missed deterministic state arithmetic

For the 288 cumulative-overspend counterfactuals, the original deterministic source treatment was HOLD.
Reviewers returned only 135 HOLD, plus 98 APPROVE and 55 STEP_UP. Sample explanations compare the cart
amount with the total budget but omit the supplied prior fulfilled amount and often omit that the next
purchase exceeds the fulfillment limit.

Arithmetic and state-policy truth should not be delegated to an LLM. Reviewers should receive computed,
auditable rule outcomes and judge only semantic evidence.

### 3. Counterfactual labels and invariants are not policy-safe

- `cumulative_overspend` frequently triggers both cumulative-budget and fulfillment-limit breaches.
- `unrelated_add_on` declares HOLD without an explicit prohibition or deterministic unrelated-item rule.
- `missing_required_evidence` can retain enough product-title evidence for reviewers to consider the
  semantic requirement satisfied.
- `near_budget_match` changes price but inherits weak semantic intent mappings; reviewers step up 136 of
  290 examples originally labeled APPROVE.

Each counterfactual needs a declared intended trigger set plus assertions that no unintended trigger is
introduced.

### 4. Offline and online rules are duplicated

`ml/features/canonical.py` independently reconstructs a subset of `services/api/app/rules.py`. The live
engine additionally checks authorization, mandate state/window, replay, merchant, route, and travel
rules. Training features can therefore describe a different policy state from the API.

### 5. Fusion is harmful

The stacker learned these semantic weights:

- semantic contradiction: `-1.1857`;
- semantic neutral: `-0.9487`.

Both semantic signals are already present inside CatBoost, so the stacker receives redundant correlated
inputs and reverses their marginal direction. On the consumed holdout the full ensemble loses 0.0802
PR-AUC and 0.1755 fixed-FPR recall relative to CatBoost alone.

### 6. Development splits have overloaded roles

The same validation split is used for CatBoost early stopping, policy-threshold selection, and candidate
selection. Calibration is fitted on the calibration split, so that split cannot independently compare
candidates. This leaves no honest development partition for architecture selection.

### 7. The training target and some gates differ

The corrected model trains on policy intervention (`STEP_UP` or `HOLD` versus `APPROVE`), while PR-AUC
and fixed-FPR ranking use binary deviation labels and omit 567 ambiguous-but-operationally-reviewed
holdout rows. Both views are useful, but the primary model-selection metric must match the training and
operational target.

## Treatment contract requiring product approval

Before data or model work resumes, create `policy-treatment-contract-v3` as a truth table. The following
is the recommended starting point; rows marked “decide” require an explicit product-risk decision.

| Evidence | Recommended prototype treatment | Basis |
|---|---|---|
| Invalid/inactive/expired mandate, replay | HOLD | Authenticated objective failure |
| Confirmed cumulative budget breach | HOLD | Deterministic stateful breach |
| Confirmed fulfillment-limit breach | HOLD | Deterministic stateful breach |
| Explicit prohibited item/category match | HOLD | Deterministic authenticated prohibition |
| Unauthorized merchant | HOLD | Deterministic authenticated restriction |
| Single-cart budget overspend | Decide HOLD or STEP_UP | Rubric and API currently disagree |
| Currency mismatch | Decide HOLD or STEP_UP | Rubric and API currently disagree |
| Semantically unrelated item without explicit prohibition | STEP_UP | Model evidence, not deterministic proof |
| Semantic contradiction | STEP_UP | Model-only HOLD remains prohibited |
| Insufficient or missing semantic evidence | STEP_UP | Card Member confirmation required |
| Elevated structured-model risk | STEP_UP | Model-only HOLD remains prohibited |
| All deterministic checks pass and learned risk is low | APPROVE | Low-risk path |

Also split the conflated `PROHIBITED_OR_UNRELATED_ITEM` reason into an explicit deterministic prohibition
code and a semantic unrelated-item code.

## Proposed execution sequence

Every phase is an approval boundary and finishes with a progress-ledger checkpoint.

### Step 25 — Freeze the policy and label contract

Deliverables:

- versioned treatment truth table;
- precedence rules: deterministic rule truth → semantic judgment → structured risk → treatment policy;
- separate fields for `deterministic_outcome`, `semantic_outcome`, `policy_intervention_target`, and
  optional research-only `binary_deviation`;
- documented decisions for single-cart overspend and currency mismatch.

Tests and exit gate:

- truth-table parameterized unit tests cover every reason code;
- no reason code maps to multiple treatments in one policy version;
- model probability can cause STEP_UP but never HOLD;
- user approves the two unresolved treatment choices.

Estimated effort: 1–2 hours. No training or API cost.

### Step 26 — Unify offline and live deterministic rules

Deliverables:

- one shared pure rule-evaluation core consumed by both dataset feature construction and FastAPI;
- offline features derived from actual rule statuses/reason codes rather than a second implementation;
- versioned rule-result schema and feature provenance.

Tests and exit gate:

- offline/online parity for every rule fixture is 100%;
- property tests cover budget boundaries, cumulative arithmetic, currency, and fulfillment counts;
- malformed/missing state is NOT_EVALUABLE rather than silently safe;
- existing API and project suites remain green.

Estimated effort: 2–4 hours. No training or API cost.

### Step 27 — Repair the counterfactual generator

Deliverables:

- generator v3 with declared intended rule and semantic triggers;
- unrelated add-ons labeled according to the approved semantic policy;
- cumulative examples that isolate cumulative breach unless a multi-breach cohort is explicitly
  requested;
- evidence-removal examples whose missing evidence is measurable rather than inferred from provenance.

Tests and exit gate:

- each transformation has exact trigger-set assertions;
- parent/child group binding remains intact;
- no price, quantity, or state inconsistency;
- multi-breach examples are separately tagged and cannot enter single-trigger evaluation cohorts.

Estimated effort: 2–4 hours. No training or API cost.

### Step 28 — Establish a human-audited label benchmark

Deliverables:

- a stratified 300–500-row audit spanning each attack family, deterministic trigger, LLM consensus,
  LLM adjudication, and source type;
- deterministic outcomes precomputed by the shared engine;
- humans review semantic entailment/contradiction/insufficiency and disputed policy cases, rather than
  recomputing arithmetic;
- reviewer guide with worked boundary examples.

Tests and exit gate:

- deterministic labels have 100% oracle agreement;
- every sample has two independent reviews plus adjudication for disagreement;
- agreement and confusion are reported per attack family;
- no model prediction or attack-family name is shown to reviewers.

Estimated effort: tooling 2–4 hours plus human review time. No LLM job should be submitted until the
human benchmark reveals which portions can safely be scaled with assisted review.

### Step 29 — Build dataset v3 with honest split roles

Recommended partitions:

1. `train_fit` — fitting and grouped out-of-fold predictions;
2. `calibration` — calibration only;
3. `policy_tuning` — operating-threshold selection only;
4. `candidate_selection` — architecture and ablation selection only;
5. future `final_holdout` — frozen only after every development choice is locked.

Deliverables:

- hybrid labels where deterministic rule results are authoritative and semantic labels come from audited
  review;
- group, parent, and source-record isolation across partitions;
- label-source and treatment balance reports;
- no use of the consumed Step 23 holdout for fitting or selection.

Tests and exit gate:

- zero example/group/parent/source overlap;
- all split roles are single-purpose and checksum-bound;
- deterministic and semantic label contracts validate independently;
- representation and treatment shifts remain within predeclared tolerances.

Estimated effort: 2–4 hours local after the label contract and audit are ready.

### Step 30 — Re-establish model baselines

Run in this order:

1. deterministic policy only;
2. frozen semantic model only;
3. CatBoost only, with semantic scores included;
4. calibrated CatBoost;
5. fusion only if it has a plausible independent signal.

Selection rules:

- policy-intervention PR-AUC and recall at the operational false-step-up limit are primary;
- binary deviation metrics remain secondary diagnostics;
- CatBoost is the default winner unless another candidate improves supported attack-family recall and
  calibration without degrading the primary metrics;
- a stacker with reversed semantic direction or any non-degradation failure is ineligible.

Tests and exit gate:

- grouped OOF predictions cover every fitted row exactly once;
- calibration and tuning partitions are never used for fitting;
- candidates are deterministic across repeated seeds where promised;
- model manifests bind data, split roles, features, semantic model, and policy versions.

Estimated effort: 30–90 minutes locally for structured candidates; semantic retraining is a separate
approval only if Step 28 shows that the semantic model itself is the limiting component.

### Step 31 — Lock the candidate and promotion criteria

Deliverables:

- one immutable selected candidate;
- one immutable policy threshold;
- the existing promotion limits retained unless product risk changes them independently of Step 23;
- cohort gates for every adequately supported attack family.

Exit gate:

- operational recall `>= 0.90`;
- false step-up `<= 0.10`;
- false decline `<= 0.02`;
- expected calibration error `<= 0.08`;
- supported-family recall `>= 0.80`;
- challenger non-degradation gates pass on candidate-selection data.

Estimated effort: 30–60 minutes. No final-holdout access.

### Step 32 — Freeze a new independent final holdout

The original source had 38,000 eligible unused train rows before the consumed 4,000-row holdout was
selected, so a new holdout appears feasible, but availability must be recomputed after excluding the
fast-track dataset, consumed holdout, and all related groups/parents/source records.

Deliverables:

- a new seed and freeze version;
- explicit exclusion of both earlier evaluation sets;
- deterministic labels produced by the approved shared engine;
- blinded semantic review only where judgment is actually required;
- a stratified human audit before the holdout is unlocked.

Exit gate:

- zero relationship overlap with development and both previous golden sets;
- all labels comply with the v3 contract;
- model and threshold remain frozen throughout review.

Estimated effort: 1–2 hours local preparation plus review time and any separately approved review cost.

### Step 33 — One-time final evaluation and separate promotion decision

Deliverables:

- one checksum-bound final report;
- complete operational, calibration, latency, attack-family, and provenance metrics;
- promotion remains a separate explicit approval even if every gate passes.

If any criterion fails, preserve the result, do not retune against the new holdout, and begin another
development cycle with a subsequently new final set.

## Test strategy throughout

| Layer | Required tests |
|---|---|
| Policy | Reason-code truth table, precedence, model-only-HOLD prohibition |
| Rules | Boundary/property tests and 100% offline/API parity |
| Generator | Exact intended-trigger invariants and group/source integrity |
| Labels | Schema, provenance, deterministic precedence, reviewer blinding, agreement reports |
| Splits | Example/group/parent/source isolation and single-purpose split roles |
| Semantic | Label order, probability quality, per-family ranking, inference provenance |
| CatBoost | Feature profile, OOF coverage, deterministic artifact bindings |
| Fusion | Independent-signal requirement, coefficient audit, non-degradation gates |
| Calibration | Held-out-only fit, ECE/Brier, stable threshold binding |
| Evaluation | Selection checksum, sealed-set single access, immutable report |
| Runtime | Artifact loading, policy parity, latency, API component tests |

Run focused tests before and after each phase, then the full project/API/Ruff/diff suite at every approval
boundary.

## Actions explicitly ruled out

- Do not lower promotion thresholds because Step 23 failed.
- Do not tune the current model or policy against the consumed holdout.
- Do not repair labels by automatically restoring every synthetic source label; some source labels are
  themselves inconsistent with the intended policy.
- Do not ask LLM reviewers to recompute deterministic arithmetic.
- Do not retain fusion merely because it was in the original architecture; measurable incremental value
  is required.
- Do not promote or connect the current remediation artifact to the live API.
