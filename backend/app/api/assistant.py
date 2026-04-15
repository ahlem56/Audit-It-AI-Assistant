from typing import Annotated, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.models.api_models import AssistantRequest
from app.services.assistant_service import build_export_file, process_assistant_request
from app.utils.file_naming import slugify, timestamp

router = APIRouter()


@router.post("/assistant")
async def assistant(
    payload: Annotated[Optional[AssistantRequest], Body()] = None,
    user_input: Annotated[Optional[str], Query()] = None,
    export: Annotated[Optional[bool], Query()] = None,
    mission_id: Annotated[Optional[str], Query()] = None,
):
    try:
        resolved_user_input = (user_input or "").strip()
        resolved_export = bool(export)
        resolved_mission_id = (mission_id or "").strip() or None

        if not resolved_user_input and payload:
            payload_user_input = (payload.user_input or "").strip()
            if payload_user_input.lower() != "string":
                resolved_user_input = payload_user_input
            resolved_export = payload.export
            resolved_mission_id = (payload.mission_id or "").strip() or resolved_mission_id

        if not resolved_user_input:
            raise HTTPException(status_code=400, detail="user_input must be provided.")

        result = await run_in_threadpool(process_assistant_request, resolved_user_input, resolved_mission_id)
    except ValueError as exc:
        detail = str(exc)
        if "was not found" in detail:
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc

    if not resolved_export:
        return result

    if result.get("agent") != "report_agent":
        raise HTTPException(
            status_code=400,
            detail="Export is supported only for report generation results.",
        )

    file_stream = await run_in_threadpool(build_export_file, result)
    filename = f"report_{slugify(resolved_user_input)}_{timestamp()}.pptx"
    media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    return StreamingResponse(
        file_stream,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
