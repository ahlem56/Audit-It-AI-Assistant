from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.audit_input import AuditObservation
from app.models.report_sections import ReportQualityGateResult


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    mission_id: Optional[str] = None


MissionStatus = Literal["Draft", "Ready", "Finalized"]
ParsingStatus = Literal["not_uploaded", "parsing", "parsed", "error"]
WorkflowStepState = Literal["completed", "in_progress", "coming_next"]


class MissionCreateRequest(BaseModel):
    mission_id: Optional[str] = None
    name: str = Field(..., min_length=1)
    client_name: str = ""
    fiscal_year: str = ""
    status: MissionStatus = "Draft"


class MissionUpdateRequest(BaseModel):
    name: Optional[str] = None
    client_name: Optional[str] = None
    fiscal_year: Optional[str] = None
    status: Optional[MissionStatus] = None
    parsing_status: Optional[ParsingStatus] = None
    uploaded_file_name: Optional[str] = None


class MissionWorkflowStepResponse(BaseModel):
    key: str
    label: str
    state: WorkflowStepState
    status_label: str
    description: str


class MissionWorkflowResponse(BaseModel):
    steps: list[MissionWorkflowStepResponse] = Field(default_factory=list)
    next_best_action: str = ""
    validated_observations_count: int = 0
    total_observations_count: int = 0
    report_generated: bool = False
    exported_at: Optional[str] = None


class MissionResponse(BaseModel):
    mission_id: str
    name: str
    client_name: str = ""
    fiscal_year: str = ""
    status: MissionStatus = "Draft"
    created_at: str
    updated_at: str
    uploaded_file_name: Optional[str] = None
    parsing_status: ParsingStatus = "not_uploaded"
    observations_count: int = 0
    applications_count: int = 0
    control_ids_count: int = 0
    report_generated_at: Optional[str] = None
    exported_at: Optional[str] = None
    owner_email: str = ""
    invited_auditor_emails: list[str] = Field(default_factory=list)
    workflow: MissionWorkflowResponse = Field(default_factory=MissionWorkflowResponse)


class MissionDeleteResponse(BaseModel):
    deleted: str


class SendReportEmailRequest(BaseModel):
    to_email: str = Field(..., min_length=3)
    subject: str = Field(..., min_length=3)
    body: str = Field(..., min_length=3)


class SendReportEmailResponse(BaseModel):
    mission_id: str
    sent_to: str
    subject: str
    filename: str
    status: str = "sent"


class MissionQualityGateResponse(ReportQualityGateResult):
    mission_id: str


class MissionInviteRequest(BaseModel):
    auditor_email: str = Field(..., min_length=3, max_length=255)


class ObservationsUpdateRequest(BaseModel):
    observations: list[AuditObservation] = Field(default_factory=list)
    preserve_manual_overrides: bool = True


class AuditorFeedback(BaseModel):
    feedback_id: str
    mission_id: str
    created_at: str
    author: Optional[str] = None
    scope: Optional[str] = None
    target_id: Optional[str] = None
    rating: Optional[int] = None
    sentiment: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    comment: Optional[str] = None
    requires_action: bool = False
    status: str = "pending"


class CreateFeedbackPayload(BaseModel):
    scope: Literal["report", "observation"] = "report"
    target_id: Optional[str] = None
    rating: Optional[int] = None
    sentiment: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    comment: Optional[str] = None
    requires_action: bool = False


class UpdateFeedbackStatusPayload(BaseModel):
    status: str


class AuthUser(BaseModel):
    user_id: str
    email: str
    first_name: str = ""
    last_name: str = ""
    display_name: str = ""
    organization: str = ""
    job_title: str = ""
    role: str = "auditor"
    auth_provider: str = "entra_external_id"
    last_login_at: Optional[str] = None
    profile_image_url: Optional[str] = None


class AuthConfigResponse(BaseModel):
    enabled: bool
    provider: str
    login_url: Optional[str] = None
    signup_url: Optional[str] = None
    logout_url: Optional[str] = None
    password_sign_in_enabled: bool = True
    microsoft_sign_in_enabled: bool = True


class AuthSessionResponse(BaseModel):
    authenticated: bool
    auth_enabled: bool
    user: Optional[AuthUser] = None


class LogoutResponse(BaseModel):
    logged_out: bool
    logout_url: Optional[str] = None


class UpdateMyProfileRequest(BaseModel):
    organization: Optional[str] = Field(default=None, max_length=200)
    job_title: Optional[str] = Field(default=None, max_length=200)


class NotificationResponse(BaseModel):
    notification_id: str
    recipient_email: str = ""
    type: str
    title: str
    message: str
    mission_id: Optional[str] = None
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[str] = None
    is_read: bool = False
    created_at: str
    read_at: Optional[str] = None
