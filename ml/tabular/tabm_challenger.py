from __future__ import annotations

import argparse
import json
from pathlib import Path


def inclusion_gate(
    core_metrics: dict[str, float],
    challenger_metrics: dict[str, float],
    *,
    core_p95_ms: float,
    challenger_p95_ms: float,
    latency_budget_ms: float = 2000,
) -> dict[str, object]:
    improved = (
        challenger_metrics.get("violation_recall", 0) > core_metrics.get("violation_recall", 0)
        or challenger_metrics.get("pr_auc", 0) > core_metrics.get("pr_auc", 0)
    )
    calibration_ok = challenger_metrics.get("expected_calibration_error", 1) <= (
        core_metrics.get("expected_calibration_error", 1) + 0.01
    )
    latency_ok = challenger_p95_ms <= latency_budget_ms
    return {
        "include_online": improved and calibration_ok and latency_ok,
        "improved_primary_metric": improved,
        "calibration_ok": calibration_ok,
        "latency_ok": latency_ok,
        "core_p95_ms": core_p95_ms,
        "challenger_p95_ms": challenger_p95_ms,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate official-package TabM results against the online inclusion gate."
    )
    parser.add_argument("--core-report", type=Path, required=True)
    parser.add_argument("--challenger-report", type=Path, required=True)
    args = parser.parse_args()
    core = json.loads(args.core_report.read_text())
    challenger = json.loads(args.challenger_report.read_text())
    result = inclusion_gate(
        core["metrics"],
        challenger["metrics"],
        core_p95_ms=core["latency_ms"]["p95"],
        challenger_p95_ms=challenger["latency_ms"]["p95"],
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

