# Fast-Track ML Pipeline Progress

Last updated: 2026-08-20 14:49 +08

This file is the restartable source of truth for the fast-track experiment. It records completed work,
artifact locations, verification evidence, and the next approval gate. Generated datasets and model files
remain gitignored; their committed builders, manifests, and checksums make them reproducible.

## Approval protocol

1. Execute exactly one numbered step at a time unless the user explicitly approves a larger range.
2. After a step completes, update this file with its status, artifacts, checksums, commands, and tests.
3. Steps 25–33 are explicitly approved for automatic continuation; no intermediate approval pause is
   required.
4. Billable API jobs and local training within Steps 25–33 are explicitly authorized, but each must
   remain checksum-bound and restartable.
5. A laptop shutdown is safe whenever the current status below is `WAITING_FOR_APPROVAL` or
   `WAITING_ON_REMOTE`.
6. Long-running folds will write resumable checkpoints before any training is started.

## Current checkpoint

- Workflow status: `DEVELOPMENT_GATE_FAILED`
- Last valid completed step: `STEP_31_LOCK_CANDIDATE_AND_GATES`
- Active step: none; Steps 32–33 are prohibited until a new development candidate passes Step 31
- Approval status: the user explicitly approved uninterrupted execution of Steps 25–33, including local
  training and necessary review work; no intermediate approval is required unless scope or authority
  must materially expand
- Replacement-holdout OpenAI jobs submitted: yes — all eight original reviewer Batch jobs and the
  approved two-request Reviewer A retry are `completed`; all `8,000` final review responses pass strict
  validation and are imported atomically; the approved `1,285`-request adjudication Batch is `completed`
  and downloaded; the approved five-request retry is also completed/downloaded; all `1,285`
  adjudications pass strict validation and are imported, and all `4,000` replacement-holdout examples
  are resolved in the immutable reviewed export
- Historical billable OpenAI jobs submitted: yes — six original reviewer Batch jobs, one original
  adjudication Batch job, one original two-row adjudication retry, eight replacement reviewer jobs, and
  one replacement two-row reviewer retry, one completed replacement adjudication Batch, plus one
  completed replacement five-row adjudication retry
- Local model training started: yes — semantic, CatBoost, grouped stacker, and calibrator training are
  complete; two corrected remediation candidates were retrained and the semantic candidate was selected
  using development validation data only. The selected candidate has now been scored once on the
  replacement holdout and failed all eight promotion criteria; no model was promoted and the live API
  remains unchanged

## Immutable inputs currently available

| Input | Location | Recorded checksum/status |
|---|---|---|
| Option 1 English corpus | `ml/data/generated/option1-en/ace-esci-en-hybrid.jsonl` | SHA-256 `14e46c3aaef299de6007ca2e1233c4198643529c5a77cc614578187092e9256f`; 60,000 rows |
| Option 2 public corpus | `ml/data/generated/option2/ace-public-benchmark.jsonl` | SHA-256 `945678346ac6cc03f2cb2b7ea45451fae8d5749993bae70edfba3fa5ca1e8b06`; 150,000 rows |
| English NLI base model | `artifacts/base-models/english-nli/` | Immutable upstream revision recorded in `ace-artifact-manifest.json` |
| OpenAI key | `.env.annotation` | Present and access-checked; secret value is never recorded here |
| Annotation reviewer A | `ml/data/llm_annotations.py` | `gpt-5.4-mini-2026-03-17` |
| Annotation reviewer B | `ml/data/llm_annotations.py` | `gpt-4.1-mini-2025-04-14` |
| Annotation adjudicator | `ml/data/llm_annotations.py` | `gpt-5.4-2026-03-05` |

## Step ledger

| Step | Work | Expected artifact | Expected duration | Status |
|---:|---|---|---:|---|
| 00 | Establish progress ledger and approval protocol | This file | 10 min | completed |
| 01 | Implement and unit-test group-safe representative sampling | `ml/data/select_fast_track.py`, tests | 1–2 h | completed |
| 02 | Materialize 4,000-row Option 1 train sample while retaining all held-out rows | `ml/data/generated/fast-track/option1/` | 10–20 min | completed |
| 03 | Materialize approximately 10,000 Option 2 pretraining rows and retain the full benchmark | `ml/data/generated/fast-track/option2/` | 10–20 min | completed |
| 04 | Derive the reduced review queue and prepare two reviewer batches | `ml/data/annotations/fast-track/` | 10–20 min | completed |
| 05 | Submit GPT-5.4-mini and GPT-4.1-mini reviewer batches | OpenAI batch state files | remote, up to 24 h/wave | completed |
| 06 | Download, validate, and import both reviewer outputs | Review SQLite database | 15–30 min after completion | completed |
| 07 | Prepare and submit full GPT-5.4 adjudication for disagreements | Adjudication state file | remote, up to 24 h | completed |
| 08 | Import adjudication and export the reviewed fast-track dataset | Reviewed JSONL + manifest | 15–30 min | completed |
| 09 | Add and test resumable semantic-fold checkpoints | Training state manifest | 1–2 h | completed |
| 10 | Run sampled Option 2 domain pretraining | Domain-adapted checkpoint | 30–45 min | completed after remediation |
| 11 | Train semantic fold 1 | Fold-1 predictions/checkpoint | 20–25 min | completed after corrected retry |
| 12 | Train semantic fold 2 | Fold-2 predictions/checkpoint | 20–25 min | completed |
| 13 | Train semantic fold 3 | Fold-3 predictions/checkpoint | 20–25 min | completed |
| 14 | Train semantic fold 4 | Fold-4 predictions/checkpoint | 20–25 min | completed |
| 15 | Train semantic fold 5 | Fold-5 predictions/checkpoint | 20–25 min | completed |
| 16 | Train the final semantic model | Final model artifact | 25–30 min | completed |
| 17 | Generate predictions and build canonical features | Predictions + features-v2 | 25–50 min | completed |
| 18 | Train CatBoost, stacker, and calibrator | Fusion artifact bundle | 10–20 min | completed |
| 19 | Run golden evaluation, complete tests, and review promotion gate | Evaluation report | 15–30 min | completed — failed gate |
| 20 | Diagnose and implement non-golden remediation | Policy-aware selection + shortcut controls | 45–90 min | completed |
| 21A | Freeze the replacement holdout and prepare blinded review requests | Locked holdout + 8 request shards | 30–60 min | completed |
| 21B | Submit two independent reviewer passes | 8 OpenAI Batch state files | 5–15 min, then remote up to 24 h | completed |
| 21C | Download, validate, and import reviewer results; prepare disagreements | Review database + adjudication request | 15–30 min after completion | completed after two-row retry |
| 21D | Submit GPT-5.4 disagreement adjudication | OpenAI Batch state file | 5–10 min, then remote up to 24 h | completed in 9m54s |
| 21E | Download/import adjudication and export the reviewed locked holdout | Reviewed holdout + manifest | 15–30 min after completion | completed after five-row retry |
| 22 | Retrain and select corrected structured candidates | Ablations + corrected fusion bundle | 20–45 min | completed |
| 23 | Run one-time replacement-holdout evaluation and review promotion | Final report | 15–30 min | completed — failed gate |
| 24 | Diagnose failure and design remediation plus a new independent holdout | Remediation plan | 45–90 min | completed |
| 25 | Freeze policy and label contract | Treatment truth table | 1–2 h | completed |
| 26 | Unify offline and live deterministic rules | Shared rule core + parity tests | 2–4 h | completed |
| 27 | Repair counterfactual generator | Generator v3 + invariants | 2–4 h | completed |
| 28 | Establish audited benchmark | Audit queue + resolved labels | review-dependent | completed via explicitly requested LLM substitute; not human |
| 29 | Build dataset v3 with honest split roles | Dataset v3 | 2–4 h | completed |
| 30 | Re-establish model baselines | Baseline reports/artifacts | 30–90 min+ | completed |
| 31 | Lock candidate and promotion criteria | Immutable selection | 30–60 min | completed — non-promotable |
| 32 | Freeze and review a new independent holdout | New locked holdout | review-dependent | not authorized: Step 31 gates failed |
| 33 | Run one-time final evaluation | Final report | 15–30 min | not authorized: no eligible candidate/holdout |

## Completed-step evidence

### STEP_00 — progress and approval setup

- Status: completed
- Completed at: 2026-08-17 21:36 +08
- Artifact: `docs/fast-track-progress.md`
- Decision: every subsequent step is an explicit approval boundary.
- Recovery: reopen this file and continue only from the `Next approval required for` entry.

### STEP_01 — representative sampler implementation and tests

- Status: completed
- Completed at: 2026-08-17 21:40 +08
- Implementation: `ml/data/select_fast_track.py`
- Unit/component tests: `tests/data/test_fast_track_selection.py`
- Operator commands: `make data-fast-track-option1` and `make data-fast-track-option2`
- Selection rules: sample only training groups; retain every validation, calibration, and golden row;
  preserve observed categories; bind source and output checksums; enforce a maximum total-variation
  distance of `0.08` for each monitored representation dimension.
- Test evidence:
  - Ruff: passed for `ml`, `services`, and `tests`.
  - API suite: `23 passed`.
  - Full project suite: `55 passed`.
  - `git diff --check`: passed.
  - Make targets: dry-run validated only; neither materialization command was executed.
- Read-only Option 1 integration smoke:
  - Source train rows: `42,000`; requested sample: `4,000`.
  - Selected train groups: `3,133`.
  - Held-out rows retained: `18,000`; projected output rows: `22,000`.
  - Maximum observed representation TVD: `0.005369` (gate: `0.08`).
  - Missing source categories: none.
  - Preview selected-example-ID hash:
    `227b547f1334396d67ff88bfb7ef2bee29afdbacd0e68209c7874149b42d05e6`.
- Materialized artifacts: none. `ml/data/generated/fast-track/` remains absent.
- Recovery: implementation is complete and tested; it is safe to shut down. Do not execute either
  Make target until its corresponding step is approved.

### STEP_02 — Option 1 fast-track materialization and validation

- Status: completed
- Completed at: 2026-08-17 21:48 +08
- Dataset: `ml/data/generated/fast-track/option1/ace-fast-track.jsonl` (`22,000` rows;
  approximately `77 MB`)
- Manifest: `ml/data/generated/fast-track/option1/manifest.json`
- Dataset SHA-256: `0846aabc0d6fbd56cbbf0f4218725b75eaf9f3d54ecca8f9946ef20c7604783a`
- Manifest SHA-256: `d5d15c892bdb822dcab26cce06aa51ae0f2860a408aa83484e10d50090e7f946`
- Source immutability check: source still has `60,000` rows and SHA-256
  `14e46c3aaef299de6007ca2e1233c4198643529c5a77cc614578187092e9256f`.
- Saved composition:
  - Train: `4,000` rows across `3,133` train groups.
  - Validation: `6,000` rows retained in full.
  - Calibration: `6,000` rows retained in full.
  - Golden: `6,000` rows retained in full.
  - Canonical validator observed `18,133` total groups and no group/split leakage.
- Representation result: maximum TVD `0.005369` against the `0.08` gate; no source
  categories were omitted.
- Reproducibility: seed `2026`; selected-example-ID SHA-256
  `227b547f1334396d67ff88bfb7ef2bee29afdbacd0e68209c7874149b42d05e6`.
- Issue found and fixed: the fast-track manifest now includes canonical `row_count` as well as
  selection-specific `output_rows`; a regression test verifies compatibility with
  `ml.data.validate_dataset`.
- Test evidence:
  - Focused selector/validator suite: `7 passed`.
  - Canonical validation: passed schema, unique-ID, group-safety, row-count, and checksum gates.
  - Ruff: passed for `ml`, `services`, and `tests`.
  - API suite: `23 passed`.
  - Full project suite: `55 passed`.
  - `git diff --check`: passed.
- Git handling: generated dataset and manifest are ignored by `ml/data/generated/`; their builders
  and recorded checksums remain the reproducible source of truth.
- Step-boundary check: Option 2 output is absent; no billable OpenAI job or local training was started.
- Recovery: the Option 1 artifact is complete and validated. It is safe to shut down and resume from
  `STEP_03` only after explicit approval.

### STEP_03 — Option 2 fast-track materialization and validation

- Status: completed
- Completed at: 2026-08-17 21:51 +08
- Dataset: `ml/data/generated/fast-track/option2/ace-fast-track.jsonl` (`55,000` rows;
  approximately `158 MB`)
- Manifest: `ml/data/generated/fast-track/option2/manifest.json`
- Dataset SHA-256: `29ec5026872ab0916d2ff04334d380cf6d6ca2aa8f2b82122a7afaa37fe34b83`
- Manifest SHA-256: `33cd074d7b51c6920e36fd73d6918f1db05fee7281406156fbbab0d801356162`
- Source immutability check: source still has `150,000` rows and SHA-256
  `945678346ac6cc03f2cb2b7ea45451fae8d5749993bae70edfba3fa5ca1e8b06`.
- Saved composition:
  - Train: `10,000` rows across `6,989` train groups.
  - Validation benchmark: `15,000` rows retained in full.
  - Calibration benchmark: `15,000` rows retained in full.
  - Golden benchmark: `15,000` rows retained in full.
  - Canonical validator observed `38,470` total groups and no group/split leakage.
- Representation result: maximum TVD `0.005462` against the `0.08` gate; no source
  categories were omitted.
- Reproducibility: seed `2026`; selected-example-ID SHA-256
  `ffe37b48c3d0dc160493541ce1b2918f751fa8131f064d583b9bee552c1fe8b2`.
- Test evidence:
  - Focused selector/validator suite: `7 passed`.
  - Canonical validation: passed schema, unique-ID, group-safety, row-count, and checksum gates.
  - Ruff: passed for `ml`, `services`, and `tests`.
  - API suite: `23 passed`.
  - Full project suite: `55 passed`.
  - `git diff --check`: passed.
- Cross-artifact check: Option 1 remains unchanged at SHA-256
  `0846aabc0d6fbd56cbbf0f4218725b75eaf9f3d54ecca8f9946ef20c7604783a`.
- Git handling: generated Option 2 files are ignored by `ml/data/generated/`; the builder and
  recorded checksums preserve reproducibility.
- Step-boundary check: no annotation batch was prepared or submitted, and no billable OpenAI job or
  local training was started.
- Recovery: both fast-track datasets are complete and validated. It is safe to shut down and resume
  from `STEP_04` only after explicit approval.

### STEP_04 — reduced review queue and local reviewer batches

- Status: completed
- Completed at: 2026-08-17 21:56 +08
- Input dataset SHA-256: `0846aabc0d6fbd56cbbf0f4218725b75eaf9f3d54ecca8f9946ef20c7604783a`
- Output directory: `ml/data/annotations/fast-track/`
- Manifest SHA-256: `5fd34a839ff6b4838a8034400d475c8c826b5c11d3514d6a34d0040c1d147677`
- Eligible queue: `3,284` English unreviewed examples.
- Selected queue: `2,500` examples, SHA-256
  `6d16cfd0696183c4f179faa8a4192a6a86e346275f4043f0429607fad2e0cb5b`.
- Selection policy: seed `2026`; retain every selected-train and golden review row, then balance the
  remaining capacity across validation and calibration:
  - Train: `284 / 284`.
  - Golden: `1,000 / 1,000`.
  - Validation: `608 / 1,000`.
  - Calibration: `608 / 1,000`.
  - The other `784` examples remain preserved and explicitly unreviewed.
- Reviewer A: pinned `gpt-5.4-mini-2026-03-17`; `2,500` requests in three shards
  (`1,000 + 1,000 + 500`).
- Reviewer B: pinned `gpt-4.1-mini-2025-04-14`; `2,500` requests in three shards
  (`1,000 + 1,000 + 500`).
- Total prepared requests: `5,000`; total payload size: `26,984,096` bytes.
- Request-shard SHA-256 values:
  - A-000: `188a740e777c2e5afa424a08851837e07b0c058917c8233a2d5461a679652cb9`
  - A-001: `101a93471f7d15a3b117c0c373bcd070505fb37bc66b2244d46c69cb3f7e322c`
  - A-002: `9fc221f6bfd1d5e228f7a15269e7a2fe7389a15e94fb7da11cd3da4d26c9fa06`
  - B-000: `09a0e37f68472dcbec33169bab1e3f1208755c2a28284ad68bd3221a7d64ee15`
  - B-001: `e5c18f80530e88ea20f8d1e08570844fdaecaf0d3ffa742dc723597f410fc2c7`
  - B-002: `d7bfc0bb4d8c95c90072cb63d2c98d1267942d2d58a95146d2c19b77539dc10a`
- Local validator gates: dataset and queue binding; queue uniqueness and split counts; exact reviewer
  coverage; shard hashes and counts; pinned model and reviewer IDs; Responses endpoint; strict JSON
  schema; evidence-only payloads with no source labels.
- Issue found and fixed: validation now reads physical JSONL records rather than splitting valid
  in-string Unicode U+2028 separators; a real-corpus failure and regression test cover this case.
- Test evidence:
  - Focused LLM annotation suite: `6 passed`.
  - Prepared-batch validator: passed all `5,000` requests.
  - Ruff: passed for `ml`, `services`, and `tests`.
  - API suite: `23 passed`.
  - Full project suite: `56 passed`.
  - `git diff --check`: passed.
- Pre-submission estimate: approximately `$6–$12` for the two reviewer passes, with actual billing
  depending on tokenizer and generated/reasoning tokens. Later full-model adjudication is separate and
  depends on the disagreement rate. Pricing checked on 2026-08-17 against official OpenAI model pages:
  GPT-5.4 mini Batch `$0.75/M` input and `$4.50/M` output; GPT-4.1 mini Batch `$0.40/M` input and
  `$1.60/M` output.
- Step-boundary check: no submission-state directory exists, no file was uploaded, no billable API job
  was created, and no local model training was started.
- Recovery: the queue and all request shards are locally complete and validated. It is safe to shut
  down. `STEP_05` would create six remote Batch jobs (three resumable shards per reviewer) and requires
  explicit approval.

### STEP_05 — submit reviewer shards to OpenAI Batch

- Status: completed
- Completed at: 2026-08-17 22:00 +08
- Local state directory: `ml/data/annotations/fast-track/states/`
- Submission result: six unique input files and six unique Batch jobs were accepted; initial status for
  every job was `validating`.
- Reviewer A (`gpt-5.4-mini-2026-03-17`):
  - A-000: `batch_6a83139a38c081908eac07be9d0b7d9d`
  - A-001: `batch_6a83139d6ae081908e7cefd9f4b05fb1`
  - A-002: `batch_6a8313a013e081908f97fa324159582c`
- Reviewer B (`gpt-4.1-mini-2025-04-14`):
  - B-000: `batch_6a8313ad74d08190b674384eddb1f913`
  - B-001: `batch_6a8313b037708190b87beefe83c30daf`
  - B-002: `batch_6a8313b1d3e88190839760e5bdc3e92a`
- Restart safety: each state records its remote Batch ID, uploaded-file ID, local input path, and input
  SHA-256. The state validator confirmed all six states exactly match the six prepared manifest shards,
  with no missing, extra, or duplicate remote IDs.
- New component test: submission-state validation is covered with local fake state records and rejects
  path/hash/coverage inconsistencies.
- Test evidence:
  - Focused LLM annotation suite: `7 passed`.
  - Prepared-request validation: all `5,000` requests still pass.
  - Submission-state validation: six states, six unique Batch IDs, six unique uploaded-file IDs.
  - Ruff: passed for `ml`, `services`, and `tests`.
  - API suite: `23 passed`.
  - Full project suite: `57 passed`.
  - `git diff --check`: passed.
- Git handling: the state files are ignored by `ml/data/annotations/` and remain available locally for
  restart and download operations.
- Step-boundary check: no remote status polling beyond the submission responses, no result file download,
  no review import, no adjudication request, and no local model training was started.
- Recovery: the remote jobs continue independently of the laptop and can take up to the Batch completion
  window. It is safe to shut down. `STEP_06` will refresh all six statuses, wait if necessary, download and
  validate completed outputs, and import them only after explicit approval.

### STEP_06 — reviewer output download, validation, and import

- Status: completed
- Completed at: 2026-08-17 22:58 +08
- Remote result: all six Batch jobs completed; `5,000 / 5,000` requests succeeded with zero Batch
  failures or error files.
- Validated output directory: `ml/data/annotations/fast-track/outputs/`
- Validated output manifest SHA-256:
  `2601a20d90507c28c0089a191bddfcf7cb7390132f3ff70637582f85d522ebec`
- Reviewer A output SHA-256 values:
  - A-000: `77aeab07c8b98d4dce584d56c62dba83da98de821c59b9b046b1ab6c11d47650`
  - A-001: `7e5a0297eb24d0697dae4d245e1765be756e04b75f637a51815140e22b412d33`
  - A-002: `be60feda4d21ea14b8de4c6ad587f73d12abfdb1f91b626f56153d41926826ea`
