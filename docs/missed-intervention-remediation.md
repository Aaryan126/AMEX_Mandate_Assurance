# Missed-intervention remediation ledger

This is the resumable execution ledger for development-v4 and later conditional stages.
Every completed stage records its immutable inputs, outputs, validation results, API
usage, cost, and gate decision here before the next stage starts.

## Execution policy

- Development-v3 paths are immutable and may be read only for diagnosis/regression.
- Every candidate-selection cohort is single-use. Once evaluated, it cannot be used for
  tuning, training, or another selection claim.
- Expensive work runs only after the corresponding fixture/component tests pass.
- LLM-assisted labels are never described as human labels.
- The aggregate new OpenAI Batch cost ceiling is USD 60.
- Stages advance automatically: Stage A -> Stage B on failure -> Stage C on failure.
  A passing development stage advances to one untouched final holdout.

## Status

| Stage | Status | Result |
|---|---|---|
| V3 preservation and baseline | completed | Archive and hashes in `development-v3-checkpoint.md`; 46 API, 111 ML/data, and 6 web tests passed; production build passed. |
| Stage A: targeted data/feature/policy repair | completed, non-promotable | Fresh candidate evaluation failed recall, calibration, family, reviewed-none, and PR-AUC-regression gates. |
| Stage B: semantic remediation | completed, non-promotable | Aggregate operations gates passed, but reviewed semantic recall was 0.4928 versus the required 0.80. |
| Stage C: group-robust specialists | completed, stopped at C1 | The no-spend gate failed: reviewed semantic policy recall regressed to 0.4353 versus the 0.70 authorization threshold. No Stage C2 review was purchased. |
| Untouched final evaluation | conditional | Runs once after the first passing development stage. |

## Stage A gate

- Intervention recall >= 0.90.
- False-step-up rate <= 0.10.
- False-decline rate <= 0.02.
- Expected calibration error <= 0.08.
- Recall >= 0.80 for every intervention family with at least 50 examples.
- Reviewed `none`-family recall >= 0.80.
- PR-AUC no more than 0.01 below locked v3 on the same fresh candidate core.
- All dataset, group-isolation, feature-leakage, and manifest/hash checks pass.

## Stage A checkpoint — review-ready

- Frozen unused pool: 26,853 rows and 20,642 groups; SHA-256
  `3877f17bb917ce8242304cd8b03939317a0be538d56c77f4b04a58fbab8d0ceb`.
- Pool composition: 14,867 real-public relationships and 11,986 hybrid-grounded
  counterfactuals. Development-v3, fast-track, replacement-holdout, unreviewed source,
  and golden relationships were excluded.
- Locked `english-nli-v3` predictions: 26,853 rows; SHA-256
  `a1f1ffb98766429a3d2e235f67043a66b59636e84e22a4817afebe9c3aa277f1`.
- Pool features-v2 used for v3 uncertainty scoring: SHA-256
  `297c4d06d5817055b1c1ea9f95729c030d7d13dfc2f1dc92c2d32adb679d94cb`.
- Frozen review queue: 1,200 rows; SHA-256
  `d483f1c4eb3c9d0247d960ff782b9173d7fa5a64c388603c2ba010186b46933d`.
- Review cohorts: 500 representative candidate semantic, 300 candidate challenge,
  and 400 hard development rows (200 train, 100 calibration, 100 policy tuning).
- Selection ledger SHA-256:
  `26b7798675b4cb0aebc561b46a9581505e16155e5449692d2f535234b6fc36e7`.
- Prepared and validated 2,400 requests in four 600-request shards: two pinned
  GPT-5.4-mini shards and two pinned GPT-4.1-mini shards.
- Submitted at 2026-08-20 16:58 +08 and checksum-validated against all four request
  shards:
  - GPT-5.4-mini: `batch_6a86c1be88348190bc8f5d55d82833b8` and
    `batch_6a86c1c213748190baa1056a16132f8a`.
  - GPT-4.1-mini: `batch_6a86c1c520848190b6143298d7ce0f9e` and
    `batch_6a86c1c7ab1c8190892e11f427725d50`.
- First status snapshot: two jobs `in_progress`, two jobs `validating`, zero failed
  requests. The Batch API expiry deadline is approximately 2026-08-21 16:58 +08.
- Execution must pause after the Stage A candidate evaluation and report its metrics to
  the user before Stage B, Stage C, or a final holdout begins.

## Stage A final result — locked non-promotable

- Review resolution: 608 reviewer agreements and 592 GPT-5.4 adjudications. Two
  adjudications (0.34%) reached their original output-token limit and were retried once;
  all 1,200 labels resolved with zero failed requests.
