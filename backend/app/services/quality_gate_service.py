from __future__ import annotations

import re
from collections import Counter, defaultdict

from app.models.audit_input import StructuredAuditInput
from app.models.report_sections import (
    AuditReportOutput,
    QualityGateIssue,
    ReportQualityGateResult,
)

_JUSTIFICATION_EVIDENCE_RE = re.compile(
    r"\b(\d+|evidence|preuve|fact|factuel|constat|expose|risque|impact)\b",
    re.IGNORECASE,
)


def _norm(value: str) -> str:
    return " ".join((value or "").split()).strip().lower()


def _looks_short(value: str, minimum: int) -> bool:
    return len(_norm(value)) < minimum


def _has_sufficient_priority_justification(value: str) -> bool:
    cleaned = _norm(value)
    return len(cleaned) >= 40 and bool(_JUSTIFICATION_EVIDENCE_RE.search(cleaned))


def _token_overlap_ratio(left: str, right: str) -> float:
    left_tokens = {token for token in re.findall(r"\w{5,}", _norm(left))}
    right_tokens = {token for token in re.findall(r"\w{5,}", _norm(right))}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(1, len(left_tokens))


def _has_recommendation_auditability(value: str) -> bool:
    text = _norm(value)
    has_evidence = any(marker in text for marker in ("preuve", "journal", "trace", "validation", "resultat", "rapport", "tableau de bord", "log"))
    has_follow_up = any(marker in text for marker in ("suivi", "periodique", "mensuel", "trimestriel", "revue", "indicateur", "exception", "delai", "echeance"))
    return has_evidence and has_follow_up


def _issue(
    *,
    rule_id: str,
    severity: str,
    title: str,
    message: str,
    recommendation: str,
    affected_observation_ids: list[str] | None = None,
    affected_applications: list[str] | None = None,
    affected_section: str = "",
    score_impact: int,
) -> QualityGateIssue:
    return QualityGateIssue(
        rule_id=rule_id,
        severity=severity,  # type: ignore[arg-type]
        title=title,
        message=message,
        recommendation=recommendation,
        affected_observation_ids=affected_observation_ids or [],
        affected_applications=affected_applications or [],
        affected_section=affected_section,
        score_impact=score_impact,
    )


