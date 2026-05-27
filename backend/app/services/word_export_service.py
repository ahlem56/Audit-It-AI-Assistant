from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate

from app.models.export_models import ExportReportRequest


WORD_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "data" / "rapport_template_dynamic.docx"

WORD_SECTIONS = [
    "Préambule",
    "Modalité et intervenants",
    "Objectifs et approche",
    "Périmètre d'intervention",
    "Synthèse générale",
    "Points relevés",
    "Plan d'action et recommandations détaillées",
    "Annexes",
    "Conclusion",
]


def _safe(value: object) -> str:
    return "" if value is None else str(value)


def _display_priority(priority: str) -> str:
    return {
        "Critical": "Critique",
        "High": "Élevée",
        "Medium": "Moyenne",
        "Low": "Faible",
    }.get(priority, priority or "")


def _extract_report_year(data) -> str:
    title = _safe(getattr(data, "cover_title", ""))
    match = re.search(r"FY\s*([0-9]{2,4})", title, flags=re.IGNORECASE)
    if match:
        year = match.group(1)
        return f"20{year}" if len(year) == 2 else year

    report_date = _safe(getattr(data, "report_date", ""))
    digits = "".join(char for char in report_date if char.isdigit())
    if len(digits) >= 4:
        return digits[-4:]

    period = _safe(getattr(data, "report_period", ""))
    tokens = [token for token in re.split(r"\D+", period) if len(token) == 4]
    return tokens[-1] if tokens else ""


def _stakeholder_item(value: object) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            "name": _safe(value.get("name") or value.get("interlocuteur") or value.get("label")),
            "role": _safe(value.get("role") or value.get("fonction") or value.get("function")),
        }

    text = _safe(value).strip()
    role_match = re.match(r"^(?P<name>.+?)\s*\((?P<role>[^)]+)\)\s*$", text)
    if role_match:
        return {"name": role_match.group("name").strip(), "role": role_match.group("role").strip()}
    if " - " in text:
        name, role = text.split(" - ", 1)
        return {"name": name.strip(), "role": role.strip()}
    if ":" in text:
        name, role = text.split(":", 1)
        return {"name": name.strip(), "role": role.strip()}
    return {"name": text, "role": ""}