- Approximate Batch API cost: USD 7.22 (about USD 2.80 reviewers, USD 4.41 primary
  adjudication, and under USD 0.02 retry).
- Development-v4 dataset: 14,500 rows; SHA-256
  `201dc67b2ad56a85a6ed2128d531def7cec9aea05896c742efb0dc7e63c43f87`.
- Frozen semantic predictions: 14,500 rows; SHA-256
  `61c25c262e6612dcf6d2d59bc4f55ab75f3c7ae925d3a266850cd8706f699087`.
- Features-v3: SHA-256
  `9e24ba4d7c0f2dd32bd30dd6cfd4566aa50ef799c4b2fe8d501d274ebd20f782`.
- Selected model: shortcut-safe features-v3, unweighted CatBoost. Direct semantic
  overrides were disabled by policy tuning. Candidate rows accessed during training: 0.
- Candidate-selection cohort: 1,500 fresh rows, comprising 700 deterministic-policy and
  800 LLM-assisted labels; no weak labels.

| Metric | Stage A v4 | Locked v3 on same candidate | Gate |
|---|---:|---:|---:|
| PR-AUC | 0.9717 | 0.9872 | v4 >= v3 - 0.01 (failed) |
| Brier | 0.1456 | 0.0789 | reported |
| ECE | 0.1448 | 0.0883 | <= 0.08 (failed) |
| Intervention recall | 0.6158 | 0.8465 | >= 0.90 (failed) |
| False step-up rate | 0.0346 | 0.1124 | <= 0.10 (v4 passed) |
| False decline rate | 0.0000 | 0.0000 | <= 0.02 (passed) |
| Reviewed `none` recall | 0.2153 | 0.7062 | >= 0.80 (failed) |
| Active challenge recall | 0.1130 | not a v3 gate | diagnostic |

- Supported-family recall passed for cumulative overspend, missing evidence, and
  unrelated add-on (all 1.0), but failed for `none` (0.2153). Near-budget recall was
  0.4091 on 22 violations and therefore remained below the 50-violation supported-family
  gate.
- Status: `LOCKED_NON_PROMOTABLE`. No final holdout is authorized, the live API remains
  unchanged, and Stage B is paused for user review.

## Stage B revision after Stage A

Stage A's development reviews were not suitable for calibration: the reviewed train,
calibration, and policy-tuning roles were respectively 99%, 99%, and 97% interventions,
while the candidate reviews were 68.5%. This distribution shift left almost no reviewed
legitimate semantic examples for learning probabilities or policy thresholds. On the
same Stage A candidate, an oracle threshold under the 10% false-step-up budget reached
recall 0.7147 for v4 but 0.8846 for locked v3. Fixed semantic overrides did not improve
that frontier. Stage B therefore starts from locked v3, not the regressed v4 model.

The corrected Stage B review design uses 1,500 new, relationship-isolated English
examples from a pool that excludes every Stage A relationship:

| Role | Low v3 risk | Boundary | High v3 risk | Challenge | Total |
|---|---:|---:|---:|---:|---:|
| Train | 245 | 210 | 245 | 0 | 700 |
| Calibration | 70 | 60 | 70 | 0 | 200 |
| Policy tuning | 70 | 60 | 70 | 0 | 200 |
| Candidate | 105 | 90 | 105 | 100 | 400 |

Low, boundary, and high are the bottom 35%, middle 30%, and top 35% of calibrated
locked-v3 probabilities in the frozen unused semantic pool. Fixed 0.30/0.70 boundaries
were rejected before API submission because only 245 unused rows exceeded 0.70, versus
the 490 required for balanced coverage. Quantile strata preserve the intended risk
coverage without using any unknown labels. Labels therefore remain blinded until dual
review. The 400 candidate reviews are
single-use. The 700 new training reviews may be combined with the 200 Stage A training
reviews and about 2,100 prior training-only replay examples; no Stage A candidate row
may enter training. After labels are resolved, semantic baseline and JTT variants will
be grouped-OOF trained and calibrated, then compared through a routed policy built on
locked v3. Direct semantic overrides remain disabled unless fresh policy-tuning evidence
shows a benefit. Stage B will be reported before any Stage C work begins.

## Stage B checkpoint — review-ready

- Frozen post-Stage-A pool: 6,991 rows and 6,142 groups; SHA-256
  `c586e7d30a54d38bcd43f9d5e2e6771c4d989b2857c069fab06d8454b6b3f496`.
- Filtered features-v2 SHA-256:
  `bd1edb9adc434c523d1a8443c768a4620d1286581962bf77b768f136737faefe`.
