from __future__ import annotations

from pydantic import BaseModel, Field


class ObservationReasoning(BaseModel):
    observation_id: str = ""
    risk: str = ""
    risk_scenario: str = ""
    impact: str = ""
    business_impact: str = ""
    control_impact: str = ""
    compliance_impact: str = ""
    root_cause: str = ""
    aggravating_factors: list[str] = Field(default_factory=list)
    priority: str = ""
    priority_justification: str = ""
    recommendation: str = ""
    recommendation_objective: str = ""
    immediate_action: str = ""
    structural_action: str = ""
    owner: str = ""
    evidence_expected: str = ""
    follow_up_mechanism: str = ""
    recommendation_steps: list[str] = Field(default_factory=list)
