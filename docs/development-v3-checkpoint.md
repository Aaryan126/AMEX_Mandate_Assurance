# Development v3 checkpoint

Checkpoint date: 2026-08-20 (Asia/Singapore)

This checkpoint preserves the locked development-v3 system before missed-intervention
remediation begins. Development-v3 artifacts are diagnostic/regression inputs only and
must never be overwritten or reopened for model selection.

## Source state

- Branch: `main`
- Parent commit: `38cb01c73370961c374b7bc32bb5ac1aaff22d5e`
- The checkpoint commit includes all non-ignored project work present after secret and
  ignore checks. Local secrets, raw/generated datasets, annotations, models, and reports
  remain excluded by `.gitignore`.

## Recovery archive

- Local path: `artifacts/models/checkpoints/development-v3-locked-20260820.tar.gz`
- Size: 624 MB
- SHA-256: `ac5fbc45aa95e5db55fbb19c6638284244b9afffbb314604d92e8d49beccaf8d`
- Contents: the semantic-fast-track model, development-v3 dataset and features,
  development-v3 CatBoost/calibrator/policy artifacts, evaluation reports, and the
  relevant assisted-review records.
- The archive was successfully read back with `tar -tzf` after creation.

## Locked artifact hashes

| Artifact | SHA-256 |
|---|---|
| `ace-development-v3.jsonl` | `cea3faaf3b3b873bb1f3ca1322dca9b9de67230b6e2d74a1fc4feb553d0e8b62` |
| development-v3 `manifest.json` | `5952218c01678da8e1ed1b920217527f7d7d553db2a180c40d99d90a351ae471` |
| `features-v2.jsonl` | `dcf6687ced1bf6f84c880c0da22fb4d41e3dd62b159b3ce6b13fbf4b3e410354` |
| `features-v2.manifest.json` | `afbcac09a659583b8bf6f73d135d16e0868ea4f4fdf77e2f4e092223852c0fa7` |
| `semantic-predictions.jsonl` | `572a4a1f624668fa4fb84157c8c4716c0272f828a59f4a343a984cad4b244f08` |
| `semantic-predictions.manifest.json` | `ae039f2201156f79221244e876a0d0efca745340099791364819838770d0fd56` |
| `catboost-v1.cbm` | `3c79a6a282db6c8ffa401bdb8df1aed96c860fdbcedaa00612db821f184107a9` |
| CatBoost manifest | `984a70cfb1a456be8e00916ed96d52143c8c51387538472643c15fdc7cacfc22` |
| baseline report | `7e9c87dfb13a9884c238e31ca68b4571dae9fdcdb37ab6879e46ae3f95120e38` |
| candidate lock | `bb7cf7b63135255a5a6e801b0c0af622e4191020efe2bbbc9477fec9b6606899` |
| Platt calibrator | `9d81a6be64917ffee8d9621b631fe2cad09e11175726d9826faaa40a31fcc1fa` |

## Baseline verification

- API unit/component tests: 46 passed.
- ML/data unit/component tests: 111 passed.
- Web component tests: 6 passed.
- Next.js production build: passed.
- A combined API+ML pytest invocation is intentionally not used because both suites
  expose a top-level Python package named `tests`; the Makefile runs them in separate
  interpreter processes.

