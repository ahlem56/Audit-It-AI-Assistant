from __future__ import annotations

from pydantic import BaseModel, Field


class ObservationReasoning(BaseModel):
    observation_id: str = ""
    risk: str = ""
    impact: str = ""
    root_cause: str = ""
    priority: str = ""
    priority_justification: str = ""
    recommendation: str = ""
    recommendation_objective: str = ""
    recommendation_steps: list[str] = Field(default_factory=list)

