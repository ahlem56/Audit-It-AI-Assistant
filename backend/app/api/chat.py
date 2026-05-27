from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.models.api_models import ChatRequest
from app.services.auth_service import require_authenticated_user
from app.services.assistant_service import process_assistant_request
from app.services.security_audit_service import log_security_event

router = APIRouter()


@router.post("/chat")
async def chat(
    request: Request,
    payload: Annotated[Optional[ChatRequest], Body()] = None,
    question: Annotated[Optional[str], Query()] = None,
    mission_id: Annotated[Optional[str], Query()] = None,
    user=Depends(require_authenticated_user),
):
    resolved_question = (question or "").strip()
    resolved_mission_id = (mission_id or "").strip() or None

    if not resolved_question and payload:
        payload_question = (payload.question or "").strip()
        if payload_question.lower() != "string":
            resolved_question = payload_question
        resolved_mission_id = (payload.mission_id or "").strip() or resolved_mission_id

    if not resolved_question:
        raise HTTPException(status_code=400, detail="A question must be provided.")
    if not resolved_mission_id:
        raise HTTPException(status_code=400, detail="A mission_id must be provided for mission-scoped AI access.")

    try:
        await run_in_threadpool(
            log_security_event,
            action="CHAT_QUESTION_ASKED",
            user=user,
            request=request,
            mission_id=resolved_mission_id,
            resource_type="chat",
            resource_id=resolved_mission_id,
            metadata={"question_length": len(resolved_question)},
        )
        result = await run_in_threadpool(process_assistant_request, resolved_question, resolved_mission_id, user_id=user["user_id"])
        await run_in_threadpool(
            log_security_event,
            action="AI_ANSWER_GENERATED",
            user=user,
            request=request,
            mission_id=resolved_mission_id,
            resource_type="chat",
            resource_id=resolved_mission_id,
            metadata={
                "agent": result.get("agent"),
                "sources_count": len(result.get("sources") or []),
                "answer_length": len(str(result.get("answer") or "")),
            },
        )
        return result
    except ValueError as exc:
        detail = str(exc)
        if "was not found" in detail:
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc
