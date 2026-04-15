from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.agent_outputs import SourceReference
from app.models.report_sections import AuditReportOutput


class ExportReportRequest(BaseModel):
    request: str
    structured_output: AuditReportOutput
    sources: list[SourceReference] = Field(default_factory=list)
