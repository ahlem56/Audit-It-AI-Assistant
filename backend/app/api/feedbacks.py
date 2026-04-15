from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.models.api_models import AuditorFeedback, CreateFeedbackPayload, UpdateFeedbackStatusPayload

MISSIONS_DIR = Path("app/data/missions")

router = APIRouter(prefix="/missions")


def _mission_dir(mission_id: str) -> Path:
    return MISSIONS_DIR / mission_id


def _ensure_mission_exists(mission_id: str) -> None:
    if not _mission_dir(mission_id).is_dir():
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


def _list_feedbacks(mission_id: str) -> dict:
    _ensure_mission_exists(mission_id)
    return {
        "mission_id": mission_id,
        "feedbacks": _load_feedbacks(mission_id),
    }


def _create_feedback(mission_id: str, payload: CreateFeedbackPayload) -> dict:
    _ensure_mission_exists(mission_id)

    feedback = AuditorFeedback(
        feedback_id=uuid.uuid4().hex[:12],
        mission_id=mission_id,
        created_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        **payload.model_dump(),
    )

    feedbacks = _load_feedbacks(mission_id)
    feedbacks.append(feedback.model_dump())
    _save_feedbacks(mission_id, feedbacks)
    return feedback.model_dump()


def _update_feedback_status(mission_id: str, feedback_id: str, payload: UpdateFeedbackStatusPayload) -> dict:
    _ensure_mission_exists(mission_id)

    feedbacks = _load_feedbacks(mission_id)
    for feedback in feedbacks:
        if feedback.get("feedback_id") == feedback_id:
            feedback["status"] = payload.status
            _save_feedbacks(mission_id, feedbacks)
            return feedback

    raise ValueError(f"Feedback '{feedback_id}' was not found.")


def _delete_feedback(mission_id: str, feedback_id: str) -> dict:
    _ensure_mission_exists(mission_id)

    feedbacks = _load_feedbacks(mission_id)
    updated_feedbacks = [feedback for feedback in feedbacks if feedback.get("feedback_id") != feedback_id]
    if len(updated_feedbacks) == len(feedbacks):
        raise ValueError(f"Feedback '{feedback_id}' was not found.")

    _save_feedbacks(mission_id, updated_feedbacks)
    return {"deleted": feedback_id}


@router.get("/{mission_id}/feedbacks")
async def get_feedbacks(mission_id: str):
    try:
        return await run_in_threadpool(_list_feedbacks, mission_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{mission_id}/feedbacks", response_model=AuditorFeedback)
async def create_feedback(mission_id: str, payload: CreateFeedbackPayload):
    try:
        return await run_in_threadpool(_create_feedback, mission_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{mission_id}/feedbacks/{feedback_id}", response_model=AuditorFeedback)
async def update_feedback_status(mission_id: str, feedback_id: str, payload: UpdateFeedbackStatusPayload):
    try:
        return await run_in_threadpool(_update_feedback_status, mission_id, feedback_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{mission_id}/feedbacks/{feedback_id}")
async def delete_feedback(mission_id: str, feedback_id: str):
    try:
        return await run_in_threadpool(_delete_feedback, mission_id, feedback_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