- Stage A exclusions cover 14,500 example, group, and source identifiers plus 6,525
  parent relationships. The new queue has 1,500 unique example, group, and source IDs.
- Frozen review queue SHA-256:
  `162ca6c81c2da9c710e7a97d2cc88464e21c3b61760b886c00560f11fceec547`.
  Selection-ledger SHA-256:
  `31480439686f6c232469f595edc3e7a1c049cc53c1fc9accf605b0f9c93e14d9`.
- Frozen-pool calibrated-v3 quantile cut points were 0.0521 for the low stratum and
  0.3552 for the high stratum. All planned role/stratum counts were met exactly.
- Prepared and validated 3,000 requests in six 500-request shards: three pinned
  GPT-5.4-mini shards and three pinned GPT-4.1-mini shards. Request-manifest SHA-256:
  `27d805d090b04716c29b33b5413c0c425718424d6d65b72cdcdc06fa05aa7a7e`.
- Local validation: 6 focused Stage B/Stage A selection tests and 69 combined
  data/feature/evaluation tests passed. Estimated reviewer cost is about USD 3.50;
  estimated reviewer plus adjudication cost is USD 9–12, depending on agreement rate.
- All six reviewer jobs completed with 500/500 successful requests and zero failures:
  GPT-5.4-mini batches `batch_6a86fe1147688190b8397299a71ddf18`,
  `batch_6a86fe1437e881909cb59cb29e29e256`, and
  `batch_6a86fe1627748190b791e2d84dd8c731`; GPT-4.1-mini batches
  `batch_6a86fe192ddc81909229a5c0428a2dd0`,
  `batch_6a86fe1b84a48190b64ea5f6ff5b3371`, and
  `batch_6a86fe1dfaa4819093dc3ede05333c62`.
- Review import produced 974 agreements and 526 disagreements (64.9% agreement),
  with no missing or single-review rows. The validated 526-request GPT-5.4
  adjudication job is `batch_6a86ff2250ec8190aa767429ce679672`; adjudication input
  SHA-256 is `71be953e32864f781e7c0e1c4a17e5a9a81ba88e7af41fa96c8a7521bc3bf26c`.

## Stage B training and selection

- All 1,500 labels resolved: 974 by reviewer consensus and 526 by GPT-5.4
  adjudication. One truncated adjudication was successfully retried. The reviewed
  dataset SHA-256 is
  `3bcf378de782be9a4785755aefc5347fab80a19d4fcda6ba23192942747b4319`.
- The semantic corpus contains 3,400 rows: 3,000 grouped training rows, 200 validation
  rows, and 200 calibration rows. It combines 700 new Stage B training reviews, 200
  Stage A training-only reviews, and 2,100 prior training-only replay rows. The 400
  Stage B candidate reviews were excluded from training and tuning. Corpus SHA-256:
  `5c13c8c92a78d5dc7539d14e014444fe231a432286525e15656bd680dc4e1c76`.
- Both semantic candidates used five-fold grouped out-of-fold training from the frozen
  semantic-v3 base. The baseline improved validation macro-F1 from 0.4622 to 0.5554
  and contradiction recall from 0.0667 to 0.2222. The JTT variant upweighted 519
  baseline errors by 4x, but reduced validation macro-F1 to 0.5361 and contradiction
  recall to 0.1556, so it was rejected. The baseline model was selected.
- The structured Stage B dataset contains 8,500 rows: 4,700 training, 1,200
  calibration, 1,200 policy-tuning, and 1,400 single-use candidate rows. Dataset
  SHA-256 is
  `8c075f685b434b07f342d40f394ab935df56ef86f2e4bde370a23603e2043788`;
  features-v3 SHA-256 is
  `bbf04690a584580460218b32b1f06415e30d30353349333e6944f378eafabfd7`.
- Policy tuning selected the locked-v3 CatBoost score with semantic-v4 routing over a
  newly retrained CatBoost candidate. Its intervention threshold is 0.6565 and neutral
  routing threshold is 0.70. Direct contradiction overrides remain disabled.

## Stage B final result — locked non-promotable

The one-time 1,400-row candidate evaluation contains 400 LLM-assisted semantic rows
and 1,000 fresh deterministic-policy rows. Candidate targets were excluded from model
training and policy tuning. The high aggregate recall is dominated by deterministic
attack families, so the separately locked reviewed-semantic gate is the decisive
result.

