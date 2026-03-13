from pydantic import BaseModel, Field
from typing import List


class ObservationOutput(BaseModel):
    title: str = Field(..., description="Title of the audit observation")
    condition: str = Field(..., description="Observed condition")
    risk_impact: str = Field(..., description="Risk or impact of the issue")
    recommendation: str = Field(..., description="Recommended action")


class RCMRow(BaseModel):
    process_domain: str
    risk: str
    control: str
    test_procedure: str
    expected_evidence: str
    source_reference: str


class RCMOutput(BaseModel):
    rows: List[RCMRow]


class AuditReportOutput(BaseModel):
    executive_summary: str
    scope: str
    key_risks_identified: str
    controls_observed: str
    main_observations: str
    recommendations: str
    conclusion: str