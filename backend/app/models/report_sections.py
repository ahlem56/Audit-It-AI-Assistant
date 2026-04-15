from __future__ import annotations

from typing import Optional

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


class DetailedFinding(BaseModel):
    observation_id: str
    reference: str
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
    impact_detail: str = ""
    root_cause: str = ""
    recommendation: str
    recommendation_objective: str = ""
    recommendation_steps: list[str] = Field(default_factory=list)
    priority: str
    priority_justification: str = ""
    auditor_comment: str = ""
    management_summary: str = ""


class FollowUpItem(BaseModel):
    reference: str
    description: str
    status: str
    current_state: str


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