| Metric | Stage B | Locked v3 on same candidate | Gate |
|---|---:|---:|---:|
| PR-AUC | 0.9958 | 0.9958 | v4 >= v3 - 0.01 (passed) |
| Brier | 0.0477 | 0.0477 | reported |
| ECE | 0.0373 | 0.0373 | <= 0.08 (passed) |
| Intervention recall | 0.9029 | 0.8697 | >= 0.90 (passed) |
| False step-up rate | 0.0531 | 0.0398 | <= 0.10 (passed) |
| False decline rate | 0.0000 | 0.0000 | <= 0.02 (passed) |
| Reviewed semantic recall | 0.4928 | 0.3206 | >= 0.80 (failed) |
| Challenge recall | 0.6000 | not a v3 gate | diagnostic |

- Supported-family recall passed for cumulative overspend, missing evidence, and
  unrelated add-on (all 1.0), but failed for the reviewed `none` semantic family at
  0.4928. Near-budget recall was 0.5789 on 19 violations and remained below the
  50-violation support threshold.
- Stage B improved reviewed semantic recall by 17.2 percentage points over the locked
  v3 policy, but it remains 30.7 points below the promotion gate. Status is
  `LOCKED_NON_PROMOTABLE`.
- No final holdout was authorized, the live API remained unchanged, and Stage C was
  paused for review before its controlled attempt.

## Stage C0 diagnosis — proceeded to local C1 only

- Stage C0 used the consumed Stage B candidate for failure diagnosis only. It is not
  authorized for training, policy tuning, or another evaluation claim.
- The Stage B semantic model correctly classified 28.9% of reviewed contradictions,
  47.3% of reviewed neutral cases, and 85.3% of reviewed entailments. The dominant
  false negatives were contradiction-to-entailment (30), neutral-to-entailment (31),
  contradiction-to-neutral (23), and neutral-to-neutral cases that remained below the
  intervention route (22).
- A fixed, post-hoc routing grid reached 0.6699 reviewed semantic recall, 0.9361
  operational recall, and a 0.0973 false-step-up rate. This passed the predeclared
  0.65 diagnostic-headroom gate but remained below the 0.80 project target. Because
  the cohort was already consumed, these oracle values are diagnostic and not a model
  selection or performance claim.
- Stage C0 report SHA-256:
  `8569ee1fe5817a8fb7fe6c113cbea1ac5676d81a684db36cd7a20db8edf73d97`.

## Stage C1 group-robust specialist — stop gate

- One bounded specialist was trained from the immutable semantic-v3 base using two
  grouped cross-fit folds and one final run. All 3,000 permitted training rows received
  label-by-source inverse-square-root weights between 0.7030x and 2.0851x; no
  candidate or non-training row contributed to the weights. Weights SHA-256:
  `496f39132a773215f2b77996d24fbf5aa649eeca592e902fa015efc5f579e37e`.
- The specialist model manifest SHA-256 is
  `32c31c47d9ab39247446cab56eb0090d74da7d445a9f665615aef10c82ecd293`.
  A candidate-free development dataset contained 1,200 calibration and 1,200
  policy-tuning rows. Its output contains zero Stage B candidate rows and accessed zero
  candidate labels.

| Held-out semantic metric | Stage B baseline | Stage C1 |
|---|---:|---:|
| Validation macro-F1 | 0.5554 | 0.5532 |
| Validation contradiction recall | 0.2222 | 0.2000 |
| Validation neutral recall | 0.5500 | 0.6500 |
| Validation entailment recall | 0.9217 | 0.8783 |
| Calibration macro-F1 | 0.5097 | 0.4707 |

| Same policy-tuning role | Stage B | Stage C1 | C1 gate |
|---|---:|---:|---:|
| Reviewed semantic recall | 0.4588 | 0.4353 | >= 0.70 (failed) |
| Operational recall | 0.8047 | 0.8047 | no regression (passed) |
| False-step-up rate | 0.0992 | 0.0992 | <= 0.10 (passed) |
| False-decline rate | 0.0000 | 0.0000 | <= 0.02 (passed) |
| PR-AUC | 0.9510 | 0.9508 | reported |
| ECE | 0.0231 | 0.0232 | <= 0.08 (passed) |

- The specialist traded some entailment/contradiction accuracy for better neutral
  recall, but did not improve the actual reviewed intervention objective. Status is
  `STOP_STAGE_C1`.
- Stage C1 evaluation SHA-256:
  `7b1764437a6f2467d935c60f45407d0d73cb95a5d3458a0ccff121704c5ae25d`.
- Stage C2, fresh LLM review, and final holdout evaluation are not authorized. Stage C
  incurred USD 0 in API cost, the live API remains unchanged, and this controlled
  Stage C attempt is complete.