def evaluate_report_quality_gate(
    audit_input: StructuredAuditInput,
    report_output: AuditReportOutput,
) -> ReportQualityGateResult:
    issues: list[QualityGateIssue] = []
    observations_by_id = {
        (observation.observation_id or "").strip(): observation for observation in audit_input.observations
    }
    findings = list(report_output.detailed_findings or [])

    for finding in findings:
        if not _norm(finding.recommendation):
            issues.append(
                _issue(
                    rule_id="finding_missing_recommendation",
                    severity="blocking",
                    title="Finding without recommendation",
                    message=f"Finding {finding.observation_id or finding.reference} does not contain a recommendation.",
                    recommendation="Add a specific remediation recommendation before export.",
                    affected_observation_ids=[finding.observation_id],
                    affected_applications=[finding.application] if finding.application else [],
                    affected_section="findings",
                    score_impact=12,
                )
            )

        if not _has_sufficient_priority_justification(finding.priority_justification):
            issues.append(
                _issue(
                    rule_id="finding_missing_priority_justification",
                    severity="blocking",
                    title="Finding without sufficient priority justification",
                    message=f"Finding {finding.observation_id or finding.reference} has a weak or empty priority justification.",
                    recommendation="Provide a factual priority justification with evidence, impact, or quantified exposure.",
                    affected_observation_ids=[finding.observation_id],
                    affected_applications=[finding.application] if finding.application else [],
                    affected_section="findings",
                    score_impact=10,
                )
            )

        if _norm(finding.priority) in {"critical", "high"}:
            if _token_overlap_ratio(finding.risk_impact, finding.finding) > 0.55:
                issues.append(
                    _issue(
                        rule_id="finding_risk_restates_constat",
                        severity="warning",
                        title="Risk analysis restates the finding",
                        message=f"Finding {finding.observation_id or finding.reference} risk wording appears too close to the factual observation.",
                        recommendation="Rewrite the risk as a scenario with business/control impact rather than repeating the finding.",
                        affected_observation_ids=[finding.observation_id],
                        affected_applications=[finding.application] if finding.application else [],
                        affected_section="findings",
                        score_impact=5,
                    )
                )

            if not _norm(getattr(finding, "risk_scenario", "")) or not _norm(getattr(finding, "control_impact", "")):
                issues.append(
                    _issue(
                        rule_id="finding_missing_structured_risk_analysis",
                        severity="blocking",
                        title="High-priority finding missing structured risk analysis",
                        message=f"Finding {finding.observation_id or finding.reference} lacks a risk scenario or internal-control impact.",
                        recommendation="Provide risk_scenario, business/control impact, root cause and aggravating factors for High/Critical findings.",
                        affected_observation_ids=[finding.observation_id],
                        affected_applications=[finding.application] if finding.application else [],
                        affected_section="findings",
                        score_impact=10,
                    )
                )

            if not _has_recommendation_auditability(finding.recommendation + " " + " ".join(getattr(finding, "recommendation_steps", []) or [])):
                issues.append(
                    _issue(
                        rule_id="finding_recommendation_not_auditable",
                        severity="blocking",
                        title="Recommendation is not auditable enough",
                        message=f"Finding {finding.observation_id or finding.reference} recommendation lacks evidence and follow-up mechanisms.",
                        recommendation="Add owner, proof expected, control evidence, exception tracking and periodic follow-up.",
                        affected_observation_ids=[finding.observation_id],
                        affected_applications=[finding.application] if finding.application else [],
                        affected_section="recommendations",
                        score_impact=10,
                    )
                )

    for observation in audit_input.observations:
        if not observation.included_in_report:
            continue
        if _norm(observation.statut_validation) != "validated":
            issues.append(
                _issue(
                    rule_id="report_includes_unvalidated_observation",
                    severity="blocking",
                    title="Included finding not validated",
                    message=f"Observation {observation.observation_id} is included in the report while its validation status is '{observation.statut_validation or 'blank'}'.",
                    recommendation="Validate the observation or exclude it from the report before export.",
                    affected_observation_ids=[observation.observation_id],
                    affected_applications=[observation.application] if observation.application else [],
                    affected_section="findings",
                    score_impact=10,
                )
            )

    critical_findings = [finding for finding in findings if _norm(finding.priority) == "critical"]
    weak_critical_justifications = [
        finding
        for finding in critical_findings
        if not _has_sufficient_priority_justification(finding.priority_justification)
    ]
    if len(critical_findings) >= 3 and weak_critical_justifications:
        issues.append(
            _issue(
                rule_id="critical_density_without_justification",
                severity="warning",
                title="High number of Critical findings with weak justification",
                message=(
                    f"{len(critical_findings)} findings are marked Critical and "
                    f"{len(weak_critical_justifications)} of them lack strong factual justification."
                ),
                recommendation="Review the Critical classifications and reinforce or downgrade weakly justified items.",
                affected_observation_ids=[finding.observation_id for finding in weak_critical_justifications],
                affected_section="synthesis",
                score_impact=8,
            )
        )

    if _looks_short(report_output.general_synthesis, 120):
        issues.append(
            _issue(
                rule_id="general_synthesis_too_short",
                severity="blocking",
                title="General synthesis too short",
                message="The report synthesis is empty or too generic for executive review.",
                recommendation="Expand the synthesis with mission-specific findings, risk themes, and management implications.",
                affected_section="synthesis",
                score_impact=12,
            )
        )

    if _looks_short(report_output.conclusion, 60):
        issues.append(
            _issue(
                rule_id="conclusion_missing_or_too_short",
                severity="blocking",
                title="Conclusion missing or too short",
                message="The report conclusion is empty or too short to support export.",
                recommendation="Write a clear closing conclusion with the expected management actions.",
                affected_section="export",
                score_impact=10,
            )
        )

    duplicates: dict[str, list[str]] = defaultdict(list)
    for finding in findings:
        duplicate_key = _norm(f"{finding.title}|{finding.finding}")
        if duplicate_key:
            duplicates[duplicate_key].append(finding.observation_id)
    duplicated_groups = [ids for ids in duplicates.values() if len(ids) > 1]
    if duplicated_groups:
        flat_ids = [item for group in duplicated_groups for item in group]
        issues.append(
            _issue(
                rule_id="duplicate_findings_detected",
                severity="warning",
                title="Potential duplicate findings detected",
                message=f"{len(duplicated_groups)} duplicate finding group(s) were detected in the report draft.",
                recommendation="Review duplicated findings and merge or reword them before export.",
                affected_observation_ids=flat_ids,
                affected_section="findings",
                score_impact=6,
            )
        )

    covered_controls = list(report_output.covered_controls or [])
    control_matrix = list(report_output.control_matrix or [])
    covered_applications = {
        _norm(application)
        for entry in control_matrix
        for application, status in (entry.application_statuses or {}).items()
        if _norm(status) and _norm(status) != "non applicable"
    }
    if not covered_applications:
        covered_applications = {_norm(app) for app in report_output.applications or []}
    applications_with_critical_findings = {
        _norm(finding.application) for finding in critical_findings if _norm(finding.application)
    }
    uncovered_critical_apps = sorted(
        app for app in applications_with_critical_findings if app not in covered_applications
    )
    if uncovered_critical_apps and covered_controls:
        issues.append(
            _issue(
                rule_id="critical_application_without_covered_control",
                severity="warning",
                title="Critical application without covered control",
                message="At least one application with Critical findings does not appear covered in the control matrix.",
                recommendation="Review the control coverage section and ensure critical applications are explicitly mapped to controls.",
                affected_applications=uncovered_critical_apps,
                affected_section="controls",
                score_impact=7,
            )
        )

    blocking_count = sum(1 for issue in issues if issue.severity == "blocking")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    total_penalty = sum(issue.score_impact for issue in issues)
    readiness_score = max(0, 100 - total_penalty)
    export_allowed = blocking_count == 0

    if not issues:
        summary = "The report passed all quality-gate checks and is ready for export."
    elif export_allowed:
        summary = (
            f"The report can be exported, but {warning_count} warning(s) should be reviewed "
            "to improve executive readiness."
        )
    else:
        summary = (
            f"The report is blocked for export until {blocking_count} blocking issue(s) are resolved."
        )

    return ReportQualityGateResult(
        readiness_score=readiness_score,
        export_allowed=export_allowed,
        blocking_issues_count=blocking_count,
        warning_issues_count=warning_count,
        summary=summary,
        issues=issues,
    )
