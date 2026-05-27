from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.agents.report_agent import generate_audit_report
from app.models.api_models import (
    MissionCreateRequest,
    MissionDeleteResponse,
    MissionInviteRequest,
    MissionQualityGateResponse,
    MissionResponse,
    MissionUpdateRequest,
    SendReportEmailRequest,
    SendReportEmailResponse,
)
from app.models.report_sections import AuditReportOutput
from app.services.assistant_service import build_export_file
from app.services.auth_service import require_authenticated_user, require_manager_user
from app.services.mission_service import (
    create_mission,
    delete_mission,
    get_all_missions,
    get_mission,
    invite_auditor_to_mission,
    load_mission_audit_input,
    save_mission_report_cache,
    update_mission,
    user_can_manage_mission,
)
from app.services.notification_service import create_notifications, mission_recipients
from app.services.quality_gate_service import evaluate_report_quality_gate
from app.services.report_email_service import (
    build_default_report_email_body,
    build_default_report_email_subject,
    default_report_recipient,
    send_mission_invitation_email,
    send_report_email,
)
from app.services.security_audit_service import log_security_event
from app.utils.file_naming import slugify, timestamp

MISSIONS_DIR = Path("app/data/missions")
REPORT_CACHE_MAX_AGE = timedelta(hours=1)

router = APIRouter()


def _mission_report_filename(mission: dict, mission_id: str) -> str:
    return f"report_{slugify(mission.get('name') or mission_id)}_{timestamp()}.pptx"


def _mission_report_filename_for_format(mission: dict, mission_id: str, export_format: str) -> str:
    extension = "pdf" if export_format == "pdf" else "docx" if export_format == "docx" else "pptx"
    return f"report_{slugify(mission.get('name') or mission_id)}_{timestamp()}.{extension}"


def _audit_input_path(mission_id: str) -> Path:
    return MISSIONS_DIR / mission_id / "audit_input.json"


def _report_cache_path(mission_id: str) -> Path:
    return MISSIONS_DIR / mission_id / "report_cache.json"


def _load_cached_report(mission_id: str) -> dict | None:
    cache_path = _report_cache_path(mission_id)
    audit_input_path = _audit_input_path(mission_id)
    if not cache_path.exists() or not audit_input_path.exists():
        return None

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    cached_at_raw = payload.get("cached_at")
    cached_input_mtime = payload.get("audit_input_mtime_ns")
    result = payload.get("result")
    if not cached_at_raw or result is None:
        return None

    try:
        cached_at = datetime.fromisoformat(cached_at_raw)
    except ValueError:
        return None

    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) - cached_at > REPORT_CACHE_MAX_AGE:
        return None

    current_input_mtime = audit_input_path.stat().st_mtime_ns
    if cached_input_mtime != current_input_mtime:
        return None

    return result


def _save_cached_report(mission_id: str, result: dict, user_id: str | None = None) -> dict:
    cache_path = _report_cache_path(mission_id)
    audit_input_path = _audit_input_path(mission_id)
    cache_payload = {
        "cached_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "audit_input_mtime_ns": audit_input_path.stat().st_mtime_ns,
        "result": result,
    }
    cache_path.write_text(
        json.dumps(cache_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return save_mission_report_cache(mission_id, result, user_id=user_id)


def _generate_and_cache_report(mission_id: str, audit_input, user_id: str | None = None) -> dict:
    result = generate_audit_report(
        f"Generate report for mission {mission_id}",
        None,
        audit_input,
    )
    return _save_cached_report(mission_id, result, user_id=user_id)


def _load_or_generate_report_result(mission_id: str, audit_input, user_id: str | None = None) -> dict:
    cached = _load_cached_report(mission_id)
    if cached is not None:
        return cached
    return _generate_and_cache_report(mission_id, audit_input, user_id=user_id)


def _compute_quality_gate(mission_id: str, audit_input, user_id: str | None = None) -> MissionQualityGateResponse:
    report_result = _load_or_generate_report_result(mission_id, audit_input, user_id=user_id)
    structured_output = AuditReportOutput.model_validate(report_result.get("structured_output", {}))
    gate = evaluate_report_quality_gate(audit_input, structured_output)
    return MissionQualityGateResponse(mission_id=mission_id, **gate.model_dump())


@router.get("/missions", response_model=list[MissionResponse])
async def list_missions(user=Depends(require_authenticated_user)):
    return await run_in_threadpool(get_all_missions, user=user)


@router.post("/missions", response_model=MissionResponse)
async def create_mission_endpoint(payload: MissionCreateRequest, request: Request, user=Depends(require_manager_user)):
    try:
        mission = await run_in_threadpool(create_mission, payload.model_dump(), user)
        await run_in_threadpool(
            log_security_event,
            action="MISSION_CREATED",
            user=user,
            request=request,
            mission_id=mission.get("mission_id"),
            resource_type="mission",
            resource_id=mission.get("mission_id"),
            metadata={"mission_name": mission.get("name"), "client_name": mission.get("client_name")},
        )
        return mission
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/missions/{mission_id}", response_model=MissionResponse)
async def get_mission_endpoint(mission_id: str, request: Request, user=Depends(require_authenticated_user)):
    mission = await run_in_threadpool(get_mission, mission_id, user=user)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found.")
    await run_in_threadpool(
        log_security_event,
        action="MISSION_VIEWED",
        user=user,
        request=request,
        mission_id=mission_id,
        resource_type="mission",
        resource_id=mission_id,
    )
    return mission


@router.put("/missions/{mission_id}", response_model=MissionResponse)
async def update_mission_endpoint(mission_id: str, payload: MissionUpdateRequest, user=Depends(require_manager_user)):
    can_manage = await run_in_threadpool(user_can_manage_mission, mission_id, user)
    if not can_manage:
        raise HTTPException(status_code=404, detail="Mission not found.")
    try:
        return await run_in_threadpool(
            update_mission,
            mission_id,
            payload.model_dump(exclude_none=True),
            user=user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/missions/{mission_id}", response_model=MissionDeleteResponse)
async def delete_mission_endpoint(mission_id: str, user=Depends(require_manager_user)):
    try:
        return await run_in_threadpool(delete_mission, mission_id, user=user)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "was not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/missions/{mission_id}/invite-auditor", response_model=MissionResponse)
async def invite_auditor_endpoint(
    mission_id: str,
    payload: MissionInviteRequest,
    request: Request,
    user=Depends(require_manager_user),
):
    try:
        mission = await run_in_threadpool(
            invite_auditor_to_mission,
            mission_id,
            payload.auditor_email,
            manager_user=user,
        )
        await run_in_threadpool(
            log_security_event,
            action="USER_INVITED",
            user=user,
            request=request,
            mission_id=mission_id,
            resource_type="mission_invitation",
            resource_id=payload.auditor_email,
            metadata={"invited_email": payload.auditor_email},
        )
        await run_in_threadpool(
            send_mission_invitation_email,
            to_email=payload.auditor_email,
            mission_name=mission.get("name") or "",
            client_name=mission.get("client_name") or "",
            fiscal_year=mission.get("fiscal_year") or "",
            invited_by=user.get("display_name") or user.get("email") or "",
        )
        return mission
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "was not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/missions/{mission_id}/report-preview")
async def get_report_preview(mission_id: str, user=Depends(require_authenticated_user)):
    audit_input = await run_in_threadpool(load_mission_audit_input, mission_id, user_id=user["user_id"])
    if audit_input is None:
        raise HTTPException(status_code=404, detail="Mission audit input not found.")

    cached = await run_in_threadpool(_load_cached_report, mission_id)
    if cached is not None:
        return cached

    result = await run_in_threadpool(_generate_and_cache_report, mission_id, audit_input, user["user_id"])
    return result


@router.post("/missions/{mission_id}/report-preview/regenerate")
async def regenerate_report_preview(mission_id: str, user=Depends(require_authenticated_user)):
    audit_input = await run_in_threadpool(load_mission_audit_input, mission_id, user_id=user["user_id"])
    if audit_input is None:
        raise HTTPException(status_code=404, detail="Mission audit input not found.")
    return await run_in_threadpool(_generate_and_cache_report, mission_id, audit_input, user["user_id"])


@router.get("/missions/{mission_id}/quality-gate", response_model=MissionQualityGateResponse)
async def get_quality_gate(mission_id: str, user=Depends(require_authenticated_user)):
    audit_input = await run_in_threadpool(load_mission_audit_input, mission_id, user_id=user["user_id"])
    if audit_input is None:
        raise HTTPException(status_code=404, detail="Mission audit input not found.")
    return await run_in_threadpool(_compute_quality_gate, mission_id, audit_input, user["user_id"])


@router.get("/missions/{mission_id}/export-report")
async def export_report(
    mission_id: str,
    request: Request,
    format: Literal["pptx", "pdf", "docx"] = Query(default="pptx"),
    user=Depends(require_authenticated_user),
):
    audit_input = await run_in_threadpool(load_mission_audit_input, mission_id, user_id=user["user_id"])
    mission = await run_in_threadpool(get_mission, mission_id, user_id=user["user_id"])
    if audit_input is None or mission is None:
        raise HTTPException(status_code=404, detail="Mission report data not found.")

    result = await run_in_threadpool(_load_cached_report, mission_id)
    if result is None:
        result = await run_in_threadpool(_generate_and_cache_report, mission_id, audit_input, user["user_id"])

    file_stream = await run_in_threadpool(build_export_file, result, format)
    filename = _mission_report_filename_for_format(mission, mission_id, format)
    media_type = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }[format]
    await run_in_threadpool(
        update_mission,
        mission_id,
        {
            "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "status": "Finalized",
        },
        user_id=user["user_id"],
    )
    finalized_mission = await run_in_threadpool(get_mission, mission_id, user_id=user["user_id"])
    if finalized_mission is not None:
        await run_in_threadpool(
            create_notifications,
            recipients=mission_recipients(finalized_mission),
            type="report_finalized",
            title="Report finalized",
            message=f"The report for mission {finalized_mission.get('name') or mission_id} has been finalized.",
            mission_id=mission_id,
            related_entity_type="report",
            related_entity_id=mission_id,
            actor=user,
        )
    await run_in_threadpool(
        log_security_event,
        action="REPORT_EXPORTED",
        user=user,
        request=request,
        mission_id=mission_id,
        resource_type="report",
        resource_id=filename,
        metadata={"format": format},
    )

    return StreamingResponse(
        file_stream,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/missions/{mission_id}/report-email-defaults")
async def get_report_email_defaults(mission_id: str, user=Depends(require_authenticated_user)):
    mission = await run_in_threadpool(get_mission, mission_id, user_id=user["user_id"])
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found.")

    return {
        "to_email": default_report_recipient(),
        "subject": build_default_report_email_subject(
            mission_name=mission.get("name") or "",
            client_name=mission.get("client_name") or "",
            fiscal_year=mission.get("fiscal_year") or "",
        ),
        "body": build_default_report_email_body(
            client_name=mission.get("client_name") or "",
            mission_name=mission.get("name") or "",
            fiscal_year=mission.get("fiscal_year") or "",
        ),
    }


@router.post("/missions/{mission_id}/send-report-email", response_model=SendReportEmailResponse)
async def send_report_email_endpoint(mission_id: str, payload: SendReportEmailRequest, user=Depends(require_authenticated_user)):
    audit_input = await run_in_threadpool(load_mission_audit_input, mission_id, user_id=user["user_id"])
    mission = await run_in_threadpool(get_mission, mission_id, user_id=user["user_id"])
    if audit_input is None or mission is None:
        raise HTTPException(status_code=404, detail="Mission report data not found.")

    result = await run_in_threadpool(_load_cached_report, mission_id)
    if result is None:
        result = await run_in_threadpool(_generate_and_cache_report, mission_id, audit_input, user["user_id"])

    try:
        file_stream = await run_in_threadpool(build_export_file, result)
        attachment_bytes = file_stream.getvalue()
        filename = _mission_report_filename(mission, mission_id)
        await run_in_threadpool(
            send_report_email,
            to_email=payload.to_email,
            subject=payload.subject,
            body=payload.body,
            attachment_bytes=attachment_bytes,
            attachment_filename=filename,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to send report email: {exc}") from exc

    return SendReportEmailResponse(
        mission_id=mission_id,
        sent_to=payload.to_email,
        subject=payload.subject,
        filename=filename,
    )