- Reviewer B output SHA-256 values:
  - B-000: `2de3bdd570f35dd0bd19b3beb0b16ecf808668ba406231efe9d71893ed4d3142`
  - B-001: `fa8a66a653b6c420c20cebb99cbc1b32a82f5f75560193f7b241866f8b3aad44`
  - B-002: `009c1d29719a5ffa4eb97298140b4f830f5aeb3ed8ddcf8f0fc10de6bb25b6a3`
- Joint validation: every output has exact input custom-ID coverage, unique IDs, the expected reviewer
  identity, a strict schema-conforming label, and the recorded input/output checksum binding.
- Review database: `ml/data/annotations/fast-track/reviews.sqlite3` (approximately `17 MB`)
- Review database SHA-256: `ebd77dea8594598b5245603d0401fc8de30e621284ccef84ea4cf217eef25ae0`
- Import result:
  - Reviewer A rows: `2,500`.
  - Reviewer B rows: `2,500`.
  - Reviewed examples: `2,500`.
  - Failed imports: `0`.
  - Agreements resolved without adjudication: `1,778`.
  - Disagreements requiring adjudication: `722` (`28.88%` of reviewed examples).
  - Deliberately unselected/unreviewed: `784`.
  - Single-review examples: `0`.
- Disagreements by split: train `87`, validation `182`, calibration `175`, golden `278`.
- Idempotency check: rerunning the full six-shard import produced identical logical counts and the
  identical database SHA-256, without duplicate rows.
- Restart-safe tooling added:
  - Multi-shard status and 30-second wait commands update every local state file.
  - Incremental downloads preserve completed outputs and skip still-running jobs.
  - Output validation requires exact input coverage and strict payload conformance before import.
  - Imports are idempotent for byte-equivalent reviewer payloads and verify exact queue/reviewer counts.
- Issue found and fixed: real GPT-4.1 mini outputs may contain empty `output_text` message items before
  the populated structured output. The parser now skips empty items, and a component regression test
  covers the observed response shape.
- Test evidence:
  - Focused annotation suite: `8 passed`.
  - Real-output validation: `5,000 / 5,000` passed.
  - Submission-state validation: six completed states with unique Batch and uploaded-file IDs.
  - Ruff: passed for `ml`, `services`, and `tests`.
  - API suite: `23 passed`.
  - Full project suite: `58 passed`.
  - `git diff --check`: passed.
- Step-boundary check: no adjudication request file was prepared or submitted, and no local model training
  was started.
- Recovery: Step 6 is complete and all generated files are gitignored. It is safe to shut down.
  `STEP_07` would prepare and submit `722` disagreement cases to the pinned full GPT-5.4 adjudicator and
  requires separate explicit approval.

### STEP_07 — prepare, validate, and submit full-model adjudication

- Status: completed
- Completed at: 2026-08-18 09:46 +08
- Input disagreement count: `722`, exactly covering the unresolved reviewed examples:
  - Train: `87`.
  - Validation: `182`.
  - Calibration: `175`.
  - Golden: `278`.
- Adjudicator: pinned `gpt-5.4-2026-03-05`, reviewer identity
  `llm-adjudicator-gpt-5.4-2026-03-05`, low reasoning effort, strict structured output, and a
  per-request `500` output-token limit.
- Request payload: `ml/data/annotations/fast-track/adjudication.jsonl` (`722` rows; `4,563,189` bytes).
- Request payload SHA-256: `13c711b44b8a4ccbc87c1d9891108f2ba2f3f5cd6ba74321aedc4cf15d1f5571`.
- Request manifest: `ml/data/annotations/fast-track/adjudication.manifest.json`.
- Request manifest SHA-256: `4f46b2c3bb815499ee5c926e162ba9c3f5d7b920c62667f068cdc2d5d228dde1`.
- Adjudication prompt SHA-256: `6910b467820a3e69ec4a34c60690c0c1ea512f77fb4c0161c0fb31e645268e10`.
- Immutable bindings revalidated immediately before submission:
  - Option 1 dataset SHA-256:
    `0846aabc0d6fbd56cbbf0f4218725b75eaf9f3d54ecca8f9946ef20c7604783a`.
  - Reviewer database SHA-256:
    `ebd77dea8594598b5245603d0401fc8de30e621284ccef84ea4cf217eef25ae0`.
- Local validation requires exact current-disagreement coverage, unique custom IDs, the pinned model,
  exact adjudication prompt, Responses Batch endpoint, low reasoning configuration, exact strict JSON
  schema, output-token limit, source evidence with no source label, and the exact two conflicting
  reviewer payloads stored in SQLite.
- Submission state: `ml/data/annotations/fast-track/adjudication.state.json`; SHA-256
  `f183e486bd7687932630260f8dbd78f2bee26ec7017618e1e928a59861643d90`.
- OpenAI input file ID: `file-4CkC8x7XqF7BCTuLnmydHd`.
- OpenAI Batch ID: `batch_6a83b94bf16c8190a82b464bf655dea1`.
- Initial remote status: `validating`. The job continues remotely and does not require the laptop to
  remain open.
- Cost estimate: approximately `$4–$9` for this adjudication pass under typical tokenization/output
  lengths; actual cost depends on input tokenization and generated/reasoning tokens. The configured
  visible-plus-reasoning output ceiling is `361,000` tokens across all requests. Pricing checked on
  2026-08-18 against the official GPT-5.4 model page: Batch `$2.50/M` input and `$15/M` output.
- Safety and tests added:
  - Preparation writes a checksum-bound manifest before a submission is possible.
  - A local validator rejects stale dataset/database state, altered evidence or prior reviews, duplicate
    or incomplete disagreement coverage, an altered model/prompt/schema/reasoning/token limit, and a
    changed request checksum.
  - The component test includes a deliberately altered model request and verifies rejection.
  - Focused annotation suite: `8 passed`.
  - Ruff: passed for `ml`, `services`, and `tests`.
  - API suite: `23 passed`.
  - Full project suite: `58 passed`.
  - `git diff --check`: passed.
- Step-boundary check: no adjudication status poll beyond the submission response, no output download,
  no adjudication import, no reviewed-dataset export, and no local model training was started.
- Recovery: Step 7 is complete; the job is remotely resumable from the recorded Batch ID. It is safe to
  shut down. `STEP_08` requires explicit approval and will monitor the job, download and validate all
  `722` outputs, import them idempotently, and export the reviewed dataset.

### STEP_08 — adjudication import and reviewed export

- Status: completed
- Completed at: 2026-08-18 10:06 +08
- Primary Batch result:
  - Status: `completed`; Batch transport counts `722 / 722` completed and `0` failed.
  - Output file ID: `file-ADB1F91sJkQhz4Xnf3pAr7`; error file ID: none.
  - Usage: `1,015,588` input tokens and `172,824` output tokens, of which `94,110` were reasoning
    tokens; `1,188,412` total tokens.
  - Estimated primary charge at GPT-5.4 Batch rates: `$5.13` (`$2.54` input + `$2.59` output).
  - Updated state SHA-256: `b9329461a4de096c1d3fb13d6d7e2320a29567e0476171b20d984e43626e1fd3`.
- Downloaded primary output: `ml/data/annotations/fast-track/adjudication.output.jsonl`
  (`722` physical rows; `4,731,871` bytes); SHA-256
  `50e04fc7f3b49414e6f24fac41cdaaeae63680157f90abcc4bae0f99a98c281f`.
- Validation incident: the transport-level Batch count was successful, but the response-level validator
  found `720` completed responses and `2` responses with status `incomplete` and reason
  `max_output_tokens`. Their structured JSON was truncated and therefore rejected:
  - `ace_esci_1330323`: `402 / 500` output tokens were reasoning tokens.
  - `ace_esci_1799986`: `429 / 500` output tokens were reasoning tokens.
- Safety action: no output was imported, the review database remains at its pre-adjudication SHA-256
  `ebd77dea8594598b5245603d0401fc8de30e621284ccef84ea4cf217eef25ae0`, and no reviewed dataset was
  exported.
- Retry input prepared locally: `ml/data/annotations/fast-track/adjudication.retry-01.jsonl`
  (`2` rows; `11,057` bytes); pinned to `gpt-5.4-2026-03-05` with a `1,000` output-token cap.
- Retry input SHA-256: `a5d1377c7b0b46b4cfe8d204f8bf58b334d67462d7efe7de32bbb6de7def1af7`.
- Retry manifest: `ml/data/annotations/fast-track/adjudication.retry-01.manifest.json`; SHA-256
  `03b59ddd102920243aafe209f23fa6e14b512d5546ca47e96dd33eaba201e60b`.
- Retry manifest binds the exact two rejected custom IDs to both the original request SHA-256
  `13c711b44b8a4ccbc87c1d9891108f2ba2f3f5cd6ba74321aedc4cf15d1f5571` and downloaded-output
  SHA-256 `50e04fc7f3b49414e6f24fac41cdaaeae63680157f90abcc4bae0f99a98c281f`.
- Retry Batch result:
  - Batch ID: `batch_6a83bd5949048190b78983e653cff336`.
  - Input file ID: `file-KVgLx6hmsfUsJoT5F3WoNX`; output file ID:
    `file-HKJshg8ceh2G3R8Jd95jV2`; error file ID: none.
  - Result: `2 / 2` completed, zero failures.
  - Usage: `2,390` input tokens and `662` output tokens, including `439` reasoning tokens;
    estimated charge `$0.016`.
  - Retry state SHA-256: `75bb85e30a754cdc8df4b23c53c9d29c3823583102d611b8821fef792f3a7686`.
  - Retry output: `ml/data/annotations/fast-track/adjudication.retry-01.output.jsonl`; SHA-256
    `0c53a23c236881c16132ce7cd2a3e59408c64067bbefc223ff91cfee7716698e`.
- Combined estimated adjudication Batch charge: `$5.15` (`$5.13` primary plus `$0.016` retry).
- Validated merge: `ml/data/annotations/fast-track/adjudication.validated.jsonl` (`722` rows;
  `4,728,982` bytes); exactly two original rows replaced; SHA-256
  `faf3a1346915b18f8af42d0b1f8847c75510986eacad4bab15c9bf03f973c895`.
- Import result:
  - `722` adjudications imported with zero failures.
  - Progress: `722` adjudicated, `1,778` agreements, `0` disagreements remaining, `0` single-review
    cases, and `784` deliberately unselected/unreviewed rows.
  - Repeating the complete import produced the identical physical database SHA-256
    `5bab9d1c9ce15741fe4b276f965f0fc91bf7dadf3d7766f016c5a2d241f8d873`.
- Reviewed dataset: `ml/data/generated/fast-track/option1/ace-fast-track-reviewed.jsonl`
  (`22,000` rows; `80,846,814` bytes); SHA-256
  `f0c1aab1f3d424f9b53d549b6e757f0072a31caf7f1241aa7259477998978050`.
- Reviewed manifest: `ml/data/generated/fast-track/option1/ace-fast-track-reviewed.manifest.json`;
  SHA-256 `b2619f2a175d7835ea99951ce63898b3b67be6ffd42507502598592049ba5a10`.
- Reviewed label composition:
  - `10,437` weak ESCI mappings.
  - `8,279` deterministic counterfactuals.
  - `1,778` LLM consensus labels.
  - `722` LLM adjudicated labels (train `87`, validation `182`, calibration `175`, golden `278`).
  - `784` intentionally unreviewed labels.
- Canonical validation: `22,000` unique examples, `18,133` groups, no group/split leakage, valid
  schema/provenance/semantic references, and exact manifest checksum binding. Re-export was byte-for-byte
  deterministic with the same dataset hash.
- New local safeguards/tests:
  - Response status must be completed, not merely transport-successful.
  - Retry selection is derived only from locally invalid outputs and checksum-bound to both sources.
  - Retry merge replaces only the exact failed custom IDs and revalidates all original IDs.
  - Adjudication import requires exact stored-ID coverage and two disagreeing source reviews.
  - Reviewed export now records canonical row/checksum fields and label-source counts.
  - Focused annotation/export suites: `11 passed`.
  - Full data/ML suite: `59 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: no training state, domain pretraining, fold training, feature generation, or model
  training was started.
- Recovery: Step 8 is complete and all generated artifacts are gitignored. It is safe to shut down.
  `STEP_09` will add and test resumable semantic-fold checkpointing and requires explicit approval.

### STEP_09 — resumable semantic-fold checkpoints

- Status: completed
- Completed at: 2026-08-18 10:15 +08
- Checkpoint implementation: `ml/semantic/checkpoints.py`; SHA-256
  `bacb29097e6bba2ad43a614b27863a94cbc657bd40dba5caa879938e712e85d8`.
- Trainer integration: `ml/semantic/train_multilingual.py`; SHA-256
  `239fd12b92ffd5bd625bc417c94232b172d1a0c12dabc91e037a4e94fe719948`.
- Component tests: `tests/semantic/test_training_checkpoints.py`; SHA-256
  `9818bf2d850b1aca9cca424ca4a3b482abdaf7289ba96620572356d1c884a07b`.
- New operator stages:
  - `make semantic-fast-track-prepare` creates or verifies the immutable run state without training.
  - `make semantic-fast-track-fold FOLD=0` through `FOLD=4` runs one explicitly approved fold.
  - `make semantic-fast-track-finalize` refuses to start until every fold checkpoint is complete.
- Restart and integrity behavior:
  - `training-state.json` binds the exact dataset path/hash, labeled semantic keys, immutable base-model
    repository/revision/tree/manifest, every training hyperparameter, random seed, fold assignment, and
    expected holdout keys.
  - Group assignment is deterministic; training and holdout groups are checked for disjointness per fold.
  - A fold is marked `running` with an incremented attempt before training begins.
  - Holdout logits are written through a temporary file and atomically renamed before the fold is marked
    `completed` with its SHA-256.
  - A completed fold is structurally/checksum validated and skipped on rerun.
  - Failed or interrupted folds retain resumable attempt state; prior completed folds are not repeated.
  - Dataset, base tree, configuration, assignment, coverage, duplicate-key, logits, or artifact tampering
    causes a hard failure before training continues.
  - Final predictions and manifest are checksum-bound in the same state; a completed full run is also
    skipped on rerun.
- Real-data no-training preparation smoke:
  - Reviewed dataset SHA-256:
    `f0c1aab1f3d424f9b53d549b6e757f0072a31caf7f1241aa7259477998978050`.
  - Immutable upstream base revision: `6f5cf0a2b59cabb106aca4c287eed12e357e90eb`; verified tree SHA-256
    `df0931d853790c5181580169b40f6c14cd9b273a3493e83fe240da3bca312cff`.
  - Labeled semantic pairs: `21,216` (`4,000` train, `5,608` validation, `5,608` calibration,
    `6,000` golden).
  - Five train holdouts are nonempty and total exactly `4,000` rows: fold 0 `830`, fold 1 `753`,
    fold 2 `795`, fold 3 `796`, fold 4 `826`.
  - Corresponding holdout-group counts: `639`, `596`, `626`, `623`, and `649`.
  - The smoke state was created only in a disposable `/private/tmp` directory and invoked no model
    dependency or training routine.
- Production-state decision: no state was created under `artifacts/models/semantic-fast-track/` because
  it must be bound to the domain-adapted base produced by Step 10. Step 10 will create that immutable
  checkpoint first and then prepare the production fold state against it; binding early to the upstream
  base would make the resume contract incorrect.
- Test evidence:
  - Semantic unit/component suite: `8 passed`.
  - Full data/ML suite: `64 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff, CLI help/dry-runs, and `git diff --check`: passed.
- Step-boundary check: no Option 2 pretraining, semantic fold, final semantic model, feature generation,
  CatBoost/fusion training, or evaluation was started.
- Recovery: Step 9 is complete and safe to shut down. `STEP_10` requires explicit approval before any
  local model training begins.

### STEP_10 — sampled Option 2 domain pretraining (invalidated; remediation prepared)

- Status: invalidated by the Step 11 behavioral quality gate; FP32 remediation awaits approval
- Completed at: 2026-08-18 11:25 +08
- Published checkpoint: `artifacts/models/semantic-domain-fast-track/` (approximately `360 MB`).
- Published model/tree revision:
  `5624e38f9cc9e54b527130741fe80d4f7b0159a0f555a2a7b4274b44529aabe7`.
- Artifact manifest SHA-256:
  `c1ee071017b01515c98fccfd9d5b7460895ea26be0fddc67b762a3fad8f2e4da`.
- Completed state: `artifacts/models/semantic-domain-fast-track.state.json`; SHA-256
  `32f48e82220eb9363582f00d670fcc9d1c3b6f887ba293f2c6537f5df6d75875`.
- Immutable inputs:
  - Option 2 dataset SHA-256:
    `29ec5026872ab0916d2ff04334d380cf6d6ca2aa8f2b82122a7afaa37fe34b83`.
  - Training pairs: `6,520` across `4,581` groups (`511` neutral, `6,009` entailment).
  - Validation pairs retained in the run binding: `9,900` across `6,991` groups (`731` neutral,
    `9,169` entailment).
  - Upstream English NLI base revision: `6f5cf0a2b59cabb106aca4c287eed12e357e90eb`; tree SHA-256
    `df0931d853790c5181580169b40f6c14cd9b273a3493e83fe240da3bca312cff`.
- Training configuration: one epoch, learning rate `5e-6`, micro/effective batch size `16`, gradient
  checkpointing enabled, seed `2026`, MPS accelerator, and frozen classifier head. Option 1 was not
  replayed during this stage, preventing the future cross-fit holdouts from leaking into every fold base.
- MPS numerical safeguard and incident:
  - The first completed attempt was rejected during independent reload because the default MPS AdamW
    update had made encoder tensors non-finite even though its forward loss and gradients were finite.
  - The rejected artifact and state were preserved, not deleted, under
    `artifacts/models/quarantine/step10-nonfinite-first-attempt-20260818/`.
  - A full-model one-update diagnostic established that `AdamW(eps=1e-6, foreach=False)` preserved all
    parameters as finite. These settings are now immutable metadata for domain and fold training.
  - The shared trainer now rejects non-finite loss, sampled first-update gradients/parameters, and
    non-finite fold logits. Domain publication additionally requires finite smoke inference, a CPU scan
    of every saved floating tensor, and exact equality of the frozen classifier against the base.
  - Two monitored retries briefly overlapped because the command wrapper stopped streaming while the
    first process remained alive. Both exact process pairs were stopped, memory was verified recovered,
    and the final run was launched as one resumable terminal session. The completed state records three
    post-repair launch attempts; only the final launch ran the full epoch and published an artifact.
- Successful run: `408 / 408` optimizer steps in `1,013.4` seconds (approximately `16m53s`) at
  `0.4026` steps/second; process exit code `0`.
- Independent published-artifact validation:
  - State/manifest/tree binding is idempotent and the staging directory is absent.
  - Zero saved tensors contain a non-finite value.
  - `classifier.weight` and `classifier.bias` are exactly unchanged from the upstream base.
  - A sampled first encoder tensor changed, proving that domain adaptation was not a no-op.
  - A clean CPU reload produced finite logits with shape `3 x 3` for three English request/evidence pairs.
- Implementation and test artifacts:
  - `ml/semantic/train_domain.py`; SHA-256
    `b69f8843f34b6452566e212166154b1dcbcfb3b60398cfddb0ca61f9781acc26`.
  - `ml/semantic/train_multilingual.py`; SHA-256
    `1fbc5da082c2407241a1e9bdfd0dfa6bd8108f8b8acbe8d14bd4d9eb01296827`.
  - `ml/semantic/checkpoints.py`; SHA-256
    `17d9546ed97aadfe06d4502f7863268ff82dcf0c5aa785a68e1e680b68963524`.
  - Domain component tests: `tests/semantic/test_domain_training.py`; SHA-256
    `fa38f412a5cf86cdf46fbfc694596594a86d4bc94120e9273fda2cfe4d2fba2c`.
  - Fold component tests: `tests/semantic/test_training_checkpoints.py`; SHA-256
    `c36dd8b4d130e71103060463cdd8b4a683ed1f1f70e411929397ab293145360c`.
- Prepared next-stage state: `artifacts/models/semantic-fast-track/training-state.json`; SHA-256
  `d10df7c6be3aa4fe6e01b036c6363f2a7b5c91431bfa16fe1d4c48638a14eb6b`.
  It is bound to reviewed Option 1 SHA-256
  `f0c1aab1f3d424f9b53d549b6e757f0072a31caf7f1241aa7259477998978050` and domain tree
  `5624e38f9cc9e54b527130741fe80d4f7b0159a0f555a2a7b4274b44529aabe7`. All five folds and the final
  stage remain `pending` with `0` attempts; the directory contains only `training-state.json`.
