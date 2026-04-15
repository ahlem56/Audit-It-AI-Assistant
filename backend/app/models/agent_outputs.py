from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class RetrievalStepEvaluation(BaseModel):
    relevant: bool = True
    sufficient: bool = True
    reason: str = ""
    retry_step: Optional[str] = None


class RetrievalPlan(BaseModel):
    needs_multi_hop: bool = False
    retrieval_steps: list[str] = Field(default_factory=lambda: ["general"])
    comparison_required: bool = False
    final_task: str = "qa"


class SourceReference(BaseModel):
    source_id: str
    document_name: str
    chunk_id: Optional[int] = None
    score: Optional[float] = None
    excerpt: Optional[str] = None


class AgentResult(BaseModel):
    agent: str
    answer: str
    sources: list[SourceReference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
