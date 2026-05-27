from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app.agents.report_agent import generate_audit_report
from app.models.api_models import ObservationsUpdateRequest
from app.models.audit_input import StructuredAuditInput
from app.models.report_sections import DetailedFinding
from app.services.auth_service import require_authenticated_user
from app.services.mission_service import load_mission_audit_input, save_mission_audit_input, save_mission_report_cache
from app.services.report_composer_service import recalculate_audit_input_priorities
from app.services.security_audit_service import log_security_event

router = APIRouter()


def _replace_observations(mission_id: str, observations_update: ObservationsUpdateRequest, user_id: str) -> dict:
    audit_input = load_mission_audit_input(mission_id, user_id=user_id)
    if audit_input is None:
        raise ValueError(f"Mission '{mission_id}' audit input was not found.")

    updated_input = audit_input.model_copy(update={"observations": observations_update.observations})
    save_mission_audit_input(mission_id, updated_input, user_id=user_id)
    return {
        "mission_id": mission_id,
        "observations": [observation.model_dump() for observation in updated_input.observations],
    }


def _recalculate_observations(mission_id: str, user_id: str, preserve_manual_overrides: bool = True) -> dict:
    audit_input = load_mission_audit_input(mission_id, user_id=user_id)
    if audit_input is None:
        raise ValueError(f"Mission '{mission_id}' audit input was not found.")

    report_result = generate_audit_report(
        f"Generate report for mission {mission_id}",
        None,
        audit_input,
    )
    save_mission_report_cache(mission_id, report_result, user_id=user_id)
    raw_findings = report_result.get("structured_output", {}).get("detailed_findings", [])
    findings = [DetailedFinding.model_validate(item) for item in raw_findings]

    recalculated = recalculate_audit_input_priorities(
        audit_input,
        preserve_manual_overrides=preserve_manual_overrides,
        findings=findings,
    )
    save_mission_audit_input(mission_id, recalculated, user_id=user_id)
    return {
        "mission_id": mission_id,
        "observations": [observation.model_dump() for observation in recalculated.observations],
    }


@router.get("/missions/{mission_id}/observations")
async def get_observations(mission_id: str, user=Depends(require_authenticated_user)):
    audit_input = await run_in_threadpool(load_mission_audit_input, mission_id, user_id=user["user_id"])
    if audit_input is None:
        raise HTTPException(status_code=404, detail="Mission audit input not found.")
    return {
        "mission_id": mission_id,
        "mission": audit_input.mission.model_dump(),
        "observations": [observation.model_dump() for observation in audit_input.observations],
    }


@router.put("/missions/{mission_id}/observations")
async def update_observations(
    mission_id: str,
    payload: ObservationsUpdateRequest,
    request: Request,
    user=Depends(require_authenticated_user),
):
    try:
        result = await run_in_threadpool(_replace_observations, mission_id, payload, user["user_id"])
        await run_in_threadpool(
            log_security_event,
            action="OBSERVATION_UPDATED",
            user=user,
            request=request,
            mission_id=mission_id,
            resource_type="observation_set",
            resource_id=mission_id,
            metadata={"observations_count": len(payload.observations)},
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/missions/{mission_id}/observations/recalculate-priorities")
async def recalculate_priorities(
    mission_id: str,
    request: Request,
    user=Depends(require_authenticated_user),
):
    try:
        result = await run_in_threadpool(_recalculate_observations, mission_id, user["user_id"], True)
        await run_in_threadpool(
            log_security_event,
            action="PRIORITY_RECALCULATED",
            user=user,
            request=request,
            mission_id=mission_id,
            resource_type="observation_set",
            resource_id=mission_id,
            metadata={"observations_count": len(result.get("observations") or [])},
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
