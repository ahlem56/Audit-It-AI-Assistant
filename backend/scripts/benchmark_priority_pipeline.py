from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.models.audit_input import StructuredAuditInput
import app.services.report_composer_service as composer


def _disable_paid_reasoning() -> None:
    composer.infer_observation_reasoning = lambda observations: {}
    composer.infer_priority_reasoning = lambda observations: {}


def _load_audit_input(path: Path) -> StructuredAuditInput:
    return StructuredAuditInput.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _snapshot(report) -> dict:
    return {
        "priority_counts": {item.priority: item.count for item in report.priority_summary},
        "rows": [
            {
                "observation_id": finding.observation_id,
                "original_reference": finding.original_reference,
                "resolved_reference": finding.reference,
                "priority": finding.priority,
                "priority_mode": finding.priority_decision_mode,
                "recommendation_mode": finding.recommendation_decision_mode,
            }
            for finding in report.detailed_findings
        ],
    }


def _compare_snapshots(current: dict, baseline: dict) -> list[str]:
    issues: list[str] = []
    if current.get("priority_counts") != baseline.get("priority_counts"):
        issues.append(
            f"Priority counts changed: current={current.get('priority_counts')} baseline={baseline.get('priority_counts')}"
        )

    baseline_rows = {
        row["observation_id"]: row
        for row in baseline.get("rows", [])
    }
    for row in current.get("rows", []):
        previous = baseline_rows.get(row["observation_id"])
        if not previous:
            issues.append(f"New observation in snapshot: {row['observation_id']}")
            continue
        for field in ("resolved_reference", "priority", "priority_mode", "recommendation_mode"):
            if row.get(field) != previous.get(field):
                issues.append(
                    f"{row['observation_id']} changed {field}: current={row.get(field)} baseline={previous.get(field)}"
                )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local no-cost benchmark for the priority pipeline.")
    parser.add_argument("audit_input", help="Path to audit_input.json")
    parser.add_argument("--iterations", type=int, default=5, help="Number of benchmark iterations")
    parser.add_argument("--write-baseline", dest="write_baseline", help="Optional path to save current snapshot JSON")
    parser.add_argument("--compare-baseline", dest="compare_baseline", help="Optional path to compare against snapshot JSON")
    args = parser.parse_args()

    _disable_paid_reasoning()
    audit_input = _load_audit_input(Path(args.audit_input))

    durations_ms: list[float] = []
    latest_report = None
    for _ in range(max(args.iterations, 1)):
        started = time.perf_counter()
        latest_report = composer.compose_audit_report(audit_input)
        durations_ms.append((time.perf_counter() - started) * 1000)

    snapshot = _snapshot(latest_report)

    print(f"Iterations: {len(durations_ms)}")
    print(f"Average: {statistics.mean(durations_ms):.2f} ms")
    print(f"Median: {statistics.median(durations_ms):.2f} ms")
    print(f"Min/Max: {min(durations_ms):.2f} / {max(durations_ms):.2f} ms")
    print(f"Priority counts: {snapshot['priority_counts']}")

    if args.write_baseline:
        baseline_path = Path(args.write_baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Baseline written to {baseline_path}")

    if args.compare_baseline:
        baseline = json.loads(Path(args.compare_baseline).read_text(encoding="utf-8"))
        issues = _compare_snapshots(snapshot, baseline)
        if issues:
            print("Regression signals detected:")
            for issue in issues:
                print(f"- {issue}")
            return 1
        print("No regression detected against the baseline snapshot.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