- Test evidence:
  - Focused domain/checkpoint suite: `10 passed` after the numerical repair.
  - Full data/ML suite: `69 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: no semantic fold, final semantic model, feature generation, CatBoost/fusion
  training, or evaluation was started.
- Original recovery decision (superseded by the Step 11 finding below): Step 10 had passed its initial
  finite/checksum gates and was treated as complete.

#### Post-completion invalidation found during STEP_11

- The finite-only Step 10 checks were insufficient. On 24 varied reviewed Option 1 pairs, the upstream
  NLI model produced all three predicted classes with per-class logit standard deviations between
  `1.64` and `1.89`; the Step 10 checkpoint produced only entailment and effectively zero logit
  standard deviation for every class.
- The Step 10 model was therefore behaviorally collapsed despite containing only finite tensors. The
  working numerical diagnosis is FP16 training/optimizer-state precision: every upstream and adapted
  parameter was stored as FP16, while the safe finite AdamW update still allowed large cumulative
  encoder drift and input-independent outputs.
- The checkpoint, manifest, and state recorded above remain preserved for audit under
  `artifacts/models/quarantine/step10-step11-finite-collapse-20260818/semantic-domain-fast-track/`.
  They must not be used as a production fold base.
- Remediation now forces the loaded model to FP32 before MPS training and records
  `training_dtype: float32` in the immutable run configuration. Domain publication additionally rejects
  a balanced smoke set unless logits vary by input and at least two labels are predicted.
- Fresh no-training remediation state: `artifacts/models/semantic-domain-fast-track.state.json`;
  SHA-256 `ea9ea60639d8316ecebde27c484f0685f364fe3f48bd249328dc5d33be29513e`;
  status `prepared`, attempts `0`. No replacement model directory exists.
- This discovery reopens Step 10. Its FP32 epoch requires explicit approval before execution.

### STEP_11 — semantic fold 1 attempt (invalidated by behavioral quality gate)

- Status: invalidated; do not proceed to Step 12
- Attempt completed at: 2026-08-18 11:49 +08
- Training execution: fold index `0`, `3,170` training rows, `830` holdout rows across `639` groups,
  two epochs, `398 / 398` optimizer steps, MPS, approximately `996.0` training seconds, exit code `0`.
- Structural checkpoint result: one attempt, exact expected-key coverage, `830` unique finite three-class
  logits, prediction SHA-256
  `04b34291c72562e2d58bf18b9dbe0be44b8667a6021ab36b8cfc5212fe922640`.
- Behavioral quality failure:
  - Actual holdout labels: `98` contradiction, `229` neutral, `503` entailment.
  - Predicted labels: `830` entailment, zero contradiction, zero neutral.
  - Accuracy: `0.606024`, exactly the majority-class baseline; contradiction and neutral recall were zero.
  - Entailment margin was essentially constant (`0.77338` to `0.77350`), and mean logits were identical
    across every actual label, proving the result did not distinguish inputs.
- The fold output and its state are preserved under
  `artifacts/models/quarantine/step10-step11-finite-collapse-20260818/semantic-fast-track/`.
- New safeguards:
  - Shared training now uses FP32 even when the bootstrapped checkpoint is stored as FP16.
  - Prediction batches fail immediately on non-finite logits.
  - Domain and fold runs reject single-class or effectively input-constant predictions.
  - Completed fold checkpoint validation independently rejects single-class collapse, so a structurally
    intact but useless checkpoint cannot be resumed as valid.
  - Fold and final Make targets explicitly enable safe MPS operation fallback.
- Updated code SHA-256 values:
  - `ml/semantic/train_multilingual.py`:
    `06a7c22619012fbb31a63f1333700a374682c8e142bcae18813494b6b771899e`.
  - `ml/semantic/train_domain.py`:
    `8dbce77e9aa76685427892dd4a325062010fd3b0360ff531eeb7736704411a2e`.
  - `ml/semantic/checkpoints.py`:
    `c33a04edeef0ad090906c9130bd124ab0e55d4e1a177340022e7362e6fee6e7b`.
- Test evidence after remediation implementation:
  - Focused domain/checkpoint suite: `11 passed`.
  - Full data/ML suite: `70 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: no fold index `1`, final semantic model, feature generation, CatBoost/fusion
  training, or evaluation was started.
- Original recovery gate (now satisfied): Step 10 remediation required explicit approval before the
  corrected domain run documented below.

### STEP_10_REMEDIATION — corrected domain pretraining

- Status: completed
- Completed at: 2026-08-18 13:38 +08
- Final checkpoint: `artifacts/models/semantic-domain-fast-track/` (approximately `712 MB`).
- Model version: `english-nli-option2-domain-v3`.
- Model/tree revision:
  `5cd7caa4331b576366bed8a6fa268058b663b9770cde43aa81d5dec8a8c63234`.
- Artifact manifest SHA-256:
  `b3d2ebf9684b2ab933a7dc7956033861ed5d689d34759db7279afbbf9edfd04a`.
- Completed state: `artifacts/models/semantic-domain-fast-track.state.json`; SHA-256
  `7bf7c49cf376fb76ec1c86cee8a7f35f0dc9c1c428208840643a357a23d1c919`;
  status `completed`, attempts `1` for the final version-3 state.
- Root causes established and fixed:
  - The upstream checkpoint's native classifier order is `[entailment, neutral, contradiction]`, while
    ACE's canonical order is `[contradiction, neutral, entailment]`. The original trainer renamed the
    config labels without reordering classifier weight/bias rows, so entailment examples were optimized
    against the upstream contradiction neuron.
  - Model loading now derives the upstream row indices from `id2label`, reorders classifier rows
    `[2, 1, 0]`, and only then sets the canonical config. The order is bound into every training state.
  - Option 2's observed training labels are highly imbalanced (`511` neutral, `6,009` entailment).
    Even after label-order correction, unweighted training collapsed to entailment. Domain loss now uses
    inverse-frequency weights `[0.0, 6.379647749510763, 0.5425195540023299]`, so all rows are used once
    while neutral and entailment contribute equally in aggregate.
  - Training parameters and optimizer state use FP32. AdamW remains bound to epsilon `1e-6` and
    `foreach=False` for MPS stability.
  - The classifier is frozen after canonical reordering. Eight fixed synthetic contradiction probes are
    validation-only and require at least six contradiction predictions before publication.
- Failed remediation evidence was preserved rather than deleted:
  - `artifacts/models/quarantine/step10-fp32-wrong-label-order-20260818/` contains the FP32 attempt that
    exposed the native/canonical classifier mismatch.
  - `artifacts/models/quarantine/step10-fp32-unweighted-collapse-20260818/` contains the canonical-label
    but unweighted attempt that exposed majority-class collapse.
- Pre-run weighted rehearsal: deterministic natural-imbalance subset of `512` rows (`470` entailment,
  `42` neutral), `32` training steps, both observed prediction classes, `0.69` balanced accuracy,
  maximum logit range `4.62346`, and `8 / 8` contradiction probes preserved.
- Successful full run: `6,520` training pairs, one epoch, `408 / 408` steps in `1,192.3` seconds
  (approximately `19m52s`), MPS, exit code `0`.
- Independent final validation on a larger balanced Option 2 sample:
  - Prediction counts: `128` neutral and `72` entailment across `200` rows.
  - Accuracy: `0.78`; this is materially above the `0.50` balanced majority baseline.
  - Per-class logit standard deviations: contradiction `0.25873`, neutral `1.22985`, entailment
    `1.30280`, confirming input-dependent representations.
  - Contradiction preservation: `8 / 8` fixed probes predicted canonical class `0`.
  - All `202` saved tensors are FP32 and finite.
  - Frozen classifier tensors exactly equal the upstream tensors after canonical `[2, 1, 0]` reordering.
  - Saved `id2label` is exactly `{0: CONTRADICTION, 1: NEUTRAL, 2: ENTAILMENT}`.
  - Idempotent manifest/state/tree verification passed and the staging directory is absent.
- Corrected fold-retry state: `artifacts/models/semantic-fast-track/training-state.json`; SHA-256
  `7a62a35b562430a8bae78bce7e71b5767245546232217187795752ae901994e7`.
  It is bound to reviewed Option 1 SHA-256
  `f0c1aab1f3d424f9b53d549b6e757f0072a31caf7f1241aa7259477998978050`, domain tree
  `5cd7caa4331b576366bed8a6fa268058b663b9770cde43aa81d5dec8a8c63234`, canonical label order,
  FP32, and unweighted fold loss. All five folds and final stage are pending at attempt `0`; no fold
  prediction exists.
- Updated implementation SHA-256 values:
  - `ml/semantic/train_multilingual.py`:
    `274bcb22dd01983ab849688fa06d6c6363ea1a3c4aba2bb8419fe37be9b239b1`.
  - `ml/semantic/train_domain.py`:
    `03e4d24e36e8e453e5598f9b335a664a9ed6a2f371c3f8284f0a0fc5962d60ea`.
  - `ml/semantic/checkpoints.py`:
    `c33a04edeef0ad090906c9130bd124ab0e55d4e1a177340022e7362e6fee6e7b`.
- Test evidence:
  - Focused domain/checkpoint tests after the final repair: `13 passed`.
  - Full data/ML suite: `72 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: the corrected Step 11 fold retry, fold index `1`, final semantic model, feature
  generation, CatBoost/fusion training, and evaluation were not started.
- Recovery: safe to shut down. Continue only after explicit approval for `STEP_11_RETRY` (fold index
  `0` against the corrected domain base).

### STEP_11_RETRY — corrected semantic fold 1

- Status: completed
- Completed at: 2026-08-18 15:50 +08
- Base checkpoint: `english-nli-option2-domain-v3`; immutable tree SHA-256
  `5cd7caa4331b576366bed8a6fa268058b663b9770cde43aa81d5dec8a8c63234`.
- Training execution: fold index `0`, `3,170` training rows, `830` held-out rows across `639` groups,
  two epochs, canonical labels, FP32, unweighted fold loss, MPS.
- Runtime: `398 / 398` steps in `1,101.8` seconds (approximately `18m22s`), followed by approximately
  `17.5` seconds of holdout inference; exit code `0`.
- Checkpoint: `artifacts/models/semantic-fast-track/folds/fold-0.predictions.jsonl`; exactly `830`
  unique rows; SHA-256 `949bdcedd9a45b527aecea20db9382361502a379120771211e1833cb4c6e0da1`.
- Training state: `artifacts/models/semantic-fast-track/training-state.json`; SHA-256
  `123dbf9da73d6b3df5a9e64acddf218f59391b57ed49b4d0ad1df81e868271d3`.
- Structural/integrity validation:
  - Holdout key SHA-256 exactly matches expected
    `2cd0fe45885660ad05670d1cc942c3d967238961cccac257a11ff36d0596dbdf`.
  - All logits are finite; per-class ranges are `5.231242`, `4.512721`, and `6.922128`, confirming
    input-dependent outputs.
  - Idempotent rerun validated and skipped the completed fold without invoking training.
  - Folds `1`–`4` and the final stage remain pending at attempt `0`.
- Behavioral result:
  - Actual labels: `98` contradiction, `229` neutral, `503` entailment.
  - Predicted labels: `45` contradiction, `303` neutral, `482` entailment; all three classes are active.
  - Accuracy: `0.687952`, above the `0.606024` majority-class baseline and the invalid prior attempt.
  - Macro-F1: `0.590210`.
  - Contradiction: precision `0.644444`, recall `0.295918`, F1 `0.405594`.
  - Neutral: precision `0.504950`, recall `0.668122`, F1 `0.575188`.
  - Entailment: precision `0.807054`, recall `0.773360`, F1 `0.789848`.
  - Confusion matrix, rows actual and columns predicted:
    `[[29, 42, 27], [10, 153, 66], [6, 108, 389]]`.
  - Contradiction recall is the weakest class and must be tracked across the remaining folds and final
    golden evaluation; it is no longer a collapse and does not invalidate this cross-fit checkpoint.
- Test evidence:
  - Full data/ML suite: `72 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: fold index `1`, later folds, final semantic model, feature generation,
  CatBoost/fusion training, and evaluation were not started.
- Recovery: safe to shut down. Continue only after explicit approval for `STEP_12` (fold index `1`).

### STEP_12 — semantic fold 2

- Status: completed
- Completed at: 2026-08-18 16:22 +08
- Base checkpoint: `english-nli-option2-domain-v3`; immutable tree SHA-256
  `5cd7caa4331b576366bed8a6fa268058b663b9770cde43aa81d5dec8a8c63234`.
- Preflight: `make semantic-fast-track-prepare` validated the immutable dataset, base model,
  configuration, fold assignments, and prior completed fold without modifying the state checksum.
- Training execution: fold index `1`, `3,247` training rows, `753` held-out rows across `596` groups,
  two epochs, canonical labels, FP32, unweighted fold loss, MPS.
- Runtime: `406 / 406` optimizer steps in `1,236.7` seconds (approximately `20m37s`), followed by
  holdout inference and artifact publication; exit code `0`.
- Checkpoint: `artifacts/models/semantic-fast-track/folds/fold-1.predictions.jsonl`; exactly `753`
  unique rows; SHA-256 `a0e09bc60a674ee18e78b1d775062801f2eacbbfe9d60d0f1ca256e24f1300a3`.
- Training state: `artifacts/models/semantic-fast-track/training-state.json`; SHA-256
  `651734e98795296ad84741013234857cf6c834574dababfcce92c83f61dec641`.
- Structural/integrity validation:
  - Holdout key SHA-256 exactly matches expected
    `eb9d5f1ff143884171d82b2b4608464b800c990fa52345edacfb0a8489d7f2f9`.
  - All logits are finite; per-class ranges are `6.406195`, `4.049955`, and `6.608197`, confirming
    input-dependent outputs.
  - Idempotent rerun validated and skipped the completed fold without invoking training.
  - Fold index `0` remains completed. Fold indices `2`–`4` and the final stage remain pending at
    attempt `0`.
- Behavioral result:
  - Actual labels: `86` contradiction, `197` neutral, `470` entailment.
  - Predicted labels: `58` contradiction, `156` neutral, `539` entailment; all three classes are active.
  - Accuracy: `0.693227`, above the `0.624170` majority-class baseline.
  - Macro-F1: `0.556424`.
  - Contradiction: precision `0.465517`, recall `0.313953`, F1 `0.375000`.
  - Neutral: precision `0.544872`, recall `0.431472`, F1 `0.481586`.
  - Entailment: precision `0.760668`, recall `0.872340`, F1 `0.812686`.
  - Confusion matrix, rows actual and columns predicted:
    `[[27, 27, 32], [15, 85, 97], [16, 44, 410]]`.
  - Contradiction recall remains the weakest class. This fold clears the non-collapse and
    above-majority checks, but class-level acceptance remains deferred to aggregate cross-fit and final
    golden evaluation.
- Test evidence:
  - Full data/ML suite: `72 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: fold index `2`, later folds, final semantic model, feature generation,
  CatBoost/fusion training, and evaluation were not started.
- Recovery: safe to shut down. Continue only after explicit approval for `STEP_13` (fold index `2`).

### STEP_13 — semantic fold 3

- Status: completed
- Completed at: 2026-08-18 16:53 +08
- Base checkpoint: `english-nli-option2-domain-v3`; immutable tree SHA-256
  `5cd7caa4331b576366bed8a6fa268058b663b9770cde43aa81d5dec8a8c63234`.
- Preflight: `make semantic-fast-track-prepare` validated the immutable dataset, base model,
  configuration, fold assignments, and two prior completed folds without modifying the state checksum.
- Training execution: fold index `2`, `3,205` training rows, `795` held-out rows across `626` groups,
  two epochs, canonical labels, FP32, unweighted fold loss, MPS.
- Runtime: `402 / 402` optimizer steps in `1,204.4` seconds (approximately `20m04s`), followed by
  approximately `25.8` seconds for holdout inference and artifact publication; exit code `0`.
- Checkpoint: `artifacts/models/semantic-fast-track/folds/fold-2.predictions.jsonl`; exactly `795`
  unique rows; SHA-256 `87a2c569684c2741076c42eab20564305de29da7dbc458f216475697280c5f07`.
- Training state: `artifacts/models/semantic-fast-track/training-state.json`; SHA-256
  `ea1c3c2b848c03370c8b34d8a67596e68ad1563360a281e7b4ca160310e1dea6`.
- Structural/integrity validation:
  - Holdout key SHA-256 exactly matches expected
    `ec9d5310c45e523ef7046fbab0aaf9e62bb89e6e9ecd9eba8ec7c047009b9031`.
  - All logits are finite; per-class ranges are `4.489186`, `3.893056`, and `5.963033`, confirming
    input-dependent outputs.
  - Idempotent rerun validated and skipped the completed fold without invoking training.
  - Fold indices `0`–`2` are completed once each. Fold indices `3`–`4` and the final stage remain
    pending at attempt `0`.
- Behavioral result:
  - Actual labels: `105` contradiction, `191` neutral, `499` entailment.
  - Predicted labels: `51` contradiction, `171` neutral, `573` entailment; all three classes are active.
  - Accuracy: `0.669182`, above the `0.627673` majority-class baseline.
  - Macro-F1: `0.514843`.
  - Contradiction: precision `0.470588`, recall `0.228571`, F1 `0.307692`.
  - Neutral: precision `0.461988`, recall `0.413613`, F1 `0.436464`.
  - Entailment: precision `0.748691`, recall `0.859719`, F1 `0.800373`.
  - Confusion matrix, rows actual and columns predicted:
    `[[24, 35, 46], [14, 79, 98], [13, 57, 429]]`.
  - Contradiction recall is again the weakest class and is lower than in the first two corrected folds.
    This fold clears the non-collapse and above-majority checks, but the growing class-level concern
    must be assessed across all cross-fit predictions and on the final golden evaluation before any
    promotion decision.
- Test evidence:
  - Full data/ML suite: `72 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: fold index `3`, fold index `4`, final semantic model, feature generation,
  CatBoost/fusion training, and evaluation were not started.
- Recovery: safe to shut down. Continue only after explicit approval for `STEP_14` (fold index `3`).

### STEP_14 — semantic fold 4

- Status: completed
- Completed at: 2026-08-18 17:30 +08
- Base checkpoint: `english-nli-option2-domain-v3`; immutable tree SHA-256
  `5cd7caa4331b576366bed8a6fa268058b663b9770cde43aa81d5dec8a8c63234`.
- Preflight: `make semantic-fast-track-prepare` validated the immutable dataset, base model,
  configuration, fold assignments, and three prior completed folds without modifying the state
  checksum.
- Training execution: fold index `3`, `3,204` training rows, `796` held-out rows across `623` groups,
  two epochs, canonical labels, FP32, unweighted fold loss, MPS.
- Runtime: `402 / 402` optimizer steps in `1,175.9` seconds (approximately `19m36s`); total recorded
  fold duration including model loading, holdout inference, and artifact publication was approximately
  `20m25s`; exit code `0`.
- Checkpoint: `artifacts/models/semantic-fast-track/folds/fold-3.predictions.jsonl`; exactly `796`
  unique rows; SHA-256 `d0fff282dfb82381b6811cb84da8ac457db2160a638bb9279fb2a7161cb98702`.
- Training state: `artifacts/models/semantic-fast-track/training-state.json`; SHA-256
  `a14d1b61f7ba5900028f20b13b9232d14d3d300eca4c80e6c34d803012101d64`.
- Structural/integrity validation:
  - Holdout key SHA-256 exactly matches expected
    `0accda4e3ace47f6e763af7ce081e772d5cdfea7bd54b8d511e9f2fda6c370a0`.
  - All logits are finite; per-class ranges are `6.789781`, `4.823664`, and `7.098459`, confirming
    input-dependent outputs.
  - Idempotent rerun validated and skipped the completed fold without invoking training.
  - Fold indices `0`–`3` are completed once each. Fold index `4` and the final stage remain pending at
    attempt `0`.
- Behavioral result:
  - Actual labels: `100` contradiction, `197` neutral, `499` entailment.
  - Predicted labels: `82` contradiction, `274` neutral, `440` entailment; all three classes are active.
  - Accuracy: `0.668342`, above the `0.626884` majority-class baseline.
  - Macro-F1: `0.565455`.
  - Contradiction: precision `0.402439`, recall `0.330000`, F1 `0.362637`.
  - Neutral: precision `0.467153`, recall `0.649746`, F1 `0.543524`.
  - Entailment: precision `0.843182`, recall `0.743487`, F1 `0.790202`.
  - Confusion matrix, rows actual and columns predicted:
    `[[33, 49, 18], [18, 128, 51], [31, 97, 371]]`.
  - Contradiction recall improved relative to folds `0`–`2`, but remains the weakest-class concern.
    Aggregate cross-fit and final golden evaluation are still required before any promotion decision.
