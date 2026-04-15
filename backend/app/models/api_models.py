from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.audit_input import AuditObservation


class AssistantRequest(BaseModel):
    user_input: str = Field(..., min_length=1)
    export: bool = False
    mission_id: Optional[str] = None


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    mission_id: Optional[str] = None


MissionStatus = Literal["Draft", "Ready", "Finalized"]
ParsingStatus = Literal["not_uploaded", "parsing", "parsed", "error"]


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


class MissionDeleteResponse(BaseModel):
    deleted: str


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
    author: Optional[str] = None
    scope: Optional[str] = None
    target_id: Optional[str] = None
    rating: Optional[int] = None
    sentiment: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    comment: Optional[str] = None
    requires_action: bool = False


class UpdateFeedbackStatusPayload(BaseModel):
    status: str
