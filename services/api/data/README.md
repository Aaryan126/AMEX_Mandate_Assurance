# Development-v3 presentation summary

`development-v3-evaluation-summary.json` is the small, tracked API projection of the locked development-v3
candidate evidence. It is intentionally separate from generated evaluation reports so a local or Docker demo
cannot silently fall back to the obsolete synthetic smoke-test report.

The values are copied from the checksum-bound local artifacts recorded in
`docs/development-v3-checkpoint.md`:

- candidate metrics and family slices: `artifacts/models/development-v3-baselines/baseline-report.json`;
- status and gate decision: `artifacts/models/development-v3-baselines/candidate-lock.json`.

This file is presentation evidence, not a serving manifest. The candidate remains
`LOCKED_NON_PROMOTABLE`, and the live prototype continues to use its deterministic fallback.