- Test evidence:
  - Full data/ML suite: `72 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: fold index `4`, final semantic model, feature generation, CatBoost/fusion
  training, and evaluation were not started.
- Recovery: safe to shut down. Continue only after explicit approval for `STEP_15` (fold index `4`).

### STEP_15 — semantic fold 5 and aggregate cross-fit check

- Status: completed
- Completed at: 2026-08-18 17:54 +08
- Base checkpoint: `english-nli-option2-domain-v3`; immutable tree SHA-256
  `5cd7caa4331b576366bed8a6fa268058b663b9770cde43aa81d5dec8a8c63234`.
- Preflight: `make semantic-fast-track-prepare` validated the immutable dataset, base model,
  configuration, fold assignments, and four prior completed folds without modifying the state
  checksum.
- Training execution: fold index `4`, `3,174` training rows, `826` held-out rows across `649` groups,
  two epochs, canonical labels, FP32, unweighted fold loss, MPS.
- Runtime: `398 / 398` optimizer steps in `1,172.8` seconds (approximately `19m33s`); total recorded
  fold duration including model loading, holdout inference, and artifact publication was approximately
  `20m20s`; exit code `0`.
- Checkpoint: `artifacts/models/semantic-fast-track/folds/fold-4.predictions.jsonl`; exactly `826`
  unique rows; SHA-256 `8eb83516bbbc5aa8e249de516a9a8a16d2a868fb9bd1a2847dcc438cd175bb35`.
- Training state: `artifacts/models/semantic-fast-track/training-state.json`; SHA-256
  `2e0776af676c7c57cfd11902c130f67e1c2fdd5812dbf8a04849ef9cef55cfc2`.
- Structural/integrity validation:
  - Holdout key SHA-256 exactly matches expected
    `896d04ff96073559803d2e5d3f8c45c6f3ef582a1bf1e342d51e2c9466af6461`.
  - All logits are finite; per-class ranges are `5.729916`, `5.810069`, and `7.496066`, confirming
    input-dependent outputs.
  - Idempotent rerun validated and skipped the completed fold without invoking training.
  - All five cross-fit folds are completed once each. The final semantic stage remains pending at
    attempt `0`.
- Fold behavioral result:
  - Actual labels: `84` contradiction, `230` neutral, `512` entailment.
  - Predicted labels: `56` contradiction, `232` neutral, `538` entailment; all classes are active.
  - Accuracy: `0.668281`, above the `0.619855` majority-class baseline.
  - Macro-F1: `0.502799`.
  - Contradiction: precision `0.250000`, recall `0.166667`, F1 `0.200000`.
  - Neutral: precision `0.504310`, recall `0.508696`, F1 `0.506494`.
  - Entailment: precision `0.782528`, recall `0.822266`, F1 `0.801905`.
  - Confusion matrix, rows actual and columns predicted:
    `[[14, 42, 28], [24, 117, 89], [18, 73, 421]]`.
- Aggregate out-of-fold result across the complete 4,000-row training sample:
  - Coverage is exactly `4,000` unique semantic keys with no duplicate or missing row; combined key
    SHA-256 `d4357bfdd02832cb22d3a5ba48b5a0d5313678b5136aaf0841fd82d59af58ddd`.
  - Actual labels: `473` contradiction, `1,044` neutral, `2,483` entailment.
  - Predicted labels: `292` contradiction, `1,136` neutral, `2,572` entailment.
  - Accuracy: `0.677250`, above the `0.620750` majority-class baseline.
  - Macro-F1: `0.548944`.
  - Contradiction: precision `0.434932`, recall `0.268499`, F1 `0.332026`.
  - Neutral: precision `0.494718`, recall `0.538314`, F1 `0.515596`.
  - Entailment: precision `0.785381`, recall `0.813532`, F1 `0.799209`.
  - Confusion matrix: `[[127, 195, 151], [81, 562, 401], [84, 379, 2020]]`.
  - The complete cross-fit signal is better than the majority baseline and non-collapsed, but
    contradiction recall of `0.268499` is a material class-level risk. It must remain visible through
    final-model, fusion, and golden evaluation gates; it precludes an unqualified promotion decision.
- Test evidence:
  - Full data/ML suite: `72 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: final semantic-model training, feature generation, CatBoost/fusion training,
  and evaluation were not started.
- Recovery: safe to shut down. Continue only after explicit approval for `STEP_16`.

### STEP_16 — final semantic model, held-out predictions, and calibration

- Status: completed
- Completed at: 2026-08-18 19:10 +08
- Base checkpoint: `english-nli-option2-domain-v3`; immutable tree SHA-256
  `5cd7caa4331b576366bed8a6fa268058b663b9770cde43aa81d5dec8a8c63234`.
- Preflight: `make semantic-fast-track-prepare` validated all five fold artifacts and placed the state
  at `ready_to_finalize`; final attempts were `0` before execution.
- Training execution: all `4,000` training rows, `5,608` validation rows, two epochs, canonical labels,
  FP32, unweighted loss, MPS, micro/effective batch size `16`.
- Runtime: `500 / 500` optimizer steps in `1,628.5` seconds (approximately `27m09s`). Total recorded
  final-stage duration was approximately `43m23s`, including model loading/writing, inference over
  `17,216` non-training rows, temperature selection, and atomic publication; exit code `0`.
- Final model: `artifacts/models/semantic-fast-track/model/`; tree SHA-256
  `0158b350e9b1a90e7faa254049e42564bdaee0f76443138fbae764843c2f4f94`.
- Manifest: `artifacts/models/semantic-fast-track/manifest.json`; SHA-256
  `e3ea66b8a6aaa58587a6e461e0dcc50a63fa8e77ee7fc2ecd5802e03fe9cc37c`.
- Semantic predictions: `artifacts/models/semantic-fast-track/semantic-predictions.jsonl`; SHA-256
  `ec486236d317d7f98861d820d119a9be8f4cab4fffb425550e6ea1c3bdf64ce1`.
- Completed training state: `artifacts/models/semantic-fast-track/training-state.json`; SHA-256
  `ef8ffdeda26f981b8325f93cf782e85d007fbc2b4736fb398380bb98322b6fe3`;
  final attempts `1`, all five folds completed once each.
- Calibration: selected temperature `1.55` from the `5,608` calibration rows.
- Structural/integrity validation:
  - Exactly `21,216` unique prediction keys match the complete semantic dataset; key SHA-256
    `bac11465060709b244ed0af4be5c11135cb16d4809839d370cd74165bd0a8b21`.
  - Split coverage is exactly `4,000` train, `5,608` validation, `5,608` calibration, and `6,000`
    golden rows.
  - Prediction origins are exactly `4,000` cross-fit training rows and `17,216` held-out rows.
  - Every probability is finite, within `[0, 1]`, and the three classes sum to one per row.
  - Probability ranges are contradiction `[0.005248, 0.917324]`, neutral `[0.006412, 0.916169]`,
    and entailment `[0.033225, 0.986578]`, confirming non-collapsed outputs.
  - Saved labels are exactly `{0: CONTRADICTION, 1: NEUTRAL, 2: ENTAILMENT}`.
  - The independently recomputed model-tree hash matches the manifest.
  - Idempotent `make semantic-fast-track-finalize` returned the saved manifest without retraining or
    increasing attempts.
- Validation-split behavioral result (`5,608` rows):
  - Actual labels: `677` contradiction, `1,407` neutral, `3,524` entailment.
  - Predicted labels: `335` contradiction, `1,796` neutral, `3,477` entailment.
  - Accuracy: `0.695257`, above the `0.628388` majority-class baseline.
  - Macro-F1: `0.566337`.
  - Contradiction: precision `0.495522`, recall `0.245199`, F1 `0.328063`.
  - Neutral: precision `0.500557`, recall `0.638948`, F1 `0.561349`.
  - Entailment: precision `0.815070`, recall `0.804200`, F1 `0.809599`.
  - Confusion matrix: `[[166, 309, 202], [67, 899, 441], [102, 588, 2834]]`.
- Calibration-split behavioral check (`5,608` rows): accuracy `0.680635` versus `0.621790` majority
  baseline, macro-F1 `0.556302`, contradiction recall `0.251778`.
- Golden handling: all `6,000` golden rows were checked for unique keys, held-out origin, and valid
  probabilities only. Their labels were not scored here; formal golden and policy evaluation remains
  reserved for STEP_19.
- Quality caveat: the final semantic model is non-collapsed and materially above its majority baseline,
  but contradiction recall remains weak. This must be retained as an explicit gate through features,
  fusion, and formal golden evaluation; the result does not justify automatic promotion.
- Test evidence:
  - Full data/ML suite: `72 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: STEP_17 feature generation, CatBoost/fusion training, and formal evaluation were
  not started.
- Recovery: safe to shut down. Continue only after explicit approval for `STEP_17`.

### STEP_17 — complete semantic predictions and canonical features

- Status: completed
- Completed at: 2026-08-18 19:30 +08
- Preflight discovery: the STEP_16 artifact contained all `21,216` supervised semantic rows, but the
  reviewed 22,000-example dataset also contains `784` semantic constraints with no semantic or
  deviation label. They are intentionally unreviewed and occur only in validation (`392`) and
  calibration (`392`). The feature builder correctly refused to replace these missing scores with
  fabricated zeros.
- Implementation:
  - Added `nli_inference_rows`/`load_nli_inference_rows` so semantic constraints can be scored without
    making them eligible for supervised training; unlabeled rows use an internal `-1` sentinel only
    during inference and are published with `label: null`.
  - Added `ml/semantic/complete_predictions.py`, an atomic and resumable completion pass bound to the
    reviewed dataset, original STEP_16 predictions, semantic manifest, final model-tree hash, model
    version, and calibrated temperature.
  - Added `make semantic-fast-track-complete-predictions` and `make features-fast-track`, plus README
    operator documentation.
  - Added tests for inference-only row selection, exact merge behavior, calibrated probabilities,
    tamper rejection, and idempotent resume.
- Implementation SHA-256 values:
  - `ml/semantic/dataset.py`:
    `cb2a04dc663bd629c3f9cfc9d0ca2b2aa348035a683ba881e4b08f605f977785`.
  - `ml/semantic/complete_predictions.py`:
    `0939c7607a75cdc8972c528a6eb16edc87ae59a010dcaec934d400c5b0a89945`.
  - `tests/semantic/test_complete_predictions.py`:
    `3235dcc6d5230024c633d78762c23984c75957b8c00fc510573551690cdaf72a`.
- Completion execution:
  - Reused final model tree
    `0158b350e9b1a90e7faa254049e42564bdaee0f76443138fbae764843c2f4f94` and temperature `1.55`.
  - Performed inference only on the `784` missing rows; no optimizer, label mutation, or weight update.
  - Preserved all `21,216` STEP_16 prediction records exactly after parsing. The original artifact
    remains unchanged at SHA-256
    `ec486236d317d7f98861d820d119a9be8f4cab4fffb425550e6ea1c3bdf64ce1`.
  - Inferred predicted classes: `51` contradiction, `229` neutral, and `504` entailment; all classes
    are active and all probabilities are finite, bounded, and normalized.
- Complete prediction artifact:
  - `artifacts/models/semantic-fast-track/semantic-predictions.complete.jsonl`; exactly `22,000`
    unique semantic keys; SHA-256
    `bb03a146f44948bef0719a59e57564a662c5c7c3c432b781bede4c5cf8157865`.
  - Key SHA-256 `077dd52f6818bd600d261c0256ec0a9b3fad6da7e97bb18cb9c9812a42fe5a8a`.
  - Origins: `4,000` cross-fit, `17,216` held-out, `784` unlabeled inference-only.
  - Split coverage: `4,000` train, `6,000` validation, `6,000` calibration, `6,000` golden.
  - Completion manifest SHA-256
    `9278856ca710965c70dc6f730bc85dcbcf9c16f6a192ab09b8ff210610c735eb`.
  - Idempotent rerun returned `skipped: true` without loading the model or rerunning inference.
- Canonical feature artifact:
  - `ml/data/generated/fast-track/features-v2.jsonl`; exactly `22,000` unique examples; SHA-256
    `ef3e486c7b347568d70136dde968a660019ca9fd31d1764709b5368a03738818`.
  - `ml/data/generated/fast-track/features-v2.manifest.json`; SHA-256
    `a2cfaab060f61f78266689dbfbfb91c51001d7953d4350755861a0f9a571edfb`.
  - Manifest binds reviewed dataset SHA-256
    `f0c1aab1f3d424f9b53d549b6e757f0072a31caf7f1241aa7259477998978050`, complete-prediction
    SHA-256 `bb03a146f44948bef0719a59e57564a662c5c7c3c432b781bede4c5cf8157865`, semantic model
    version `english-nli-v3`, feature version `features-v2`, and the exact 15-feature order.
  - Deterministic rebuild reproduced the same feature checksum with zero missing predictions.
  - Split coverage: `4,000` train, `6,000` validation, `6,000` calibration, `6,000` golden across
    `18,133` groups, with zero cross-split groups.
  - Labels retained without fabrication: `9,709` match (`0`), `7,641` violation (`1`), and `4,650`
    null. Supervised availability is `3,244` train, `4,578` validation, `4,607` calibration, and
    `4,921` golden rows; null-label rows remain available for inference but are excluded by trainers.
  - All 12 numeric features are finite, all 3 categorical features are populated, semantic scores
    exactly match the complete predictions, and no protected feature is present.
- Test evidence:
  - Focused completion/semantic/feature tests: `8 passed` before materialization.
  - Full data/ML suite: `75 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: CatBoost, grouped stacker, Platt calibrator, threshold selection, and formal
  evaluation were not started.
- Recovery: safe to shut down. Continue only after explicit approval for `STEP_18`.

### STEP_18 — CatBoost baseline, grouped stacker, calibrator, and threshold

- Status: completed
- Completed at: 2026-08-18 19:35 +08
- Isolation decision: existing root-level CatBoost/fusion files are older synthetic demo artifacts.
  STEP_18 wrote only to `artifacts/models/fast-track-fusion-v2/` and did not overwrite or promote any
  existing serving/demo bundle.
- Training hardening implemented before fitting:
  - Feature datasets now require a matching `features-v2` manifest, exact feature order, feature-file
    checksum, semantic prediction checksum, semantic model version, unique example IDs, finite values,
    populated categories, binary-or-null labels, and zero cross-split group leakage.
  - Train, calibration, and validation subsets must each contain both binary classes.
  - Grouped OOF folds explicitly verify disjoint train/holdout groups. OOF probabilities must cover
    every training row, remain finite/in-range, and vary with input.
  - CatBoost models and JSON/manifest files are written through temporary artifacts and atomically
    renamed.
  - Manifests now bind the feature manifest and semantic artifacts and record class counts, OOF fold
    composition, probability ranges, threshold target, and achieved false-step-up rate.
  - Added `make train-fast-track-v2` and retained `serving_approved: false` plus
    `model_hold_enabled: false`.
- Implementation SHA-256 values:
  - `ml/tabular/train_catboost.py`:
    `6343d8e9777f5becca9ec9ff1f5634d592bf581d5ebf5f3ed7fb3373e0fdcb88`.
  - `ml/fusion/train_fusion.py`:
    `5bb4295fa2a4f40799b5cac2bc94a42f75278415d6e2ce5bee36c3b441fc1a58`.
  - `tests/features/test_build_features.py`:
    `a8b2fca7c81197f2e909d8d851145e4032a1b9ae3b8252fa801d8279a906e818`.
  - `tests/evaluation/test_fusion_runtime.py`:
    `e4f71bd55f285f492ec71da2981071ab50c4ad5b38af953205fc7463a174bfa8`.
- Environment and immutable input:
  - CatBoost `1.2.10`; scikit-learn `1.9.0`; random seed `2026`.
  - Feature dataset/manifest SHA-256 values:
    `ef3e486c7b347568d70136dde968a660019ca9fd31d1764709b5368a03738818` and
    `a2cfaab060f61f78266689dbfbfb91c51001d7953d4350755861a0f9a571edfb`.
  - Training: `3,244` labeled rows (`1,837` match, `1,407` violation) across `2,789` groups.
  - Calibration: `4,607` labeled rows (`2,547` match, `2,060` violation).
  - Validation/threshold selection: `4,578` labeled rows (`2,559` match, `2,019` violation).
  - Five OOF holdouts contain `649`, `649`, `649`, `649`, and `648` rows; all contain both classes
    and no group overlaps. Combined OOF probability range: `[0.014372, 0.992387]`.
  - Golden rows used or scored during training: `0`.
- Execution: `make train-fast-track-v2` completed with exit code `0` in approximately `2.8` seconds.
- Standalone CatBoost baseline:
  - `catboost-v1.cbm`; SHA-256
    `a237e1272111aac92b359a7366308b8ba7bca3c99f514ff6177ccc8165e66970`.
  - Manifest SHA-256
    `76fbaeb8f643330cc1a2a76c9f5c2a988a2b762da33af483abd662894791ef3c`.
  - Early stopping selected iteration `113` / `114` trees.
  - Validation PR-AUC `0.968264`, ROC-AUC `0.968437`, log loss `0.222413`, Brier `0.067582`.
- Fusion bundle:
  - Base CatBoost `fusion-catboost-v2.cbm`; SHA-256
    `d1309f0ead2e07a8d2b6cdf46f5671685ec848b5308748640664daf60812057f`.
  - Stacker/calibrator `fusion-v2.json`; SHA-256
    `474ffa4ddf7effc7ba27192b2798ea15e55239b7622e8277cc45bac4621c96f7`.
  - Manifest SHA-256
    `e63f2515904a4b9620a8d1c9ceb81bfc20335df1dc296d63dbca12c9c42c2346`.
  - Stacker coefficients in declared feature order: `[-1.561074, 0.182942, 7.816809, 1.177057,
    0.0]`; intercept `-3.607106`. Calibrator coefficient `7.205909`; intercept `-3.461540`.
  - Calibrated validation PR-AUC `0.967594`, ROC-AUC `0.967830`, log loss `0.230325`, Brier
    `0.069219`; probability range `[0.033782, 0.976635]`.
- Validation-derived operating point:
  - Step-up threshold `0.3062713483`; model-only HOLD is disabled and has no threshold.
  - Confusion counts: TP `1,822`, FP `254`, TN `2,305`, FN `197`.
  - Violation recall `0.902427`, precision `0.877649`, accuracy `0.901485`, specificity `0.900742`.
  - False-step-up rate `0.099258`, within the configured `0.10` validation target.
- Required caveats for STEP_19:
  - Fusion is slightly worse than standalone CatBoost on every reported validation ranking/calibration
    metric, so it is not yet proven additive and must not be promoted on the threshold result alone.
  - The stacker's negative semantic-contradiction coefficient can arise from conditional redundancy
    with CatBoost, but it requires ablation review rather than causal interpretation.
  - Standalone CatBoost feature importance is led by `line_item_count` (`54.25%`), followed by
    cumulative utilization (`17.89%`) and semantic contradiction (`8.46%`). The dominant item-count
    signal may reflect the counterfactual data construction and must be checked for shortcut behavior
    on golden attack families.
- Runtime safety validation:
  - Standalone CatBoost artifact loads successfully through the live scorer contract.
  - The fusion scorer rejects the experiment manifest because it has not passed promotion.
  - No serving manifest or temporary artifact exists; model-only HOLD remains prohibited.