def _stakeholder_items(values: list[object]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for value in values:
        if isinstance(value, dict):
            items.append(_stakeholder_item(value))
            continue

        text = _safe(value).strip()
        split_text = re.sub(r"\)\s+(?=[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ' -]+\s+\()", ")|", text)
        for part in [chunk.strip() for chunk in split_text.split("|") if chunk.strip()]:
            items.append(_stakeholder_item(part))
    return items


def _priority_summary_item(item) -> dict[str, Any]:
    percentage = getattr(item, "percentage", 0)
    try:
        percentage_value: int | float = round(float(percentage), 1)
    except (TypeError, ValueError):
        percentage_value = 0

    return {
        "priority": _safe(getattr(item, "priority", "")),
        "priority_label": _display_priority(_safe(getattr(item, "priority", ""))),
        "count": getattr(item, "count", 0),
        "percentage": percentage_value,
    }


def _priority_count(summary: list[dict[str, Any]], priority: str) -> int:
    for item in summary:
        if item.get("priority") == priority:
            try:
                return int(item.get("count") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _finding_item(finding) -> dict[str, Any]:
    priority = _safe(getattr(finding, "priority", ""))
    recommendation_steps = getattr(finding, "recommendation_steps", []) or []
    action_text = _safe(getattr(finding, "recommendation", ""))
    if recommendation_steps:
        action_text = action_text + "\n" + "\n".join(f"- {step}" for step in recommendation_steps)

    return {
        "observation_id": _safe(getattr(finding, "observation_id", "")),
        "reference": _safe(getattr(finding, "reference", "")),
        "domain": _safe(getattr(finding, "domain", "")),
        "category": _safe(getattr(finding, "category", "")),
        "application": _safe(getattr(finding, "application", "")),
        "layer": _safe(getattr(finding, "layer", "")),
        "owners": _safe(getattr(finding, "owners", "")),
        "title": _safe(getattr(finding, "title", "")),
        "expected_control": _safe(getattr(finding, "expected_control", "")),
        "finding": _safe(getattr(finding, "finding", "")),
        "risk_impact": _safe(getattr(finding, "risk_impact", "")),
        "risk_scenario": _safe(getattr(finding, "risk_scenario", "")),
        "impact_detail": _safe(getattr(finding, "impact_detail", "")),
        "business_impact": _safe(getattr(finding, "business_impact", "")),
        "control_impact": _safe(getattr(finding, "control_impact", "")),
        "compliance_impact": _safe(getattr(finding, "compliance_impact", "")),
        "root_cause": _safe(getattr(finding, "root_cause", "")),
        "aggravating_factors": list(getattr(finding, "aggravating_factors", []) or []),
        "immediate_action": _safe(getattr(finding, "immediate_action", "")),
        "structural_action": _safe(getattr(finding, "structural_action", "")),
        "owner": _safe(getattr(finding, "owner", "")),
        "evidence_expected": _safe(getattr(finding, "evidence_expected", "")),
        "follow_up_mechanism": _safe(getattr(finding, "follow_up_mechanism", "")),
        "recommendation": action_text,
        "auditor_comment": _safe(getattr(finding, "auditor_comment", "")),
        "management_summary": _safe(getattr(finding, "management_summary", "")),
        "priority": priority,
        "priority_label": _display_priority(priority),
    }


def _application_detail_item(application) -> dict[str, str]:
    return {
        "name": _safe(getattr(application, "name", "")),
        "description": _safe(getattr(application, "description", "")),
        "operating_system": _safe(getattr(application, "operating_system", "")),
        "database": _safe(getattr(application, "database", "")),
        "provider": _safe(getattr(application, "provider", "")),
    }


def _word_context(result: ExportReportRequest) -> dict[str, Any]:
    data = result.structured_output
    report_year = _extract_report_year(data)
    previous_year = str(int(report_year) - 1) if report_year.isdigit() else ""
    priority_summary = [_priority_summary_item(item) for item in (data.priority_summary or [])]
    findings = [_finding_item(item) for item in (data.detailed_findings or [])]
    recommendations = [_finding_item(item) for item in (data.detailed_recommendations or [])]
    applications = list(data.applications or [])
    application_details = [_application_detail_item(item) for item in (data.application_details or [])]
    if not application_details:
        application_details = [
            {
                "name": _safe(application),
                "description": "",
                "operating_system": "",
                "database": "",
                "provider": "",
            }
            for application in applications
        ]
    maturity_level = _safe(getattr(data, "maturity_level", "")) or "À confirmer"

    return {
        "client_name": _safe(data.client_name) or "Client",
        "report_year": report_year,
        "prior_fiscal_year": f"FY{previous_year[-2:]}" if previous_year else "",
        "report_period": _safe(data.report_period),
        "report_date": _safe(data.report_date),
        "cover_title": _safe(data.cover_title),
        "cover_subtitle": _safe(data.cover_subtitle),
        "confidentiality_notice": _safe(data.confidentiality_notice) or "Strictement privé et confidentiel",
        "word_sections": WORD_SECTIONS,
        "table_of_contents": list(data.table_of_contents or WORD_SECTIONS),
        "preamble": _safe(data.preamble),
        "modality": _safe(data.scope_summary),
        "objectives": list(data.objectives or []),
        "audit_approach": list(data.audit_approach or []),
        "scope_summary": _safe(data.scope_summary),
        "applications": applications,
        "application_details": application_details,
        "stakeholders": _stakeholder_items(list(data.stakeholders or [])),
        "priority_summary": priority_summary,
        "metrics": {
            "total_findings": len(findings),
            "critical_count": _priority_count(priority_summary, "Critical"),
            "high_count": _priority_count(priority_summary, "High"),
            "applications_count": len(application_details) or len(applications),
            "maturity_level": maturity_level,
            "maturity_assessment": _safe(getattr(data, "maturity_assessment", "")) or "Appréciation issue de la synthèse des constats.",
        },
        "general_synthesis": _safe(data.general_synthesis) or _safe(data.executive_summary),
        "executive_highlights": list(getattr(data, "executive_highlights", []) or []),
        "watch_points": list(data.watch_points or []),
        "detailed_findings": findings,
        "detailed_recommendations": recommendations,
        "appendices": list(data.appendices or []),
        "conclusion": _safe(data.conclusion),
    }


def build_report_docx(result: ExportReportRequest) -> BytesIO:
    if not WORD_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Word template not found: {WORD_TEMPLATE_PATH}")

    document = DocxTemplate(str(WORD_TEMPLATE_PATH))
    document.render(_word_context(result))

    output = BytesIO()
    document.save(output)
    output.seek(0)
    return output
