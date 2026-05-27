from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.models.api_models import AuditorFeedback, CreateFeedbackPayload, UpdateFeedbackStatusPayload
from app.services.auth_service import require_authenticated_user
from app.services.mission_service import get_mission
from app.services.sql_storage_service import (
    azure_sql_enabled,
    create_feedback as create_sql_feedback,
    delete_feedback as delete_sql_feedback,
    list_feedbacks as list_sql_feedbacks,
    update_feedback_status as update_sql_feedback_status,
)

MISSIONS_DIR = Path("app/data/missions")

router = APIRouter(prefix="/missions")


def _mission_dir(mission_id: str) -> Path:
    return MISSIONS_DIR / mission_id


def _ensure_mission_exists(mission_id: str, user_id: str) -> None:
    mission = get_mission(mission_id, user_id=user_id)
    if mission is None:
        raise ValueError(f"Mission '{mission_id}' was not found.")


def _load_feedbacks(mission_id: str) -> list:
    path = MISSIONS_DIR / mission_id / "feedbacks.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_feedbacks(mission_id: str, feedbacks: list):
    path = MISSIONS_DIR / mission_id / "feedbacks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(feedbacks, f, ensure_ascii=False, indent=2)


def _list_feedbacks(mission_id: str, user_id: str) -> dict:
    _ensure_mission_exists(mission_id, user_id)
    return {
        "mission_id": mission_id,
        "feedbacks": list_sql_feedbacks(mission_id) if azure_sql_enabled() else _load_feedbacks(mission_id),
    }


def _feedback_author(user: dict) -> str:
    return (
        str(user.get("display_name") or "").strip()
        or str(user.get("email") or "").strip()
        or "Authenticated user"
    )


def _create_feedback(mission_id: str, payload: CreateFeedbackPayload, user: dict) -> dict:
    user_id = str(user["user_id"])
    _ensure_mission_exists(mission_id, user_id)

    feedback = AuditorFeedback(
        feedback_id=uuid.uuid4().hex[:12],
        mission_id=mission_id,
        created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        author=_feedback_author(user),
        **payload.model_dump(),
    )

    if azure_sql_enabled():
        create_sql_feedback(feedback.model_dump())
    else:
        feedbacks = _load_feedbacks(mission_id)
        feedbacks.append(feedback.model_dump())
        _save_feedbacks(mission_id, feedbacks)
    return feedback.model_dump()


def _update_feedback_status(mission_id: str, feedback_id: str, payload: UpdateFeedbackStatusPayload, user_id: str) -> dict:
    _ensure_mission_exists(mission_id, user_id)

    if azure_sql_enabled():
        updated = update_sql_feedback_status(mission_id, feedback_id, payload.status)
        if updated:
            return updated
    else:
        feedbacks = _load_feedbacks(mission_id)
        for feedback in feedbacks:
            if feedback.get("feedback_id") == feedback_id:
                feedback["status"] = payload.status
                _save_feedbacks(mission_id, feedbacks)
                return feedback

    raise ValueError(f"Feedback '{feedback_id}' was not found.")


def _delete_feedback(mission_id: str, feedback_id: str, user_id: str) -> dict:
    _ensure_mission_exists(mission_id, user_id)

    if azure_sql_enabled():
        deleted = delete_sql_feedback(mission_id, feedback_id)
        if not deleted:
            raise ValueError(f"Feedback '{feedback_id}' was not found.")
    else:
        feedbacks = _load_feedbacks(mission_id)
        updated_feedbacks = [feedback for feedback in feedbacks if feedback.get("feedback_id") != feedback_id]
        if len(updated_feedbacks) == len(feedbacks):
            raise ValueError(f"Feedback '{feedback_id}' was not found.")
        _save_feedbacks(mission_id, updated_feedbacks)
    return {"deleted": feedback_id}


@router.get("/{mission_id}/feedbacks")
async def get_feedbacks(mission_id: str, user=Depends(require_authenticated_user)):
    try:
        return await run_in_threadpool(_list_feedbacks, mission_id, user["user_id"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{mission_id}/feedbacks", response_model=AuditorFeedback)
async def create_feedback(mission_id: str, payload: CreateFeedbackPayload, user=Depends(require_authenticated_user)):
    try:
        return await run_in_threadpool(_create_feedback, mission_id, payload, user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{mission_id}/feedbacks/{feedback_id}", response_model=AuditorFeedback)
async def update_feedback_status(mission_id: str, feedback_id: str, payload: UpdateFeedbackStatusPayload, user=Depends(require_authenticated_user)):
    try:
        return await run_in_threadpool(_update_feedback_status, mission_id, feedback_id, payload, user["user_id"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{mission_id}/feedbacks/{feedback_id}")
async def delete_feedback(mission_id: str, feedback_id: str, user=Depends(require_authenticated_user)):
    try:
        return await run_in_threadpool(_delete_feedback, mission_id, feedback_id, user["user_id"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