- Test evidence:
  - Focused training/manifest/runtime tests: `3 passed` after one legacy fixture was corrected to carry
    the required canonical example ID.
  - Full data/ML suite: `75 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Step-boundary check: no golden labels were scored, no formal evaluation report was generated, and no
  model was promoted or connected to the live API.
- Recovery: safe to shut down. Continue only after explicit approval for `STEP_19`.

### STEP_19 — golden evaluation, regression tests, and promotion-gate review

- Status: completed — promotion gate failed
- Completed at: 2026-08-18 20:01 +08
- Evaluation hardening completed before opening the golden split:
  - The evaluator now checksum-validates the feature dataset, feature manifest, semantic predictions,
    fusion manifest, CatBoost file, and stacker/calibrator file before scoring.
  - It rejects promoted artifacts and model-only HOLD, confirms group-safe input through the canonical
    feature validator, writes its report atomically, and reports real single-row plus batch latency.
  - Added comparable rules-only, semantic-only, CatBoost, rules+semantic+CatBoost, and calibrated-full
    experiments; CatBoost-without-semantic and TabM are explicitly marked `not_run` rather than using
    an invalid inference-time zeroing approximation or starting unapproved training.
  - Violation recall now correctly treats both HOLD and STEP_UP as interventions. HOLD remains reserved
    for observable deterministic critical failures, and false decline still means an erroneous HOLD on
    a legitimate purchase.
  - Promotion now requires a versioned golden report, the golden split declaration, a passed aggregate
    gate, and every recorded criterion to pass; changing only the top-level status cannot promote a
    failed result.
  - Added `make evaluate-fast-track-v2` and focused tests for STEP_UP recall, the complete experiment
    report, and inconsistent gate-attestation rejection.
- Pre-golden verification: Ruff, `git diff --check`, and all `17` focused evaluation tests passed.
- One-time golden execution:
  - Command: `make evaluate-fast-track-v2`; exit code `0`; approximately `7.7` seconds.
  - Input: `6,000` golden rows, of which `4,921` have binary labels (`2,766` legitimate and `2,155`
    violations); all `6,000` have treatment labels.
  - Report: `artifacts/reports/fast-track-v2-golden-evaluation.json`; SHA-256
    `43ef64be22161549a5db05cccf9bc1ddf66bf75e5706222a4acfad5c7c5a349a`.
  - Report bindings reproduce the feature dataset SHA-256
    `ef3e486c7b347568d70136dde968a660019ca9fd31d1764709b5368a03738818`, semantic-prediction SHA-256
    `bb03a146f44948bef0719a59e57564a662c5c7c3c432b781bede4c5cf8157865`, and fusion-manifest SHA-256
    `e63f2515904a4b9620a8d1c9ceb81bfc20335df1dc296d63dbca12c9c42c2346`.
- Golden results:
  - Primary ranking metric: violation recall `0.903480` at false-positive rate `0.098698`, with
    precision `0.877027` and evaluation-only threshold `0.284605`.
  - PR-AUC `0.966952`, ROC-AUC `0.969143`, Brier score `0.070581`, and expected calibration error
    `0.044709`; these ranking and calibration gates passed.
  - The validation-derived operational threshold `0.306271` within the complete deterministic policy
    produced violation recall `0.796537`, false-step-up rate `0.140636`, false-decline rate `0`, and
    intervention precision `0.868803`. Recall and false-step-up gates failed.
  - Minimum supported attack-family recall was `0.558780` on the untransformed `none` family, below
    the `0.80` floor; missing-required-evidence recall was `0.806548`, cumulative overspend and
    unrelated-add-on intervention recall were both `1.0`.
  - Full fusion PR-AUC was only `0.000410` below CatBoost and fixed-FPR recall was `0.001392` higher;
    both non-inferiority tolerances passed, but fusion still has no meaningful demonstrated lift.
  - The shortcut sensitivity test set only `line_item_count` to `1`: mean absolute probability change
    `0.122510`, p95 change `0.915028`, and treatment flip rate `0.113`. This confirms material reliance
    on a feature that exactly separates all `1,222` unrelated-add-on rows in this golden construction.
  - Single-row local scoring latency was p50 `0.0695 ms`, p95 `0.0796 ms`, and max `0.5280 ms`; the
    6,000-row batch took `51.66 ms`.
- Gate conclusion:
  - Report status is `failed_gate`; failed criteria are operational recall, operational false-step-up
    rate, and minimum attack-family recall.
  - The threshold was selected against calibrated model probabilities on binary validation labels,
    but fixed semantic/rule overrides add interventions outside that false-step-up budget. Also, the
    current binary trainer excludes ambiguous rows even when their reviewed treatment is STEP_UP.
    Both are candidate causes to validate using train/validation/calibration splits in remediation.
  - The original golden set is now unblinded. It may be retained as a regression set, but must not be
    used to tune the repaired model and then presented as an unbiased final evaluation. A fresh locked
    group-held-out set is required before reconsidering promotion.
- Implementation SHA-256 values:
  - `ml/evaluation/evaluate.py`:
    `cf3096408d1e3f0f50ef789d04eeacf7dda1feadda612bd4f2bdd92197bc9345`.
  - `ml/evaluation/metrics.py`:
    `c68ab79743288dae9f1cf66ea7df55b3ba6e9b68743888c4516086bb7603595e`.
  - `ml/fusion/promote.py`:
    `fa8ced8acec19ea1380057b184ec082600a9548f2f1eb04a1b262432c8a8db80`.
  - `tests/evaluation/test_fusion_runtime.py`:
    `ff902d398bba879b1e6c31aa87611296d1e8e14e758bf37fd4a5c66b01bbb462`.
  - `tests/evaluation/test_metrics.py`:
    `a20b6a2bfad86e7334e8ae7b1998ca4c85aabf3ddc306b5cde4da36effc9d8e7`.
- Final test evidence:
  - Full data/ML suite: `77 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Safety boundary: no `fusion-v2.serving.manifest.json` exists; experiment manifest still records
  `serving_approved: false` and `model_hold_enabled: false`; nothing was connected to the live API.
- Recovery: safe to shut down. The original 20-step plan (STEP_00 through STEP_19) is complete. Four
  remediation steps are proposed, starting with STEP_20, and none has been approved or started.

### STEP_20_REMEDIATION — non-golden diagnosis and corrected training/runtime contracts

- Status: completed
- Completed at: 2026-08-18 20:12 +08
- Scope boundary:
  - Diagnosis used train, validation, and calibration only; `golden_rows_scored: 0` is recorded in the
    report and all `6,000` original golden rows are listed only as excluded.
  - No fast-track remediation model was trained, no replacement holdout was created, no billable API
    work was submitted, and no serving artifact was written.
- Diagnosis artifact:
  - `artifacts/reports/step20-remediation-diagnosis.json`; SHA-256
    `ed641d375e04fe1f1c075e1c045b7aaccbaa8b81f8ce7f094155e403b653a1da`.
  - It is bound to feature dataset SHA-256
    `ef3e486c7b347568d70136dde968a660019ca9fd31d1764709b5368a03738818`, feature-manifest SHA-256
    `a2cfaab060f61f78266689dbfbfb91c51001d7953d4350755861a0f9a571edfb`, and old fusion-manifest
    SHA-256 `e63f2515904a4b9620a8d1c9ceb81bfc20335df1dc296d63dbca12c9c42c2346`.
- Non-golden findings:
  - At the old `0.306271` threshold, validation policy recall is `0.801902` and false-step-up rate is
    `0.148886`; calibration policy recall is `0.805292` and false-step-up rate is `0.133883`.
  - Fixed rule/semantic overrides alone consume `184 / 2,559` validation legitimate rows, a
    `0.071903` false-step-up rate before the model receives any budget.
  - Complete-policy threshold selection is feasible and chooses `0.786521`, producing validation
    false-step-up rate `0.099648`, but recall falls to `0.716628`. Threshold correction alone therefore
    cannot satisfy both gates.
  - Binary-deviation supervision omits `756` reviewed train rows whose binary label is null but whose
    expected treatment is STEP_UP. It also omits `1,030` such validation rows and `1,001` calibration
    rows. The policy-intervention target covers all `4,000` train rows and `5,608` reviewed rows in
    each held-out tuning split.
  - Shortcut construction is exact across the `16,000` non-golden rows: all `3,190` multi-item rows
    are `unrelated_add_on`, and all `3,190` unrelated-add-on rows are multi-item. `line_item_count`
    cannot remain in a promotable fast-track artifact.
- Remediation implementation:
  - Added declared feature profiles shared by training and serving: `full-v2`, `shortcut-safe-v2`,
    `no-semantic-v2`, and `shortcut-safe-no-semantic-v2`. Models with arbitrary feature order/profile
    are rejected.
  - Added explicit `binary_deviation` and `policy_intervention` targets. The latter maps APPROVE to `0`
    and both STEP_UP/HOLD to `1`, allowing reviewed ambiguous STEP_UP examples into fitting without
    fabricating binary deviation labels.
  - Added complete-policy threshold selection. Every candidate threshold runs the same critical HOLD,
    hard-failure, semantic-override, and model-escalation rules as serving, so all STEP_UP sources share
    one false-step-up budget. An impossible fixed-override budget fails explicitly.
  - CatBoost and fusion trainers now accept checksum-recorded feature profiles and target modes,
    construct categorical indexes for the selected profile, and bind complete-policy selection metrics
    into their manifests.
  - Fusion stack inputs are also profile-declared. The no-semantic candidate removes semantic inputs
    from both CatBoost and the logistic stacker; shortcut-safe candidates remove `line_item_count`.
  - Runtime scorers accept only declared feature and stack profiles. Promotion additionally requires a
    shortcut-safe profile, `policy_intervention` target, `complete-policy-validation-v1` threshold
    selection, and a matching evaluation-report profile.
  - Added dry-run-only Make targets `train-fast-track-v3-no-semantic` and
    `train-fast-track-v3-semantic`; both point to isolated `fast-track-remediation-v3` directories and
    neither was executed. README operator documentation explains their approval boundary.
- Candidate contracts prepared for STEP_22:
  - Structured baseline: `shortcut-safe-no-semantic-v2` + `policy_intervention`.
  - Semantic candidate: `shortcut-safe-v2` + `policy_intervention`.
  - Both retain model-only HOLD prohibition and will select thresholds on the complete policy.
- Implementation SHA-256 values:
  - `services/api/app/feature_contract.py`:
    `01c1568a40d038d19855e3921c05aae8fb5b55124d031d7efd7d869f75ae8724`.
  - `services/api/app/structured.py`:
    `bf54bf06598d2a906fa4d28606c325c4baf56f7aa8a6779ab722010ed58ec8f1`.
  - `ml/features/schema.py`:
    `ff90435c38900f4adf6f6717ee2132018f52766b9bd0d508df56d2dfcda88e5c`.
  - `ml/fusion/policy_selection.py`:
    `5dcd9ca80a92449766ba46bcf06848391a0588fa4f53ad8e2d9167c5d9d10519`.
  - `ml/fusion/diagnose_remediation.py`:
    `a38fbdf1a28ea6bc77f220e745ac648b4b8792fd0d9b965ad7cca50f9a330f27`.
  - `ml/fusion/train_fusion.py`:
    `23c19f421d447839bc642c65cf94a84682c62cc6d3792e9038fb1106461da47d`.
  - `ml/tabular/train_catboost.py`:
    `c3732237455da6fe9ef92f23bd7021bdc1169abfa6aa9a5b7776e03138360cd1`.
  - `ml/evaluation/evaluate.py`:
    `09266518cda715bdcc1c5e6c1dabf065289afcf5c3e0098413732246d229ed2e`.
  - `ml/fusion/promote.py`:
    `edc3e6a9d93729720a0263dd7748b93fe570be80cc1406b8ade4bcec98cb111c`.
  - `tests/evaluation/test_policy_selection.py`:
    `9719828bf3c8d7cfb038428d65fa7e40cbbca00f30834f2dd34474f2a0459a10`.
  - `tests/evaluation/test_fusion_runtime.py`:
    `2de420b27a2498eca67eda43a1dee6aab6b093b8a5635937660f75d05ce6d813`.
