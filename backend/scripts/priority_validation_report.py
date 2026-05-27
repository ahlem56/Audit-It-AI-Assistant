from __future__ import annotations

import argparse
import csv
import json
import sys
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


def _rows_from_report(audit_input: StructuredAuditInput) -> list[dict[str, str]]:
    _disable_paid_reasoning()
    report = composer.compose_audit_report(audit_input)

    rows: list[dict[str, str]] = []
    for finding in report.detailed_findings:
        rows.append(
            {
                "observation_id": finding.observation_id,
                "application": finding.application,
                "original_reference": finding.original_reference,
                "resolved_reference": finding.reference,
                "reference_resolution": finding.resolved_reference_reason,
                "final_priority": finding.priority,
                "priority_mode": finding.priority_decision_mode,
                "recommendation_mode": finding.recommendation_decision_mode,
                "why_escalated": finding.escalation_reason,
            }
        )
    return rows


def _print_table(rows: list[dict[str, str]]) -> None:
    headers = [
        "observation_id",
        "original_reference",
        "resolved_reference",
        "final_priority",
        "priority_mode",
        "why_escalated",
    ]
    widths = {header: len(header) for header in headers}
    for row in rows:
        for header in headers:
            widths[header] = min(max(widths[header], len(str(row[header]))), 80)

    def fmt(value: str, width: int) -> str:
        text = str(value)
        if len(text) <= width:
            return text.ljust(width)
        return (text[: width - 3] + "...") if width > 3 else text[:width]

    header_line = " | ".join(fmt(header, widths[header]) for header in headers)
    divider = "-+-".join("-" * widths[header] for header in headers)
    print(header_line)
    print(divider)
    for row in rows:
        print(" | ".join(fmt(row[header], widths[header]) for header in headers))


def _write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a no-cost priority validation report.")
    parser.add_argument("audit_input", help="Path to audit_input.json")
    parser.add_argument("--csv", dest="csv_path", help="Optional CSV output path")
    args = parser.parse_args()

    audit_input = _load_audit_input(Path(args.audit_input))
    rows = _rows_from_report(audit_input)

    print(f"Validation report generated for {len(rows)} reportable observations.")
    _print_table(rows)

    if args.csv_path:
        output_path = Path(args.csv_path)
        _write_csv(rows, output_path)
        print(f"\nCSV written to {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
