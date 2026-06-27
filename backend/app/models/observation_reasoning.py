from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def _coerce_text_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return [str(value).strip()] if str(value).strip() else []


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

    @field_validator("aggravating_factors", "recommendation_steps", mode="before")
    @classmethod
    def normalize_text_lists(cls, value: object) -> list[str]:
        return _coerce_text_list(value)
