from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from app.services.auth_service import require_authenticated_user
from app.services.mission_service import get_all_missions
from app.services.security_audit_service import list_security_events, verify_event_chain

router = APIRouter(prefix="/security")


def _visible_events_for_user(user: dict, limit: int) -> dict:
    events = list_security_events(limit=limit)
    chain = verify_event_chain(events)
    accessible_mission_ids = {
        mission["mission_id"]
        for mission in get_all_missions(user=user)
    }
    user_id = str(user.get("user_id") or "")

    visible_events = []
    for event in events:
        event_mission_id = str(event.get("mission_id") or "")
        event_user_id = str(event.get("user_id") or "")
        if event_mission_id and event_mission_id in accessible_mission_ids:
            visible_events.append(event)
        elif not event_mission_id and event_user_id == user_id:
            visible_events.append(event)

    return {
        "events": visible_events[:limit],
        "chain": chain,
    }


@router.get("/audit-events")
async def get_security_audit_events(
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(require_authenticated_user),
):
    return await run_in_threadpool(_visible_events_for_user, user, limit)
