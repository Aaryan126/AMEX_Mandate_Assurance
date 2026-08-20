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
| Stage A: targeted data/feature/policy repair | in progress | Implementation started. |
| Stage B: semantic remediation | conditional | Runs only if Stage A fails its locked gate. |
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