- Test evidence:
  - Focused evaluation/feature unit and component suite: `26 passed`.
  - Full data/ML suite: `84 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff, Make dry runs for both candidate commands, and `git diff --check`: passed.
- Safety boundary: `artifacts/models/fast-track-remediation-v3/` does not exist; the old experiment
  remains unpromoted, no serving manifest exists, and the live API behavior is unchanged.
- Recovery: safe to shut down. Continue only after explicit approval for `STEP_21`.

### STEP_21A_LOCAL_PREPARATION — replacement holdout freeze and blinded review queues

- Status: completed
- Completed at: 2026-08-18 20:28 +08
- Frozen holdout:
  - Dataset: `ml/data/generated/fast-track/replacement-holdout/replacement-holdout.blinded.jsonl`;
    `4,000` rows across `3,137` groups; SHA-256
    `fba24d1cea311c3eadfbcc8d0f20eb7fce3670440db1e1f7c61728eafe2aed0e`.
  - Manifest: `ml/data/generated/fast-track/replacement-holdout/manifest.json`; SHA-256
    `659dd9feec217e369623f770bac8ab1ac176a650f60b652fcb3db5be45dd4e0a`.
  - Source: the immutable 60,000-row Option 1 corpus; exclusion: all 22,000 rows and 18,133 groups in
    the prior fast-track corpus. The eligible unused pool contained `38,000` train rows across `29,867`
    groups.
  - Prior example, group, parent, and source-record overlap are all exactly zero. Every frozen row is
    reassigned to `golden`, every source label is stripped, and all `4,000` rows have
    `label_source=unreviewed`.
  - Representation is deterministic at seed `2027`; maximum total-variation distance is `0.004105`
    (`0.41%`) against the `0.08` gate, with no missing source category. The mix is `2,341`
    `real_public` and `1,659` `hybrid_grounded` rows.
  - Selected example, group, and source-record ID hashes are respectively
    `1ffb763cfec68e53b7ef67c83672099957616e684644420f647e99c9f3cb522d`,
    `e035e33aef5f6f2cf1b59adea6d21c0ae949998e9612c5da69d2328f970223de`, and
    `09d5e48f86f97e2326accb3067ae11e3fadbc5e27780a5cf16a6199082aeb950`.
- Blinded independent-review preparation:
  - Directory: `ml/data/annotations/replacement-holdout/`; manifest SHA-256
    `c12c41cc15547e81ad4fcc6d200a6549c76efc231cf0fcad4017679ab1ba35d9`.
  - Queue: `4,000` examples; SHA-256
    `02793ba2d91c815d0f66079e0e9fb66d1fcff0b58477ac9fe34ee54ca1f955bc`.
  - Reviewer A is pinned to `gpt-5.4-mini-2026-03-17`; reviewer B is pinned to
    `gpt-4.1-mini-2025-04-14`. Each has four 1,000-request shards, for `8,000` total requests.
  - Blind-provenance mode withholds generator transformation names and field-origin metadata from the
    models. Prompts retain only the mandate/cart/state evidence plus broad evidence and mandate origins.
    Validation reconstructs and compares every evidence payload and prompt exactly, in addition to
    checking dataset, queue, model, schema, shard, count, and checksum bindings.
- Cost estimate for the next approval gate:
  - The prior 2,500-example run actually used Reviewer A `2,902,999` input / `415,848` output tokens and
    Reviewer B `2,907,259` input / `224,728` output tokens.
  - Scaling those measured values by the new payload bytes and row count estimates A at `4.422M` input /
    `0.665M` output tokens and `$6.31`; B at `4.427M` input / `0.360M` output tokens and `$2.35`.
  - Expected reviewer total: `$8.66`; use `$7–$11` as the approval range. At the prior `28.88%`
    disagreement rate, approximately `1,155` examples would need later adjudication, estimated at
    approximately `$8.24`. Adjudication is not included in STEP_21B and will require separate approval.
- Implementation and documentation SHA-256 values:
  - `ml/data/freeze_replacement_holdout.py`:
    `afb52269f8e4973088b350eef53d9d976af07287b8f9e16d98df2e2d75d3480e`.
  - `ml/data/llm_annotations.py`:
    `69671fc872f444a8fd7fba4ddc59f91f666c5e3381d3050e515840404e9a438d`.
  - `tests/data/test_replacement_holdout.py`:
    `b8bbf6e9aa87a31f80d00377c41def4ffddf5e3c1f05aeb960098ab2902c7cb1`.
  - `tests/data/test_llm_annotations.py`:
    `42c42fb8854ff94b16c10e73f91a0f924d3601b4ab829b8fdd0a722f0ee1d9b1`.
  - `Makefile`: `abb8b63248cd60b0987fdfdf71f44a056f161d1adf8c350002471fe04d706de8`.
  - `README.md`: `ecc0123171c9f6a6707d5793bfac02d88d13379372c94820a070cee2e5eeedf7`.
- Verification evidence:
  - Canonical holdout validation: `4,000` rows, `3,137` groups, checksum passed.
  - Exact prepared-review validation: `8,000` requests across 8 shards passed.
  - Idempotent freeze rerun: returned `skipped: true` after verifying identical content.
  - Full data/ML suite: `87 passed`.
  - API suite: `23 passed`.
  - Web component suite: `6 passed` across `2` files.
  - Ruff and `git diff --check`: passed.
- Safety boundary: no replacement submission state exists, no file was uploaded, no new billable Batch
  job was created, no model training ran, and the live API remains unchanged.
- Recovery: safe to shut down. Six expected approval-gated steps remain: `STEP_21B`, `STEP_21C`,
  `STEP_21D`, `STEP_21E`, `STEP_22`, and `STEP_23`; a retry would add a contingency step. Continue only
  after explicit approval for `STEP_21B_REVIEWER_SUBMISSION`.

### STEP_21B_REVIEWER_SUBMISSION — submit two independent replacement-holdout reviews

- Status: completed; remote jobs continue independently
- Completed at: 2026-08-18 21:05 +08
- Approved billable scope: eight OpenAI Batch submissions covering the locally prepared `8,000`
  requests. No adjudication was prepared or submitted.
- Preflight evidence:
  - Annotation key file was present and non-empty; its contents were not printed or recorded.
  - Frozen dataset revalidated at `4,000` rows / `3,137` groups with SHA-256
    `fba24d1cea311c3eadfbcc8d0f20eb7fce3670440db1e1f7c61728eafe2aed0e`.
  - Prepared-review validation rechecked all `8,000` requests, pinned models, exact prompts and payloads,
    strict schemas, and shard checksums before submission.
- Reviewer A (`gpt-5.4-mini-2026-03-17`):
  - A-000: `batch_6a84533f9c7c8190ac09c3b7fa3b520f`.
  - A-001: `batch_6a845344278c81908f404b7a0e410a1d`.
  - A-002: `batch_6a84534667f08190b78b74414f9da666`.
  - A-003: `batch_6a84534953648190b996a7d068a717dd`.
- Reviewer B (`gpt-4.1-mini-2025-04-14`):
  - B-000: `batch_6a84586e5404819082dae945cb2fd373`.
  - B-001: `batch_6a84587746d8819092b4ce170b455c76`.
  - B-002: `batch_6a845895ea588190ba7a8519f4dc6ae6`.
  - B-003: `batch_6a84589b5644819097a373985796dc33`.
- Restart state directory: `ml/data/annotations/replacement-holdout/states/`. Each state binds its local
  input path and SHA-256 to one unique uploaded-file ID and one unique Batch ID.
- State SHA-256 values:
  - A-000: `a3caa81e00fa0f501f8d2b7d71ec1dd1dd2e9ba99ac8a2bf654e39455b7bc40a`.
  - A-001: `b53c6ef24cae656f55813d6bc31fcaadf3724f0069c3407138e032c283978387`.
  - A-002: `e15dd79632fcbf150a53ea3e19dd9d51872b22846e65f1d2f71ca66dc2d50807`.
  - A-003: `9d141c34749e232f890d7823fa8451d6e6577a98ce418840c22ffc137a998861`.
  - B-000: `74aefd1b75f0c7d9aab3c5be06fb15c706e3a0f75cc5c4ebebfb933a2b4b0f92`.
  - B-001: `28423de4bf076d25096dd05b9a21bc80ce0fa1daa90cfd4cc9eb8d5c2597d590`.
  - B-002: `b445626e66c1273522c91eeb260c03bb9c4eb9e63bbaa2f1c5406c08cfabee45`.
  - B-003: `52cf3d788dbb75b0e8963317c4a2b56726b2ecbe7ba21bb7c0d71a92a4ce374b`.
- Post-submission validation: eight states; four per role; eight unique Batch IDs; eight unique uploaded
  file IDs; initial status `validating` for all eight; no missing or extra shard.
- Test evidence:
  - Focused annotation and replacement-holdout suite: `12 passed`.
  - Focused Ruff checks and `git diff --check`: passed.
- Safety boundary: no status-wait loop, output download, review import, disagreement preparation,
  adjudication submission, model training, or serving change was performed.
- Recovery: the remote jobs continue if the laptop is closed. Five expected approval-gated steps remain:
  `STEP_21C`, `STEP_21D`, `STEP_21E`, `STEP_22`, and `STEP_23`; a failed request retry would add a
  contingency step. Continue only after explicit approval for `STEP_21C_REVIEWER_RESULTS`.

### STEP_21C_REVIEWER_RESULTS — active results checkpoint

- Status: remote reviewer processing complete; waiting for approval to resume local result processing
- Started at: 2026-08-18 21:08 +08
- Checkpointed at: 2026-08-20 10:25 +08
- Remote status at checkpoint:
  - Reviewer B (`gpt-4.1-mini-2025-04-14`): all four shards completed; `4,000 / 4,000` requests
    completed and `0` failed.
  - Reviewer A (`gpt-5.4-mini-2026-03-17`): all four shards completed; `4,000 / 4,000` requests
    completed and `0` failed.
  - State validation still reports eight states, eight unique Batch IDs, eight unique input-file IDs,
    exact four-per-role coverage, eight terminal `completed` statuses, and eight output-file IDs.
- Operator hardening added to `Makefile`: validation, status, resumable wait, resumable download, exact
  output validation, atomic review import, blind-provenance adjudication preparation, and exact
  adjudication-request validation targets for the replacement holdout.
- Verification evidence:
  - All new STEP_21C operator targets passed Make dry-run.
  - Focused LLM annotation suite: `10 passed`.
  - `git diff --check`: passed.
- Resume check at 2026-08-18 21:39 +08: refreshed the remote jobs and monitored several additional
  intervals. Status remained four Reviewer B shards complete and four Reviewer A shards in progress,
  with zero failed requests. Local state validation again confirmed exact 4+4 coverage and unique IDs.
- Resume check at 2026-08-18 21:59 +08: status again remained four Reviewer B shards complete and four
  Reviewer A shards in progress, with zero failed requests across all eight jobs. The OpenAI Batch API's
  supported `completion_window` is `24h`; that is the asynchronous processing deadline, not a prediction
  that each job needs 24 hours. The local poller was stopped without cancelling any remote job.
- Resume check at 2026-08-18 22:10 +08: refreshed and monitored the eight jobs again. Status remained
  four Reviewer B shards complete and four Reviewer A shards in progress, with zero failed requests.
  Exact state coverage and unique remote IDs revalidated; the local poller was stopped without cancelling
  or resubmitting any job.
- Resume check at 2026-08-18 22:22 +08: refreshed and monitored again with no state change. Reviewer B
  remains `4,000 / 4,000` complete; all four Reviewer A shards remain `in_progress` with zero failed
  requests. Exact state coverage and unique remote IDs revalidated; no job was cancelled or resubmitted.
- Resume check at 2026-08-18 22:34 +08: refreshed once with no state change. Reviewer B remains
  `4,000 / 4,000` complete; all four Reviewer A shards remain `in_progress` with zero failed requests.
  Exact state coverage and unique remote IDs revalidated; no local poll loop was needed.
- Resume check at 2026-08-18 22:46 +08: refreshed once with no state change. Reviewer B remains
  `4,000 / 4,000` complete; all four Reviewer A shards remain `in_progress` with zero failed requests.
  Exact state coverage and unique remote IDs revalidated; no local poll loop was needed.
- Resume check at 2026-08-19 07:50 +08: refreshed and briefly monitored with no state change. Reviewer B
  remains `4,000 / 4,000` complete; all four Reviewer A shards remain `in_progress` with zero failed or
  expired requests. Exact state coverage and unique remote IDs revalidated; the local poller was stopped
  without cancelling or resubmitting any job.
- Progress-diagnostic hardening at 2026-08-19 07:53 +08:
  - Status refreshes now preserve the official Batch timing fields, last-check/last-progress markers,
    request counters, usage, error metadata, and output-file availability instead of discarding them.
  - All Reviewer A jobs were created between `20:42:39` and `20:42:49` +08 on 2026-08-18 and entered
    `in_progress` between `20:42:47` and `20:43:40`. Their expiry deadline is approximately `20:42` +08
    on 2026-08-19.
  - At `07:53:32` +08, after `11.18` hours, every Reviewer A shard still reported `0 / 1,000` completed,
    `0` failed, zero input/output tokens, no output file, no error file, and no progress-state change since
    entering processing. Approximately `12.82` hours remained in the Batch completion window.
  - Reviewer B provides a healthy comparison: all four jobs completed between `21:06:47` and `21:12:09`
    +08 on 2026-08-18, with populated token usage and output files.
  - Implementation SHA-256: `ml/data/llm_annotations.py`
    `2341797cba581dc863ed05cb6bb5eb9fa46b0d56b8526477c8bd1c76356356c3`; test SHA-256:
    `d86762e78066c098de8492310aa68e56353ba8c5f8f1c0153ad104071a0f53dc`.
  - Focused annotation suite: `11 passed`; Ruff and `git diff --check`: passed.
- Resume/progress check at 2026-08-19 14:06 +08:
  - Reviewer A advanced from `0 / 4,000` at the 07:53 checkpoint to `2,747 / 4,000` (`68.675%`), with
    zero failed requests. Per-shard completed counts are `557`, `559`, `845`, and `786`.
  - All four jobs remain `in_progress`; no output or error file is available until a shard finishes.
    The API explicitly marked progress changed on the first refresh. Short follow-up samples over roughly
    90 seconds showed no further increment, confirming that reported completion is bursty.
  - The measured six-hour average is approximately `444` requests/hour. Applying that rate mechanically
    gives roughly `2.8` hours for the remaining `1,253` requests, but this is not a service guarantee.
  - Approximately `6.6` hours remain before the earliest Reviewer A expiry at `20:42:39` +08. The local
    poller was stopped without cancelling or resubmitting any job.
- Progress check at 2026-08-19 14:24 +08:
  - Reviewer A advanced by another `477` requests in approximately `18.1` minutes, from `2,747` to
    `3,224 / 4,000` (`80.6%`), with zero failures. Per-shard counts are now `813`, `780`, `845`, and
    `786`; the first two shards advanced while the latter two were unchanged during this interval.
  - `776` requests remain and approximately `6.3` hours remain before the earliest expiry. The very
    recent aggregate rate would imply roughly 30 minutes remaining, but uneven per-shard scheduling makes
    that only a directional estimate.
- Progress check at 2026-08-19 15:05 +08:
  - Reviewer A advanced by `115` requests in approximately `40.4` minutes, from `3,224` to
    `3,339 / 4,000` (`83.475%`), with zero failures. Per-shard counts are `863`, `845`, `845`, and `786`;
    the first two shards advanced while the latter two remained unchanged.
  - `661` requests remain and approximately `5.6` hours remain before earliest expiry. The most recent
    aggregate rate implies roughly `3.9` hours remaining, still inside the window but with less margin;
    Batch progress remains uneven and this is not a guarantee.
- Progress check at 2026-08-19 15:16 +08: no change from 15:05. Reviewer A remains
  `3,339 / 4,000` complete with zero failures and per-shard counts `863`, `845`, `845`, and `786`.
  Approximately `5.4` hours remain before earliest expiry.
- Progress check at 2026-08-19 15:38 +08: no change from 15:05. Reviewer A remains
  `3,339 / 4,000` complete with zero failures and per-shard counts `863`, `845`, `845`, and `786`.
  Approximately `5.1` hours remain before earliest expiry.
- Progress check at 2026-08-19 15:46 +08: no change from 15:05. Reviewer A remains
  `3,339 / 4,000` complete with zero failures and per-shard counts `863`, `845`, `845`, and `786`.
  Approximately `4.9` hours remain before earliest expiry.
- Progress check at 2026-08-19 16:20 +08:
  - Reviewer A advanced by `80` requests in approximately `33.5` minutes, from `3,339` to
    `3,419 / 4,000` (`85.475%`), with zero failures. Per-shard counts are now `863`, `845`, `925`, and
    `786`; only the third shard advanced during this interval.
  - `581` requests remain and approximately `4.37` hours remain before earliest expiry. The latest rate
    implies roughly `4.05` hours remaining, leaving little projected margin; Batch completion remains
    bursty, so neither completion nor expiry can yet be predicted confidently.
- Progress check at 2026-08-19 16:39 +08:
  - Reviewer A advanced by `28` requests in approximately `19.5` minutes, from `3,419` to
    `3,447 / 4,000` (`86.175%`), with zero failures. Per-shard counts are now `863`, `845`, `953`, and
    `786`; only the third shard advanced.
  - `553` requests remain and approximately `4.05` hours remain before earliest expiry. The latest rate
    implies roughly `6.4` hours remaining, outside the window, but the highly bursty history means this
    short-window projection is not reliable enough to declare expiry inevitable.
- Progress check at 2026-08-19 17:02 +08:
  - Reviewer A advanced by `148` requests in approximately `22.9` minutes, from `3,447` to
    `3,595 / 4,000` (`89.875%`), with zero failures. Per-shard counts are now `932`, `924`, `953`, and
    `786`; the first two shards advanced during this interval.
  - `405` requests remain and approximately `3.67` hours remain before earliest expiry. The latest burst
    rate implies roughly `1.05` hours remaining, restoring useful margin while still not guaranteeing
    completion because per-shard scheduling remains uneven.
- Progress check at 2026-08-19 17:08 +08:
  - Reviewer A advanced by `13` requests in approximately `5.2` minutes, from `3,595` to
    `3,608 / 4,000` (`90.2%`), with zero failures. Per-shard counts are now `943`, `926`, `953`, and
    `786`; only the first two shards advanced during this short interval.
  - `392` requests remain and approximately `3.58` hours remain before earliest expiry. Extrapolating
    this short interval gives roughly `2.6` hours remaining, but the third and fourth shards did not
    advance on this refresh, so the projection remains especially uncertain.
- Progress check at 2026-08-19 18:12 +08:
  - Reviewer A advanced by `216` requests in approximately `63.9` minutes, from `3,608` to
    `3,824 / 4,000` (`95.6%`), with zero failures. Per-shard counts are now `958`, `926`, `953`, and
    `987`; the fourth shard supplied most of this interval's progress and is now closest to completion.
  - `176` requests remain and approximately `2.51` hours remain before earliest expiry. The latest
    interval's aggregate rate implies roughly `52` minutes remaining, leaving useful projected margin,
    but all four shards still report `in_progress` and the estimate remains non-guaranteed.
- Progress check at 2026-08-19 18:15 +08: no change from 18:12. Reviewer A remains
  `3,824 / 4,000` complete (`95.6%`) with zero failures and per-shard counts `958`, `926`, `953`, and
  `987`. `176` requests remain, all four shards remain `in_progress`, and approximately `2.47` hours
  remain before earliest expiry.
- Progress check at 2026-08-19 18:21 +08: no change from 18:12. Reviewer A remains
  `3,824 / 4,000` complete (`95.6%`) with zero failures and per-shard counts `958`, `926`, `953`, and
  `987`. `176` requests remain, all four shards remain `in_progress`, and approximately `2.36` hours
  remain before earliest expiry.
- Progress check at 2026-08-19 18:37 +08: no change from 18:12. Reviewer A remains
  `3,824 / 4,000` complete (`95.6%`) with zero failures and per-shard counts `958`, `926`, `953`, and
  `987`. `176` requests remain, all four shards remain `in_progress`, and approximately `2.10` hours
  remain before earliest expiry.
- Progress check at 2026-08-19 18:44 +08: no change from 18:12. Reviewer A remains
  `3,824 / 4,000` complete (`95.6%`) with zero failures and per-shard counts `958`, `926`, `953`, and
  `987`. `176` requests remain, all four shards remain `in_progress`, and approximately `1.97` hours
  remain before earliest expiry.
- Progress check at 2026-08-19 19:42 +08: no change from 18:12. Reviewer A remains
  `3,824 / 4,000` complete (`95.6%`) with zero failures and per-shard counts `958`, `926`, `953`, and
  `987`. `176` requests remain and all four shards remain `in_progress`. Only approximately `1.01`
  hours remain before earliest expiry, so the risk of partial expiry is now material; no cancellation,
  retry, download, adjudication, training, or serving change was performed.
- Progress check at 2026-08-19 19:44 +08: no change. Reviewer A remains `3,824 / 4,000` complete
  (`95.6%`) with zero failures and per-shard counts `958`, `926`, `953`, and `987`. All four shards
  remain `in_progress` with no output or error file; approximately `59` minutes remain before earliest
  expiry.
- Progress check at 2026-08-19 20:16 +08: no change. Reviewer A remains `3,824 / 4,000` complete
  (`95.6%`) with zero failures and per-shard counts `958`, `926`, `953`, and `987`. All four shards
  remain `in_progress` with no output or error file. Approximately `27` minutes remain before earliest
  expiry, making partial expiry likely unless another processing burst occurs soon; no follow-on action
  was started.
- Completion check at 2026-08-20 10:25 +08:
  - All four Reviewer A shards reached `1,000 / 1,000`, so all eight reviewer jobs are now `completed`
    with `8,000 / 8,000` successful requests, zero failures, eight output-file IDs, and no error files.
  - Reviewer A entered `finalizing` between `20:42:02` and `20:42:19` +08 on 2026-08-19. Its four
    shards recorded completion between `20:42:37` and `20:43:11`; none expired despite finishing at the
    edge of the 24-hour window.
  - Reviewer A usage totals `4,430,747` input tokens and `699,166` output tokens, including `334,557`
    reasoning tokens. These remote usage figures are recorded before any local parsing or cost analysis.
- Safety boundary at checkpoint: this was a status-only check. No output was downloaded, no review
  database was created, no adjudication request was prepared or submitted, and no training or serving
  change occurred.
- Recovery: safe to shut down. After explicit approval, resume STEP_21C with
  `make replacement-holdout-download`, then validate outputs, import reviews atomically, prepare the
  blinded adjudication requests locally, validate them, calculate the exact STEP_21D cost, update this
  ledger, and stop for separate adjudication-submission approval.

#### STEP_21C reviewer-output validation and retry checkpoint

- Checkpointed at: 2026-08-20 10:33 +08
- Download result:
  - All eight output files downloaded with exactly `1,000` rows each; no remote output remains pending.
  - Reviewer A output SHA-256 values: `33e313ba75b0c2d123b2b583eaceb9871b49ad529fb4bd46b8bbc0be48cf2f08`,
    `0dcf5345f9d324f8877da8fd7dfd080bf91b121b9e7bb6134aa690b5aee6b20b`,
    `5ef9524fa4b602f3004faa64b5d33b04c685dc1c1f2b7c5606e0b58609f42544`, and
    `6e4ea236adda72841bd5ced91c32ec25328998d783edaf94922ceef84d282f3e`.
  - Reviewer B output SHA-256 values: `f0cba8418384cf33aed232243abebdb0bac2f0119cf9afc0712e4a98cdaae392`,
    `ed339941b02e5b4251758f6a3425979c7a78d17a219a31093307a5496482e9ad`,
    `d5a850d0cb90cf86c94d19e97ab4e14cd58782f2a405d1867faf317f754a8161`, and
    `140edad3c80443328a8154923f1b85ae375b636f284c97563490dbe3bc0bbbbe`.
- Validation result:
  - Import was blocked because two Reviewer A HTTP-200 responses have internal status `incomplete` and
    reason `max_output_tokens`. They consumed `500` output tokens each, mostly reasoning tokens, and
    their structured JSON answers were truncated.
  - Affected IDs are `llm-a-gpt-5.4-mini-2026-03-17:ace_cf_07b14db22f7ade0f` and
    `llm-a-gpt-5.4-mini-2026-03-17:ace_cf_d9070b974d1aae0f`. The other `7,998` output rows were not
    imported; atomic import remains intact.
- Contingency implementation:
  - Added generic review retry preparation, state-bound retry validation, and immutable directory merge
    support. The merge changes exactly the retried IDs in a new `validated-outputs/` directory, preserves
    the original downloads, and revalidates all `8,000` rows before import.
  - Added Make targets for prepare, submit, status/wait, download, retry validation, merge, full merged
    validation, and merged import; documented the operator sequence in `README.md`.
  - Implementation SHA-256: `ml/data/llm_annotations.py`
    `03cda8f2a50a9ae4e499beb0ce7c92e188cc141891a47ec098545eddf5ecdeae`; test SHA-256:
    `e22c40241385305a83d366e4d6273de7e6f82f045eba8d30e63ad6ba27517565`.
  - Focused annotation suite: `12 passed`; all four Reviewer B shards separately revalidated at
    `4,000 / 4,000`; Ruff, Make dry-run for every retry/merge/import target, and `git diff --check`:
    passed.
- Prepared retry artifact:
  - `ml/data/annotations/replacement-holdout/review-a.retry-01.jsonl`: exactly `2` requests, pinned
    `gpt-5.4-mini-2026-03-17`, unchanged blinded inputs/prompts/schema/reasoning configuration, and only
    `max_output_tokens` raised from `500` to `1,000`; SHA-256
    `03f1a892d4baa1e940a8f39f65cb0f9b81da1b939392c5d538840eeb95bad839`.
  - Manifest: `ml/data/annotations/replacement-holdout/review-a.retry-01.manifest.json`; SHA-256
    `c9c3b52fa7d373b406a2fa16a98df289f3eceacc66aca440bbe76e37381b5ffd`.
- Cost ceiling: the two original prompts used `2,468` input tokens total. At the current official
  GPT-5.4 mini Batch prices of `$0.75/M` input and `$4.50/M` output, retrying with at most `2,000`
  combined output tokens costs at most approximately `$0.010851` on the standard endpoint; actual cost
  should be lower if the responses finish below the cap.
- Safety boundary: no retry state or Batch ID exists, no new billable job was submitted, no review
  database or adjudication request exists, and no training or serving change occurred.
- Recovery at that checkpoint was to await `STEP_21C_REVIEWER_RETRY_SUBMISSION`; that submission is now
  complete and recorded below.

#### STEP_21C_REVIEWER_RETRY_SUBMISSION — completed

- Submitted at: 2026-08-20 11:13 +08
- Batch ID: `batch_6a8670bf418481908fb16547839f8031`
- Input file ID: `file-7sZYuHeayy55jjKbbU1isf`
- Input: `ml/data/annotations/replacement-holdout/review-a.retry-01.jsonl`; SHA-256
  `03f1a892d4baa1e940a8f39f65cb0f9b81da1b939392c5d538840eeb95bad839`; exact `2` requests.
- Initial remote state:
  - Created at `11:13:03`, entered `in_progress` at `11:14:06`, and was checked at `11:15:45` +08.
  - Status `in_progress`; request counts `0 / 2` completed and `0` failed; no output or error file yet.
  - Official completion window `24h`; expiry recorded as 2026-08-21 11:13:03 +08.
- State: `ml/data/annotations/replacement-holdout/review-a.retry-01.state.json`; SHA-256
  `8753408b94632d264b0b99ad4862f745dc9a49ed8304c7fb4ecfac4c9e027eef`.
- Timing estimate:
  - Practical expectation for this two-request job: roughly `5–30 minutes`; a conservative planning
    allowance is `1–2 hours` because Batch scheduling is asynchronous and not size-proportional.
  - The only service-backed upper boundary is the `24h` completion window; the practical estimate is not
    guaranteed. The job already entering processing after `63` seconds is a healthy initial signal.
- Safety boundary: exactly one approved retry Batch was submitted. No output was downloaded, no merge or
  import occurred, no review database or adjudication request exists, and no training or serving change
  occurred.
- Recovery: safe to shut down; the remote job continues independently. Continue only after explicit
  approval for `STEP_21C_REVIEWER_RETRY_RESULTS`, beginning with
  `make replacement-holdout-review-retry-status`.

#### STEP_21C_REVIEWER_RETRY_RESULTS — completed

- Completed at: 2026-08-20 12:40 +08
- Retry Batch result:
  - Batch `batch_6a8670bf418481908fb16547839f8031` completed `2 / 2` requests with zero
    failures, output file `file-Pv9swDmeJ7ga6b5gPPxxYG`, and no error file.
  - Created at `11:13:03`, entered `in_progress` at `11:14:06`, entered `finalizing` at
    `11:31:09`, and completed at `11:31:10` +08: `18m07s` from creation.
  - Usage was `2,468` input tokens and `584` output tokens, including `372` reasoning tokens
    (`3,052` total). At standard GPT-5.4 mini Batch rates, the estimated retry charge is
    approximately `$0.00448`.
  - Downloaded output: `ml/data/annotations/replacement-holdout/review-a.retry-01.output.jsonl`;
    SHA-256 `77862eb5cafb55beccbffa167e69441a4638c2956872e0fceea308b58bfa9e37`.
  - Final state SHA-256: `9fddb5a77df723ca34eb8845aa605cc8ca9fbfba7b053f5cd97f1f76a2124e73`.
- Validation and immutable merge:
  - The two responses passed strict request/state/output binding, schema, model, reviewer, and
    completeness validation.
  - Exactly the two truncated Reviewer A rows were replaced in the separate
    `validated-outputs/` directory; the eight original downloads were not modified.
  - Full-corpus revalidation passed for exactly `8,000` responses: `4,000` Reviewer A and `4,000`
    Reviewer B, all bound to dataset SHA-256
    `fba24d1cea311c3eadfbcc8d0f20eb7fce3670440db1e1f7c61728eafe2aed0e`.
  - Final merged output SHA-256 values are Reviewer A:
    `4cbf4d1a2ea772d006472581c0e0f3889691adb796113d266574b5d577061d23`,
    `d05a3867b4620614d53db0e74bc47340f69270964cb969e4a6bd9b337dc2f6dd`,
    `e545c488985c900724eb8d310a7ffc1a5561b8301402bcdd180f1038c6f66101`, and
    `96fca6bbb0f702a3bee57d74be8f924902495f0a5cc5fb98d6290a1e157ac9d8`; Reviewer B:
    `e3f7e694777b0b049ae22cb6ccb9361e0d86e854469bb5b44a0730b951f81b17`,
    `d31ad506bf5a88dddf7628a42ab31c5123114a3db6fc0d2d15d485958a9c8621`,
    `30c611270617a5d61af8109745121c068e1b5e7901a12c3890428cc4d389053c`, and
    `c45006bbb0b4b83375cab11ce802a59f85678a5af3b9f157e127cb4bf9dc3eba`.
- Atomic import result:
  - Database: `ml/data/annotations/replacement-holdout/reviews.sqlite3`; SHA-256
    `dd1e7e42a516ca1df25870d3d6ab073d6a0eed348300110f77f10b2eefc3e915`.
  - Imported `8,000` review rows with zero failures: `4,000` examples have both independent reviews.
  - `2,715` examples agree and `1,285` need adjudication; no example is single-reviewed, unreviewed,
    or already adjudicated.
  - Repeating the complete import produced the identical physical database SHA-256, confirming
    idempotency.
- Blinded adjudication preparation:
  - Input: `ml/data/annotations/replacement-holdout/adjudication.jsonl`; exactly `1,285` requests;
    SHA-256 `9f29919b6b0a85325f9b04284db03bc156c28cd5dccf5f200410dc7866193681`.
  - Manifest: `ml/data/annotations/replacement-holdout/adjudication.manifest.json`; SHA-256
    `163aab7ad0ea6521a4a2c79e4eec7f68e05efa1560b5da7d1ca814992d220a86`.
  - Every request is blinded, covers one current disagreement exactly once, contains the two conflicting
    reviews, and is bound to the current dataset and review-database checksums. The model is pinned to
    `gpt-5.4-2026-03-05`; all `1,285` examples are from the locked `golden` split.
- STEP 21D cost planning:
  - The exact charge cannot be known before execution because OpenAI bills the server-measured input and
    generated/reasoning output tokens. The closest evidence-backed projection scales the completed
    722-request adjudication's measured usage by the new input-file size and request count: approximately
    `1,739,867` input and `307,588` output tokens.
  - GPT-5.4 standard rates (`$2.50/M` input and `$15/M` output) produce `$8.96` of standard-endpoint
    math for that projected usage. Applying the Batch API's documented 50% discount gives a projected
    Batch charge of approximately `$4.48`. The configured `500`-token output cap is exactly `642,500`
    tokens across the queue; applying the same discount to the projected input plus that hard output cap
    gives a conservative Batch planning figure of approximately `$7.00`.
- Verification: adjudication coverage/binding validation passed; focused annotation and replacement
  holdout tests: `14 passed`; Ruff: passed; `git diff --check`: passed.
- Safety boundary and recovery: no adjudication state file, OpenAI input file, or Batch ID was created;
  no adjudication request was submitted; no training or serving change occurred. It is safe to shut down.
  Continue only after explicit approval for `STEP_21D_ADJUDICATION_SUBMISSION`.

### STEP_21D_ADJUDICATION_SUBMISSION — completed

- Submitted at: 2026-08-20 12:52 +08
- Preflight evidence:
  - Revalidated exactly `1,285` unique, blinded, current disagreements against the immutable dataset and
    review-database checksums immediately before submission.
  - Input remained pinned to `gpt-5.4-2026-03-05`; SHA-256
    `9f29919b6b0a85325f9b04284db03bc156c28cd5dccf5f200410dc7866193681`.
  - Focused annotation and replacement-holdout tests: `14 passed`; Ruff and `git diff --check`: passed.
- Submission result:
  - OpenAI input file ID: `file-KHKnPDsF4X2h5ygV2FcoUR`.
  - OpenAI Batch ID: `batch_6a86882b39408190b1394b74d927fef7`.
  - Initial status returned by the submission request: `validating`.
  - Resumable state: `ml/data/annotations/replacement-holdout/adjudication.state.json`; SHA-256
    `b32a374588d04baa2d10167459facca39f997e624211a707921da606efb8103c`.
- Operator support added: replacement-holdout Make targets now cover submission, status, resumable wait,
  download, and strict output validation using the same state and input paths; all commands were dry-run
  checked before submission.
- Cost and timing: projected Batch charge is approximately `$4.48`, with `$7.00` as the conservative
  planning figure based on the documented 50% Batch discount, hard output-token cap, and projected input
  usage. Exact usage and charge are unavailable until the job finishes. The API completion window is up
  to `24h`; actual queue time is asynchronous and may be much shorter.
- Safety boundary: exactly one approved adjudication Batch was submitted. No subsequent status request,
  wait loop, output download, validation, import, reviewed-holdout export, training, or serving change was
  performed.
- Recovery: the remote Batch continues with the laptop closed. Resume with explicit approval for
  `STEP_21D_ADJUDICATION_STATUS`; after it completes, `STEP_21E` requires separate approval for local
  results processing.

#### STEP_21D_ADJUDICATION_STATUS — 2026-08-20 13:01 +08

- Read-only live result: `in_progress`, `1,271 / 1,285` requests completed (`98.91%`), zero failed,
  and only `14` remaining. The API reported that progress changed on this check.
- Timeline: created at `12:52:59`, entered `in_progress` at `12:54:01`, and checked at `13:01:09`
  +08. The Batch processed the first `1,271` requests within approximately eight minutes of creation.
- Updated resumable state SHA-256:
  `934a57adbb139aa0ed9b53c2c9e9f037ec17337c72ce171113f555c92b4d9b1c`.
- Decision: do not cancel or replace this job. With `98.91%` already complete, switching to synchronous
  processing would duplicate nearly all work, cost more, and likely finish later. No cancellation,
  synchronous fallback, download, import, training, or serving change was performed.
- Recovery: leave the remote job running. Approve another `STEP_21D_ADJUDICATION_STATUS` check; once it
  reports `completed`, request separate approval for `STEP_21E` results processing.

#### STEP_21D_ADJUDICATION_STATUS — 2026-08-20 13:02 +08

- Read-only live result: `finalizing`; all `1,285 / 1,285` requests finished and zero failed.
- The Batch entered `finalizing` at `13:02:03` and was checked at `13:02:33` +08. It does not yet expose
  an output-file ID, so results cannot be downloaded safely at this checkpoint.
- Updated resumable state SHA-256:
  `1ca1184f87885bfcd42bcb0b69bbe8e05d9119eb6fadedfe19bdf38e01c5f76c`.
- Safety boundary: no second poll, download, import, training, or serving change was performed.
- Recovery: approve one more `STEP_21D_ADJUDICATION_STATUS` check. Once the state is `completed` and an
  output-file ID exists, proceed only with separate approval for `STEP_21E` results processing.

#### STEP_21D_ADJUDICATION_STATUS — completed at 2026-08-20 13:04 +08

- Final read-only result: Batch `batch_6a86882b39408190b1394b74d927fef7` is `completed` with
  `1,285 / 1,285` transport successes, zero failures, no error file, and output file
  `file-FmPujN5w5Q9wpPrRafHtJz` ready for download.
- Timing: created at `12:52:59`, entered processing at `12:54:01`, entered finalization at `13:02:03`,
  and completed at `13:02:53` +08: `9m54s` from creation.
- Measured usage: `1,746,374` input tokens and `326,678` output tokens, including `181,092` reasoning
  tokens (`2,073,052` total). Applying GPT-5.4 standard rates and the documented 50% Batch discount gives
  an estimated charge of approximately `$4.63` (`$9.27` standard-rate equivalent).
- Final resumable state SHA-256:
  `b981de1656c6c41861e00a62a649bd83e86f36c75446fc17af9a0cc7cb73f03d`.
- Safety boundary: this approval performed only one status retrieval. No output download, response-level
  validation, import, reviewed-holdout export, training, or serving change was performed.
- Recovery: safe to shut down. Continue only after explicit approval for
  `STEP_21E_ADJUDICATION_RESULTS`.

### STEP_21E_ADJUDICATION_RESULTS — validation checkpoint

- Checkpointed at: 2026-08-20 13:08 +08
- Downloaded original adjudication output:
  - Path: `ml/data/annotations/replacement-holdout/adjudication.output.jsonl`; exactly `1,285` physical
    rows and `8,560,624` bytes; SHA-256
    `48262162a96f8dcad6489a1b1523474831bd640fb76e582eef64a9d5edf57a99`.
  - Download-updated Batch state SHA-256:
    `fbc45ddbdf5365fe046010d427495cd244b220a7822768f6401ea47213f0a3aa`.
- Strict response-level validation result:
  - `1,280` responses are complete and five responses have internal status `incomplete` with reason
    `max_output_tokens`. Each affected response used the original `500`-token cap, including substantial
    hidden reasoning, before structured output completed.
  - Affected example IDs are `ace_cf_22f51c0c3bce3ac5`, `ace_cf_6069b9ccb7f9ba1a`,
    `ace_cf_a169aa81b7cf9ccd`, `ace_cf_d430e26edb93219e`, and `ace_cf_e26f4e9e55921cf4`.
  - The validation gate stopped all downstream writes. Review database SHA-256 remains
    `dd1e7e42a516ca1df25870d3d6ab073d6a0eed348300110f77f10b2eefc3e915`; it still contains zero
    adjudications. No validated merged output or reviewed replacement-holdout export exists.
- Prepared local retry:
  - Input: `ml/data/annotations/replacement-holdout/adjudication.retry-01.jsonl`; exactly five requests,
    pinned `gpt-5.4-2026-03-05`, unchanged prompts/schema/reasoning, and only the output-token cap raised
    from `500` to `1,000`; SHA-256
    `838fcd8f572343f8424e35ff0b144414b311ec58ba94eaea5695da7af2fa6a47`.
  - Manifest: `ml/data/annotations/replacement-holdout/adjudication.retry-01.manifest.json`; SHA-256
    `041082d5864e73f158e8ee5fa882a53755df40512dc5662c5d7580bb95797da2`. It binds the exact retry IDs
    to both the original input and downloaded-output checksums.
  - The five original requests used `5,462` input tokens total. At the documented GPT-5.4 Batch discount,
    the retry costs at most approximately `$0.04433` if all five consume the full new output cap; actual
    cost should be lower.
- Operator support: added Make targets for retry submission/status/wait/download/validation, immutable
  merge, adjudication import, reviewed-holdout export, and final dataset/manifest validation.
- Verification: all new operational targets passed Make dry-run; focused annotation, replacement-holdout,
  and export tests: `16 passed`; Ruff and `git diff --check`: passed.
- Safety boundary and recovery: no retry state, input-file ID, or Batch ID exists; nothing was imported or
  exported; no training or serving change occurred. Safe to shut down. Continue only after explicit
  approval for `STEP_21E_ADJUDICATION_RETRY_SUBMISSION`.

#### STEP_21E_ADJUDICATION_RETRY_SUBMISSION — completed

- Submitted at: 2026-08-20 13:12 +08
- Preflight regenerated the retry deterministically and confirmed unchanged source input, source output,
  retry input, manifest, model, five custom IDs, and `1,000`-token cap bindings.
- OpenAI input file ID: `file-1GbJJymFxm2t9RhcoYTWJa`.
- OpenAI Batch ID: `batch_6a868c9dba388190ba0dab3dad9ad66a`.
- Initial submission status: `validating`.
- Resumable state: `ml/data/annotations/replacement-holdout/adjudication.retry-01.state.json`; SHA-256
  `6f8d07048c5a7520f74d9c6d5fd2e09075ee8aa1d983d9bb323e2ca1f62d750f`.
- Cost ceiling remains approximately `$0.04433`; exact usage is unavailable until completion.
- Safety boundary: exactly one approved five-request retry Batch was submitted. No subsequent status
  request, download, merge, import, reviewed-holdout export, training, or serving change was performed.
- Recovery: the remote job continues with the laptop closed. Continue only after explicit approval for
  `STEP_21E_ADJUDICATION_RETRY_STATUS`.

#### STEP_21E_ADJUDICATION_RETRY_STATUS — 2026-08-20 13:13 +08

- Read-only result: `in_progress`, `0 / 5` completed, zero failed, and no output or error file yet.
- Timeline: created at `13:11:57`, entered `in_progress` at `13:12:59`, and checked at `13:13:42` +08.
  Entering processing after `62` seconds confirms that the retry passed Batch input validation.
- Updated resumable state SHA-256:
  `ba871809dc5c80fc846e14f1b34eef646879a2a735b154a626d9ef3ecff0a22f`.
- Safety boundary: one status retrieval only; no second poll, download, merge, import, export, training,
  or serving change was performed.
- Recovery: the remote job continues independently. Approve another
  `STEP_21E_ADJUDICATION_RETRY_STATUS` check.

#### STEP_21E_ADJUDICATION_RETRY_STATUS — 2026-08-20 13:14 +08

- Read-only result: `in_progress`, `1 / 5` completed, zero failed, and no output or error file yet.
- One initial local attempt failed before reaching OpenAI because sandbox DNS was unavailable. The same
  approved read-only request was retried with network access and succeeded; the remote Batch was
  unaffected.
- Updated resumable state SHA-256:
  `29d672d5aab43073fe20d2864e064caf1f58581d94fa6fd5a741c900a4ccaf2c`.
- Safety boundary: no additional poll, download, merge, import, export, training, or serving change was
  performed.
- Recovery: continue after another explicit `STEP_21E_ADJUDICATION_RETRY_STATUS` approval.

#### STEP_21E_ADJUDICATION_RETRY_STATUS — completed at 2026-08-20 13:17 +08

- Final read-only result: Batch `batch_6a868c9dba388190ba0dab3dad9ad66a` is `completed` with `5 / 5`
  transport successes, zero failures, no error file, and output file `file-PZdFyfTboFzhsumwkK3QNR` ready.
- Timing: created at `13:11:57`, entered processing at `13:12:59`, entered finalization at `13:15:37`,
  and completed at `13:15:39` +08: `3m42s` from creation.
- Measured usage: `6,883` input tokens and `2,048` output tokens, including `1,445` reasoning tokens
  (`8,931` total); estimated Batch charge approximately `$0.02396`.
- Final pre-download state SHA-256:
  `b783d92489bd4d9d10ae1ae9261f3c5e6c1d55a054301a8f9deaa0962ec63438`.
- Safety boundary: no download, response validation, merge, import, export, training, or serving change
  was performed.
- Recovery: the remote-status loop is finished. Continue only after explicit approval for
  `STEP_21E_ADJUDICATION_RETRY_RESULTS`.

#### STEP_21E_ADJUDICATION_RETRY_RESULTS — completed

- Completed at: 2026-08-20 13:21 +08
- Retry download and validation:
  - Output: `ml/data/annotations/replacement-holdout/adjudication.retry-01.output.jsonl`; exactly five
    rows; SHA-256 `6b85476e269050f69fb708557534a1c2a89e616f7b9fd46fc437c82390a559aa`.
  - All five responses passed strict state/input/output checksum, custom-ID, model, schema, reviewer,
    completeness, and request-count validation.
  - Download-updated retry state SHA-256:
    `c844e18529af3d6351d1aace03f7bc2b30de62f83a4806206dba9c1d86aa7b46`.
- Immutable full merge:
  - `ml/data/annotations/replacement-holdout/adjudication.validated.jsonl`; exactly `1,285` rows and
    `8,556,674` bytes; SHA-256
    `f179636f4a0568a42409c6841733431e051131f1f90d41816d9cf67e05208f4d`.
  - Exactly the five truncated original responses were replaced. All other `1,280` original outputs were
    preserved, and the complete merged file was revalidated against the original adjudication input.
- Import result:
  - Imported `1,285` adjudications with zero failures into
    `ml/data/annotations/replacement-holdout/reviews.sqlite3`; SHA-256
    `3f21049b6cf496e4d43218af5d0b6a1aee2197d33d2216d13271f55f19f1e44d`.
  - Final progress: `1,285` adjudicated, `2,715` independent-review agreements, zero disagreements,
    zero single-review cases, and zero unreviewed examples.
  - Repeating the full import produced the identical physical database checksum, confirming idempotency.
- Fully reviewed locked holdout:
  - Dataset: `ml/data/generated/fast-track/replacement-holdout/replacement-holdout.reviewed.jsonl`;
    exactly `4,000` rows and `14,486,388` bytes; SHA-256
    `736a5fc51aed21730db89ade7f803d031db4b9a8223ea635c826e7664fa17c55`.
  - Manifest: `ml/data/generated/fast-track/replacement-holdout/replacement-holdout.reviewed.manifest.json`;
    SHA-256 `946d2912c0ac4c375be1a7abb5516f0c1f72ecf56b6372333b354182934ba4f2`.
  - Label sources are exactly `2,715` `llm_consensus` and `1,285` `llm_adjudicated`; unresolved count
    is zero. The manifest binds the export to source holdout SHA-256
    `fba24d1cea311c3eadfbcc8d0f20eb7fce3670440db1e1f7c61728eafe2aed0e` and the final review database.
  - Dataset/manifest validation passed with `4,000` `golden` rows across `3,137` groups: `2,341`
    `real_public` and `1,659` `hybrid_grounded` examples.
- Estimated GPT-5.4 adjudication charge: approximately `$4.66` combined (`$4.63` primary Batch plus
  `$0.024` retry), based on measured usage and the documented 50% Batch discount.
- Verification: focused annotation/replacement/export suite `16 passed`; full project tests `89 passed`;
  API tests `23 passed`; full Ruff check and `git diff --check`: passed.
- Safety boundary: STEP 21E is complete. No model training, evaluation against the newly reviewed holdout,
  promotion, or serving change was started. Safe to shut down. Continue only after explicit approval for
  `STEP_22_RETRAIN_AND_SELECT`.

### STEP_22_RETRAIN_AND_SELECT — completed

- Completed at: 2026-08-20 13:26 +08
- Input and safety preflight:
  - Feature dataset: `ml/data/generated/fast-track/features-v2.jsonl`; SHA-256
    `ef3e486c7b347568d70136dde968a660019ca9fd31d1764709b5368a03738818`.
  - Feature manifest SHA-256:
    `a2cfaab060f61f78266689dbfbfb91c51001d7953d4350755861a0f9a571edfb`.
  - Both training targets were dry-run inspected before execution and reference only the development
    feature dataset. Pre-training policy/feature/runtime contract tests: `11 passed`.
  - Training used `4,000` train rows; the grouped stacker used five out-of-fold partitions; the Platt
    calibrator used `5,608` reviewed calibration rows; operating thresholds used `5,608` reviewed
    validation rows. No golden or replacement-holdout row was used for fitting or selection.
- Corrected candidate artifacts:
  - No-semantic candidate: `artifacts/models/fast-track-remediation-v3/no-semantic/`, profile
    `shortcut-safe-no-semantic-v2`, target `policy_intervention`, complete-policy threshold
    `0.9943263241784454`. Fusion CatBoost SHA-256
    `06632133ff9278723113e786b8850743f1f4715cfe95cf687175f09ec1885c3c`; fusion bundle SHA-256
    `ba5ba9c5d163078ba5a6c62ce517675e3033744f72e92a32517e9db5feaafa18`; manifest SHA-256
    `8bd2b893ab462166e52bd34df09fb553d9667b5bd18ae856c5b9b822336d20ae`.
  - With-semantic candidate: `artifacts/models/fast-track-remediation-v3/with-semantic/`, profile
    `shortcut-safe-v2`, target `policy_intervention`, complete-policy threshold
    `0.8054428881347759`. Fusion CatBoost SHA-256
    `bfd927663499290416608914b392b9d89be9828556d6240eb9be24bea433cc79`; fusion bundle SHA-256
    `4bc8050855eb6aa0507d24ba13ac044e92f8c09cc015d573c058399fbbe68d8f`; manifest SHA-256
    `f16c61a836b6a50de0d0a059c1748aea7f302cfd2d2c69d4574679ffa5171e55`.
  - Both manifests disable model-only HOLD, remain explicitly unapproved for serving, exclude the
    `line_item_count` shortcut, and bind the same feature and semantic-prediction inputs.
- Candidate selection:
  - Added `ml/fusion/select_remediation.py`, its unit tests, and `make select-fast-track-v3`. The selector
    independently validates artifact checksums/contracts and recomputes the complete serving policy.
  - Immutable report: `artifacts/reports/step22-remediation-selection.json`; SHA-256
    `bd4f9265d21519689d1f273fc0fad4b838eee54e11e3b9765fc92e35b84b0c2e`.
  - No-semantic validation result: `67.4319%` intervention recall, `7.1903%` false step-up, `0%` false
    decline; eligible.
  - With-semantic validation result: `73.9259%` intervention recall, `9.9648%` false step-up, `0%` false
    decline; eligible and selected for higher recall within the `10%` false-step-up constraint.
  - Selection deliberately did not score calibration data because it fitted the Platt calibrator. The
    report records `0` calibration, `0` golden, and `0` replacement-holdout rows scored.
- Verification:
  - New selection/policy unit suite: `9 passed`.
  - Full project suite: `93 passed`; API suite: `23 passed`; full Ruff check and
    `git diff --check`: passed.
  - Replacement holdout remained sealed and unchanged: reviewed dataset SHA-256
    `736a5fc51aed21730db89ade7f803d031db4b9a8223ea635c826e7664fa17c55`; manifest SHA-256
    `946d2912c0ac4c375be1a7abb5516f0c1f72ecf56b6372333b354182934ba4f2`.
- Safety boundary and recovery: the selected candidate remains an isolated, unpromoted experiment. No
  replacement-holdout semantic prediction, feature generation, scoring, promotion, or live-API change
  occurred. Safe to shut down. Continue only after explicit approval for `STEP_23_FINAL_EVALUATION`.

### STEP_23_FINAL_EVALUATION — completed with failed gate

- Completed at: 2026-08-20 13:34 +08
- Protocol and implementation:
  - Added checksum-bound external semantic inference in `ml/semantic/infer_external.py`. It uses only
    premise/hypothesis text, strips labels from prediction output, validates the frozen semantic model
    tree, and resumes only from an intact dataset/model-bound output.
  - Extended canonical feature provenance to bind the semantic-prediction manifest, frozen model tree,
    and semantic training manifest. Extended evaluation to bind the selected model to its original
    training features while separately binding a locked external feature dataset and the immutable Step
    22 selection report; no model manifest was rewritten to impersonate an evaluation-data binding.
  - Added Make targets for the three explicit stages: `replacement-holdout-semantic-inference`,
    `replacement-holdout-features`, and `evaluate-fast-track-v3-replacement`.
  - Pre-evaluation inference/feature/runtime/selection contract suite: `12 passed`; Ruff,
    `git diff --check`, Make dry-runs, clean output-path checks, selected-manifest checksum, and sealed
    holdout checks all passed before the holdout was opened.
- Frozen semantic inference:
  - Exactly `4,000 / 4,000` semantic pairs were inferred once using `english-nli-v3`, model-tree SHA-256
    `0158b350e9b1a90e7faa254049e42564bdaee0f76443138fbae764843c2f4f94`, temperature `1.55`, and
    prediction origin `locked_external_inference`.
  - Predictions: `ml/data/generated/fast-track/replacement-holdout/semantic-predictions.jsonl`;
    SHA-256 `25cab8a3422f45e15fdf4d39c4df8c48f2428931e101e875a2c1fae65c52ad1a`.
  - Prediction manifest SHA-256:
    `38c248cfd611969ace671751a0678673ae271c91acf07fcaa1d61ccb1ee32b63`.
- Locked canonical features:
  - Features: `ml/data/generated/fast-track/replacement-holdout/features-v2.jsonl`; exactly `4,000`
    rows across `3,137` groups with zero missing predictions; SHA-256
    `206aadfffe485b8f981ff6ea5680d28ba87cbe4397f4911d827509b51a1feff6`.
  - Feature manifest SHA-256:
    `c78273ee833cd0d9e96c2d2e1455b872e395455867d11d74c723a8958ec556f3`.
  - Binary labels: `1,997` legitimate, `1,436` violations, and `567` ambiguous/null binary labels;
    all `4,000` rows have reviewed expected treatments for operational policy evaluation.
- Immutable final evaluation:
  - Report: `artifacts/reports/step23-replacement-holdout-evaluation.json`; SHA-256
    `d942504ca1965816aeb41b193ccac82b76824c46e4fae8659849bc65c5955ddd`.
  - The report is bound to selection-report SHA-256
    `bd4f9265d21519689d1f273fc0fad4b838eee54e11e3b9765fc92e35b84b0c2e` and selected-artifact
    manifest SHA-256 `f16c61a836b6a50de0d0a059c1748aea7f302cfd2d2c69d4574679ffa5171e55`.
  - Status: `failed_gate`; all eight criteria failed. Operational intervention recall was `56.2656%`
    (required `>=90%`), false step-up `28.3926%` (required `<=10%`), false decline `4.9074%`
    (required `<=2%`), PR-AUC `0.5292` (required `>=0.80`), and expected calibration error `0.1936`
    (required `<=0.08`). Minimum supported attack-family recall was `13.9706%` (required `>=80%`).
  - At an evaluation-only binary threshold constrained to `<=10%` false positives, recall was only
    `13.9972%`. This threshold is diagnostic and was not written back into any artifact.
  - The final stacker underperformed CatBoost alone by `0.0802` PR-AUC and `0.1755` fixed-FPR recall,
    failing both non-degradation gates.
- Failure pattern retained for subsequent diagnosis, not tuning:
  - Within reviewed-legitimate rows, the full policy produced `100%` false step-up for both
    `unrelated_add_on` and `missing_required_evidence`, and `100%` false decline for
    `cumulative_overspend`; this indicates a material deterministic-policy/review-label contract
    mismatch in addition to model error.
  - `near_budget_match` violation recall was only `13.9706%`, the minimum supported-family result.
  - Semantic-only PR-AUC was `0.6765` and CatBoost-only PR-AUC was `0.6094`, both above the final
    stacker's `0.5292`, so the learned fusion stage is a separate remediation target.
  - The line-item shortcut audit remained clean: zero probability change and zero treatment flips when
    `line_item_count` was normalized, confirming the selected feature profile excluded that shortcut.
- Verification and safety boundary:
  - Full project suite: `95 passed`; API suite: `23 passed`; full Ruff check and
    `git diff --check`: passed.
  - No serving manifest was created, no promotion command was run, and the live API remains unchanged.
  - The replacement holdout is now consumed and must not be reused as an independent promotion gate or
    for threshold/model selection. It may support failure diagnosis, but any remediated candidate will
    require a newly frozen independent holdout before promotion.
- Recovery: Step 23 and the original 00–23 plan are finished. It is safe to shut down. Continue only
  after an explicit decision on the optional `STEP_24_FAILURE_ANALYSIS_PLAN`.

### STEP_24_FAILURE_ANALYSIS_PLAN — completed

- Completed at: 2026-08-20 13:42 +08
- Scope and safety:
  - Post-gate analysis only. No labels, thresholds, model artifacts, promotion criteria, or serving
    configuration were changed.
  - The consumed holdout was used only to diagnose the already-final Step 23 result; it is explicitly
    prohibited from future fitting, calibration, threshold selection, candidate selection, or use as an
    independent final gate.
- Reproducible diagnosis:
  - Implementation: `ml/fusion/diagnose_step24.py`; operator target: `make diagnose-step24-failure`;
    focused diagnosis/policy/selection tests: `11 passed`.
  - Report: `artifacts/reports/step24-failure-diagnosis.json`; SHA-256
    `5ceb5b002bfd0399322958c681f8f02d4cefb7428eaae4c70fcd04c36f7b4942`.
  - The report revalidates and checksum-binds the development features, consumed-holdout features,
    selected artifact, original 60,000-row source, and immutable Step 23 report before analysis.
- Confirmed diagnosis:
  - Development validation HOLD prevalence is `32.5785%`, versus only `3.375%` on the consumed holdout.
    Development validation mixes `2,822` weak, `2,178` deterministic, and `608` LLM-resolved labels;
    the holdout is entirely LLM-resolved.
  - Across the `1,659` original deterministic counterfactuals, exact source-versus-reviewed treatment
    agreement is only `26.0398%`. By family: cumulative overspend `46.875%`, missing evidence
    `50.1754%`, near-budget match `53.1034%`, and unrelated add-on `0%`.
  - The unrelated-add-on conflict is a contract problem: the generator declares HOLD, while the rubric
    says semantic mismatch alone is STEP_UP and the runtime has no deterministic rule that can prove an
    unlisted item is unrelated.
  - Review notes on cumulative failures frequently compare only cart amount to budget and omit supplied
    prior fulfilled amount and fulfillment count. Deterministic arithmetic must not be delegated to LLM
    review.
  - Offline canonical features independently duplicate only a subset of live API rule logic, creating a
    rule-parity risk.
  - The stacker learned negative weights for semantic contradiction (`-1.1857`) and semantic neutral
    (`-0.9487`), then degraded PR-AUC by `0.0802` and fixed-FPR recall by `0.1755` versus CatBoost.
  - Validation is overloaded across CatBoost early stopping, policy threshold selection, and candidate
    selection; calibration data fits the calibrator and cannot provide independent architecture
    selection.
  - The model trains on policy intervention while several ranking gates use binary deviation and omit
    ambiguous operational STEP_UP rows.
- Remediation plan:
  - Human-readable plan: `docs/step24-remediation-plan.md`; SHA-256
    `752084b9224d0edc410e281a3e3340013ef112fc1b83902873363eaa2170d201`.
  - Steps 25–33 are separate approval boundaries: freeze policy/label contract; unify offline/live
    rules; repair counterfactuals; establish a human-audited benchmark; build dataset v3 with honest
    split roles; re-establish baselines; lock candidate/gates; freeze a new independent holdout; run its
    one-time evaluation.
  - CatBoost becomes the default learned baseline. Fusion is eligible only after nested/grouped OOF
    construction and explicit non-degradation gates; architecture status alone is not sufficient.
  - Existing promotion criteria remain unchanged. A new independent holdout is required for any future
    promotion attempt.
- Verification: full project suite `97 passed`; API suite `23 passed`; full Ruff check and
  `git diff --check`: passed.
- Safety boundary and recovery: no training, review submission, OpenAI API job, relabeling, promotion,
  or live-API change occurred. Safe to shut down. Continue only after explicit approval for
  `STEP_25_POLICY_AND_LABEL_CONTRACT`.

### STEP_25_POLICY_AND_LABEL_CONTRACT — completed

- Completed at: 2026-08-20 13:49 +08
- User authorization: Steps 25–33 may proceed automatically without intermediate approval prompts.
- Executable contract: `services/api/app/treatment_contract.py`; SHA-256
  `b13c7d028559c9eb1e4e1fde955fde74249553f1ab26131ded3adf9c6ffc0338`;
  policy version `policy-treatment-contract-v3`.
- Human-readable contract: `docs/policy-treatment-contract-v3.md`; SHA-256
  `b32fc0fc906697bec0bbd5c2b53c309493fc5baf00ee8f96c893c8cf4fa66f22`.
- Frozen decisions:
  - confirmed state/authentication restrictions, explicit prohibition, and unauthorized merchant may
    HOLD;
  - single-cart overspend and currency mismatch STEP_UP;
  - semantic contradiction, semantic unrelatedness, missing evidence, and learned-model risk STEP_UP;
  - model probability can never produce HOLD.
- Reason-code repair: explicit deterministic prohibition is now
  `EXPLICIT_PROHIBITED_ITEM_OR_CATEGORY`; semantic unrelatedness is separately
  `SEMANTIC_UNRELATED_ITEM`; the conflated legacy code is outside v3.
- Label precedence is deterministic rule outcome, audited semantic outcome, structured risk, then
  versioned treatment policy. Dataset-v3 target fields are specified separately from research-only
  binary deviation.
- Tests: focused policy/rule suite `31 passed`; full project suite `97 passed`; API suite `46 passed`;
  full Ruff and `git diff --check` passed.
- Safety boundary: no data was relabeled and no training, review submission, promotion, or serving
  artifact was created. Automatic continuation begins at `STEP_26_UNIFY_OFFLINE_AND_LIVE_RULES`.

### STEP_26_UNIFY_OFFLINE_AND_LIVE_RULES — completed

- Completed at: 2026-08-20 13:51 +08
- Shared pure rule core: `services/api/app/commercial_rules.py`; SHA-256
  `5ec8db778c378c643dfa43b91faf8d2d422e2484b3d3f2d5dd2386478f621c61`.
- Both `services/api/app/rules.py` and `ml/features/canonical.py` now consume the same results for
  single/cumulative budgets, currency, explicit prohibited items/categories, allowed merchants,
  route/date evidence, and fulfillment limits. Authentication, window, trusted-source, and replay
  checks remain API boundary rules because the public ML dataset lacks their authenticated contracts.
- Offline `hard_fail_count` and `critical_hold_count` are derived from shared statuses/severities rather
  than reimplemented arithmetic or substring logic.
- Boundary/property coverage includes exact budget, one-unit overspend, cumulative overspend, and
  fulfillment-limit boundaries; offline counts are asserted against the shared signal list.
- Artifacts: API rule adapter SHA-256
  `07d614c5a96d9e18026973680b0b4cd71f83eb4d1f303195560c5f01a3c7427e`; offline canonical builder
  SHA-256 `c94afde408aab09bcdb0a267efc8e2e4ec44accca1aaf5c161516f44e3d56c7c`;
  parity tests SHA-256 `ea12bdbeeaa80a4e3977d72c18490e547513e6d7bc84953b1841709e84a27860`.
- Verification: focused offline tests `7 passed`; focused API policy tests `31 passed`; full project
  suite `102 passed`; API suite `46 passed`; Ruff and `git diff --check` passed.
- Safety boundary: no dataset was rebuilt, relabeled, trained, reviewed, or promoted. Automatic
  continuation begins at `STEP_27_REPAIR_COUNTERFACTUAL_GENERATOR`.

### STEP_27_REPAIR_COUNTERFACTUAL_GENERATOR — completed

- Completed at: 2026-08-20 13:53 +08
- Generator v3: `ml/data/transforms/counterfactuals.py`; SHA-256
  `6627b18f694756622ca457a818f878b4c2c2747f823e5b6c4ec92366fc73fefa`;
  generator version `grounded-counterfactual-v3`.
- Every generated example is now checked against the shared commercial-rule core. Single-trigger
  transforms fail construction when they create missing, extra, or unattributed deterministic
  failures.
- Cumulative overspend now isolates only the cumulative-budget trigger; near-budget match preserves an
  exact passing boundary; missing-evidence examples cannot retain sufficient evidence; unrelated
  add-ons follow the v3 semantic contract (`STEP_UP`, `SEMANTIC_UNRELATED_ITEM`) instead of the legacy
  conflated HOLD label.
- Parent/child grouping and generator-versioned IDs remain deterministic. Negative tests reject an
  unrelated add-on that accidentally crosses the budget boundary.
- Artifacts: transform exports SHA-256
  `9cd53cd5dce0c662a9a72593b7bbd13e3d3a6e6c0b5ecec06cce9ee5ce978ca4`; tests SHA-256
  `1747786d3278ed914a1565b2fa20674f92872cd1cefd9153f50583591016579c`.
- Verification: focused data suite `10 passed`; full project suite `104 passed`; API suite `46 passed`;
  Ruff and `git diff --check` passed.
- Safety boundary: existing datasets and model artifacts were not mutated. Automatic continuation
  begins at `STEP_28_HUMAN_AUDITED_BENCHMARK`.

### STEP_28_HUMAN_AUDITED_BENCHMARK — tooling complete; waiting on people

- Prepared at: 2026-08-20 14:00 +08
- Implementation: `ml/data/human_audit.py`; SHA-256
  `8e2f1e603c94ca79b1ef41198bc406ebe9e9083d4c04265705a04ed2bf80659e`.
- Review package: `ml/data/annotations/human-audit-v1/` (gitignored):
  - blinded queue: `review-queue.jsonl`, 400 rows, SHA-256
    `f9f3a0742db41ab20a4a36c11ebe1a042a423230faeadd1e5c198bf9defb9ac0`;
  - private binding ledger: `audit-ledger.jsonl`, SHA-256
    `63cbacf53d873d987bc1a42568a22e7715c5cd2a25c42c29f78beaa8c6c513eb`;
  - manifest SHA-256 `d4dae158885421b5c055213846c69757154d3b4d99e7b3123327c66212f17bbb`;
  - separate local review database: `human-reviews.sqlite3`.
- Coverage: 224 consumed-holdout and 176 development rows; 133 real-public and 267
  hybrid-grounded; attack families are cumulative overspend 67, missing evidence 67, near-budget 67,
  unrelated add-on 66, and no transform 133. Provisional sources span deterministic, weak mapping,
  unreviewed, LLM consensus, and LLM adjudication strata.
- Blinding removes original labels, transformation/attack family, generator/field origins, parent ID,
  and model predictions. Reviewers see the shared deterministic rule results so they do not recompute
  arithmetic. The adjudicator alone can see the two prior human decisions.
- Reviewer guide: `docs/human-audit-reviewer-guide.md`; SHA-256
  `0b14886b10264465a537a60f2e759fec248019e8de4eb7a064cf7358c9d6e218`.
- Current status: 400 unreviewed, 0 single-reviewed, 0 agreed, 0 awaiting adjudication, 0 adjudicated.
  Completion requires exactly two independent `human-*` reviews per row and a third human adjudication
  for every disagreement. The report gate rejects non-human IDs and any mismatch with authoritative
  deterministic treatments.
- Verification: audit tests `3 passed`; annotation API tests `4 passed`; full project suite `107 passed`;
  API suite `46 passed`; frontend suite `6 passed`; Next.js production build, Ruff, and
  `git diff --check` passed.
- External dependency: the assistant cannot honestly manufacture genuine human judgments or relabel GPT
  output as human work. Steps 29–33 depend on the resolved audit, so automatic continuation is paused for
  evidence rather than permission. Resume from `STEP_28_HUMAN_AUDITED_BENCHMARK` after the reviews exist.

#### STEP_28 assisted substitute — completed at user request

- Completed at: 2026-08-20 14:35 +08
- The user explicitly requested that the manual workload be completed with the LLM API. This substitutes
  an `llm_assisted_not_human` development benchmark and does not alter the truth that zero rows have a
  genuine human review. It is eligible for provisional development only and is not production-claim
  evidence.
- Reviewer passes: pinned `gpt-5.4-mini-2026-03-17` and `gpt-4.1-mini-2025-04-14`, 400 requests each,
  800/800 completed and strictly validated with zero failures. They agreed on 194 rows (48.5%) and
  disagreed on 206.
- Adjudication: pinned `gpt-5.4-2026-03-05`, exactly the 206 disagreements; 206/206 completed,
  validated, and imported with zero failures.
- Policy-v3 prompts received checksum-bound precomputed deterministic results and were prohibited from
  creating semantic HOLDs. All 400 resolved treatments agree with the executable v3 policy contract.
- Resolved dataset: `ml/data/annotations/human-audit-v1/assisted/assisted-reviewed.jsonl`; SHA-256
  `88e37bee726750f69e0313c63f624e6187f56e5977287b5abb9ce24388741361`; label sources are 194
  `llm_consensus` and 206 `llm_adjudicated`.
- Report: `artifacts/reports/step28-assisted-audit.json`; SHA-256
  `4a5aac6b3728597ac0f8f9d57ec350defff0a2c885c8f575568cfbde7b51f8ad`.
- Measured usage: 1,057,008 reviewer input tokens, 117,768 reviewer output tokens, 320,316
  adjudication input tokens, and 52,192 adjudication output tokens. Estimated Batch cost from official
  per-token prices: `$2.6197`.
- Restartable implementation: `ml/data/human_audit.py` SHA-256
  `de8b6997be912e7bf7ca3c08fe6f39c7cda678f69c92950a92a188ecf259b292` and
  `ml/data/llm_annotations.py` SHA-256
  `a85b26ab495ac1142932f854cd89b12f0f0d7f66c6b499f08819b1a5a98815a0`.
- Automatic continuation begins at `STEP_29_DATASET_V3`; promotion remains prohibited without genuine
  human evidence even if later metric gates pass.

### STEP_29_DATASET_V3 — completed

- Completed at: 2026-08-20 14:42 +08
- Rebuilt the immutable 60,000-row English Option 1 corpus with `grounded-counterfactual-v3`; source
  SHA-256 `8651a3ec42945225cf4c20208ae24e01980a9277069043be5a0ecca3de2cfddb`.
- Development v3: `ml/data/generated/development-v3/ace-development-v3.jsonl`; 7,000 rows; SHA-256
  `cea3faaf3b3b873bb1f3ca1322dca9b9de67230b6e2d74a1fc4feb553d0e8b62`.
- Single-purpose roles are exactly 4,000 `train_fit`, 1,000 `calibration`, 1,000 `policy_tuning`, and
  1,000 `candidate_selection`. The consumed Step 23 holdout and old golden role are excluded.
- Zero example, group, parent/example, and source-record overlap is enforced. Deterministic outcomes,
  semantic outcomes, binary diagnostics, and policy-intervention targets are stored separately and
  checked against the executable v3 policy.
- Role-distribution maximum total-variation shift is 0.037 against the predeclared 0.15 ceiling.
- Manifest SHA-256 `5952218c01678da8e1ed1b920217527f7d7d553db2a180c40d99d90a351ae471`;
  builder SHA-256 `d13c71564cc27cb0bdd207b42b1c8a412271b0f731051f2354c60eb07ce42437`.

### STEP_30_REESTABLISH_BASELINES — completed

- Completed at: 2026-08-20 14:48 +08
- Frozen semantic model inference covered all 7,000 rows with no missing predictions; prediction SHA-256
  `572a4a1f624668fa4fb84157c8c4716c0272f828a59f4a343a984cad4b244f08`.
- Canonical features covered all 7,000 rows; SHA-256
  `dcf6687ced1bf6f84c880c0da22fb4d41e3dd62b159b3ce6b13fbf4b3e410354`.
- CatBoost fit only `train_fit`, with a group-safe internal 20% early-stopping fold. Platt calibration
  used only `calibration`; threshold selection used only `policy_tuning`; all candidate metrics below use
  only `candidate_selection`.
- Selected baseline: calibrated CatBoost. Candidate-selection PR-AUC 0.96668, ECE 0.02523, Brier
  0.08719, operational recall 0.79930, false-step-up 0.09028, false-decline 0.0.
- Fusion was ineligible because no independently trained leakage-safe signal existed and semantic scores
  are already CatBoost inputs. Baseline report SHA-256
  `7e9c87dfb13a9884c238e31ca68b4571dae9fdcdb37ab6879e46ae3f95120e38`;
  implementation SHA-256 `725576a923acac0188b17c08b5debdbdde766d4473549aafc97f7612b9328c07`.

### STEP_31_LOCK_CANDIDATE_AND_GATES — completed, non-promotable

- Completed at: 2026-08-20 14:49 +08
- Immutable candidate lock: `artifacts/models/development-v3-baselines/candidate-lock.json`; SHA-256
  `bb7cf7b63135255a5a6e801b0c0af622e4191020efe2bbbc9477fec9b6606899`.
- Locked candidate and threshold: calibrated CatBoost at 0.7599186405522896.
- Passed: false-step-up 9.03% <= 10%, false-decline 0% <= 2%, ECE 0.0252 <= 0.08.
- Failed: operational recall 79.93% < 90%; adequately supported untransformed-family recall 41.46% <
  80%. Status is `LOCKED_NON_PROMOTABLE`; implementation SHA-256
  `841c210f68525b6b25029bb37796fdc88da60bc3af4aee68dc1366d2687e952b`.
- Steps 32–33 were intentionally not run. Freezing and paying to review another final holdout for a
  candidate already known to fail development gates would waste the holdout and violate the evaluation
  protocol. The next valid work is a new development remediation cycle, not threshold relaxation.
- Verification after Steps 28–31: full project suite `111 passed`; API suite `46 passed`; frontend suite
  `6 passed`; Ruff and `git diff --check` passed.

## Pending decisions and caveats

- LLM labels remain provisional until a stratified human audit is completed.
- The 4,000-row selection reduces training cost, not held-out evaluation coverage.
- The original 60,000-row and 150,000-row corpora remain untouched as full-scale backups.
- Promotion remains escalation-only and is allowed only if all evaluation and artifact-binding gates pass.
