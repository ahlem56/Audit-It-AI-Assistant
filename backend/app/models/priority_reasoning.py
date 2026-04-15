from __future__ import annotations

from pydantic import BaseModel


class PriorityReasoning(BaseModel):
    observation_id: str = ""
    priority: str = ""
    priority_justification: str = ""

