from typing import Annotated, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.models.api_models import ChatRequest
from app.services.assistant_service import process_assistant_request

router = APIRouter()


@router.post("/chat")
async def chat(
    payload: Annotated[Optional[ChatRequest], Body()] = None,
    question: Annotated[Optional[str], Query()] = None,
    mission_id: Annotated[Optional[str], Query()] = None,
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

    try:
        return await run_in_threadpool(process_assistant_request, resolved_question, resolved_mission_id)
    except ValueError as exc:
        detail = str(exc)
        if "was not found" in detail:
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc
