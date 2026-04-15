from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.agents.report_agent import generate_audit_report
from app.models.api_models import MissionCreateRequest, MissionDeleteResponse, MissionResponse, MissionUpdateRequest
from app.services.assistant_service import build_export_file
from app.services.mission_service import (
    create_mission,
    delete_mission,
    get_all_missions,
    get_mission,
    load_mission_audit_input,
    update_mission,
)
from app.utils.file_naming import slugify, timestamp

MISSIONS_DIR = Path("app/data/missions")
REPORT_CACHE_MAX_AGE = timedelta(hours=1)

router = APIRouter()


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


def _save_cached_report(mission_id: str, result: dict) -> dict:
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
    return result


def _generate_and_cache_report(mission_id: str, audit_input) -> dict:
    result = generate_audit_report(
        f"Generate report for mission {mission_id}",
        None,
        audit_input,
    )
    return _save_cached_report(mission_id, result)


@router.get("/missions", response_model=list[MissionResponse])
async def list_missions():
    return await run_in_threadpool(get_all_missions)


@router.post("/missions", response_model=MissionResponse)
async def create_mission_endpoint(payload: MissionCreateRequest):
    try:
        return await run_in_threadpool(create_mission, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/missions/{mission_id}", response_model=MissionResponse)
async def get_mission_endpoint(mission_id: str):
    mission = await run_in_threadpool(get_mission, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found.")
    return mission


@router.put("/missions/{mission_id}", response_model=MissionResponse)
async def update_mission_endpoint(mission_id: str, payload: MissionUpdateRequest):
    try:
        return await run_in_threadpool(
            update_mission,
            mission_id,
            payload.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/missions/{mission_id}", response_model=MissionDeleteResponse)
async def delete_mission_endpoint(mission_id: str):
    try:
        return await run_in_threadpool(delete_mission, mission_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "was not found" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/missions/{mission_id}/report-preview")
async def get_report_preview(mission_id: str):
    audit_input = await run_in_threadpool(load_mission_audit_input, mission_id)
    if audit_input is None:
        raise HTTPException(status_code=404, detail="Mission audit input not found.")

    cached = await run_in_threadpool(_load_cached_report, mission_id)
    if cached is not None:
        return cached

    return await run_in_threadpool(_generate_and_cache_report, mission_id, audit_input)


@router.post("/missions/{mission_id}/report-preview/regenerate")
async def regenerate_report_preview(mission_id: str):
    audit_input = await run_in_threadpool(load_mission_audit_input, mission_id)
    if audit_input is None:
        raise HTTPException(status_code=404, detail="Mission audit input not found.")
    return await run_in_threadpool(_generate_and_cache_report, mission_id, audit_input)


@router.get("/missions/{mission_id}/export-report")
async def export_report(mission_id: str):
    audit_input = await run_in_threadpool(load_mission_audit_input, mission_id)
    mission = await run_in_threadpool(get_mission, mission_id)
    if audit_input is None or mission is None:
        raise HTTPException(status_code=404, detail="Mission report data not found.")

    result = await run_in_threadpool(_load_cached_report, mission_id)
    if result is None:
        result = await run_in_threadpool(_generate_and_cache_report, mission_id, audit_input)

    file_stream = await run_in_threadpool(build_export_file, result)
    filename = f"report_{slugify(mission.get('name') or mission_id)}_{timestamp()}.pptx"
    media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    return StreamingResponse(
        file_stream,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
