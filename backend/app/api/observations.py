from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app.models.api_models import ObservationsUpdateRequest
from app.services.auth_service import require_authenticated_user, user_is_manager
from app.services.mission_service import load_mission_audit_input, save_mission_audit_input
from app.services.priority_recalculation_service import recalculate_mission_observation_priorities
from app.services.security_audit_service import log_security_event

router = APIRouter()


def _normalize_validation_status(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or "draft"


def _replace_observations(
    mission_id: str,
    observations_update: ObservationsUpdateRequest,
    user_id: str,
    *,
    can_validate: bool = False,
) -> dict:
    audit_input = load_mission_audit_input(mission_id, user_id=user_id)
    if audit_input is None:
        raise ValueError(f"Mission '{mission_id}' audit input was not found.")

    if not can_validate:
        current_statuses = {
            observation.observation_id: _normalize_validation_status(observation.statut_validation)
            for observation in audit_input.observations
        }
        for observation in observations_update.observations:
            observation_id = observation.observation_id
            next_status = _normalize_validation_status(observation.statut_validation)
            if observation_id in current_statuses and next_status != current_statuses[observation_id]:
                raise PermissionError("Only managers can update observation validation status.")
            if observation_id not in current_statuses and next_status == "validated":
                raise PermissionError("Only managers can update observation validation status.")

    updated_input = audit_input.model_copy(update={"observations": observations_update.observations})
    save_mission_audit_input(mission_id, updated_input, user_id=user_id)
    return {
        "mission_id": mission_id,
        "observations": [observation.model_dump() for observation in updated_input.observations],
    }


def _recalculate_observations(mission_id: str, user_id: str, preserve_manual_overrides: bool = True) -> dict:
    return recalculate_mission_observation_priorities(
        mission_id,
        user_id,
        preserve_manual_overrides=preserve_manual_overrides,
    )


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
        result = await run_in_threadpool(
            _replace_observations,
            mission_id,
            payload,
            user["user_id"],
            can_validate=user_is_manager(user),
        )
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
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
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
