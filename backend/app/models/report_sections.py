from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field
from app.models.audit_input import ApplicationScope


class CoveredControl(BaseModel):
    reference: str
    process: str
    description: str
    test_procedure: str


class ControlMatrixEntry(BaseModel):
    reference: str
    process: str = ""
    control_description: str = ""
    application_statuses: dict[str, str] = Field(default_factory=dict)
    overall_priority: Optional[str] = None


class PrioritySummaryItem(BaseModel):
    priority: str
    count: int
    percentage: float


class KeyFigure(BaseModel):
    label: str
    value: str
    commentary: str = ""


class ProcessSummary(BaseModel):
    process_code: str
    process_name: str
    observation_count: int
    applications: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    watch_points: list[str] = Field(default_factory=list)


class TraceabilitySource(BaseModel):
    source_id: str = ""
    document_name: str = ""
    source_type: str = ""
    excerpt: str = ""


class FindingTraceability(BaseModel):
    observation_source_id: str = ""
    original_reference: str = ""
    resolved_reference: str = ""
    fields_used: list[str] = Field(default_factory=list)
    source_documents: list[TraceabilitySource] = Field(default_factory=list)
    heuristic_rules_triggered: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    priority_justification: str = ""
    priority_decision_mode: str = ""
    recommendation_decision_mode: str = ""
    agent: str = "report_agent"
    generated_at: str = ""
    report_version: str = ""


class DetailedFinding(BaseModel):
    observation_id: str
    original_reference: str = ""
    reference: str
    resolved_reference_reason: str = ""
    domain: str
    category: str = ""
    application: str
    layer: str = ""
    owners: str = ""
    title: str
    expected_control: str
    finding: str
    compensating_procedure: str
    risk_impact: str
    risk_scenario: str = ""
    impact_detail: str = ""
    business_impact: str = ""
    control_impact: str = ""
    compliance_impact: str = ""
    root_cause: str = ""
    aggravating_factors: list[str] = Field(default_factory=list)
    recommendation: str
    recommendation_objective: str = ""
    immediate_action: str = ""
    structural_action: str = ""
    owner: str = ""
    evidence_expected: str = ""
    follow_up_mechanism: str = ""
    recommendation_steps: list[str] = Field(default_factory=list)
    recommendation_decision_mode: str = ""
    priority: str
    priority_justification: str = ""
    priority_decision_mode: str = ""
    escalation_reason: str = ""
    auditor_comment: str = ""
    management_summary: str = ""
    traceability: FindingTraceability = Field(default_factory=FindingTraceability)


class FollowUpItem(BaseModel):
    reference: str
    description: str
    status: str
    current_state: str


QualityIssueSeverity = Literal["blocking", "warning"]


class QualityGateIssue(BaseModel):
    rule_id: str
    severity: QualityIssueSeverity
    title: str
    message: str
    recommendation: str = ""
    affected_observation_ids: list[str] = Field(default_factory=list)
    affected_applications: list[str] = Field(default_factory=list)
    affected_section: str = ""
    score_impact: int = 0


class ReportQualityGateResult(BaseModel):
    readiness_score: int = 100
    export_allowed: bool = True
    blocking_issues_count: int = 0
    warning_issues_count: int = 0
    summary: str = ""
    issues: list[QualityGateIssue] = Field(default_factory=list)


class AuditReportOutput(BaseModel):
    cover_title: str = ""
    cover_subtitle: str = ""
    client_name: str = ""
    report_period: str = ""
    report_date: str = ""
    confidentiality_notice: str = "Strictement prive et confidentiel"
    table_of_contents: list[str] = Field(default_factory=list)
    preamble: str = ""
    objectives: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    scope_summary: str = ""
    applications: list[str] = Field(default_factory=list)
    application_details: list[ApplicationScope] = Field(default_factory=list)
    covered_processes: list[str] = Field(default_factory=list)
    audit_approach: list[str] = Field(default_factory=list)
    covered_controls: list[CoveredControl] = Field(default_factory=list)
    control_matrix: list[ControlMatrixEntry] = Field(default_factory=list)
    key_figures: list[KeyFigure] = Field(default_factory=list)
    executive_highlights: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    watch_points: list[str] = Field(default_factory=list)
    maturity_level: str = ""
    maturity_assessment: str = ""
    priority_insight: str = ""
    strategic_priorities: list[str] = Field(default_factory=list)
    transversal_initiatives: list[str] = Field(default_factory=list)
    process_summaries: list[ProcessSummary] = Field(default_factory=list)
    general_synthesis: str = ""
    priority_summary: list[PrioritySummaryItem] = Field(default_factory=list)
    detailed_findings: list[DetailedFinding] = Field(default_factory=list)
    detailed_recommendations: list[DetailedFinding] = Field(default_factory=list)
    prior_recommendations_follow_up: list[FollowUpItem] = Field(default_factory=list)
    appendices: list[str] = Field(default_factory=list)
    executive_summary: str = ""
    conclusion: str = ""
    quality_gate: ReportQualityGateResult = Field(default_factory=ReportQualityGateResult)
