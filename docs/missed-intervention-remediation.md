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
| Stage B: semantic remediation | paused | Stage A failed, but no Stage B work may begin before user review. |
| Stage C: group-robust specialists | conditional | Runs only if Stage B fails its fresh locked gate. |
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
