from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.models.api_models import NotificationResponse
from app.services.auth_service import require_authenticated_user
from app.services.notification_service import (
    list_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)

router = APIRouter()


@router.get("/notifications", response_model=list[NotificationResponse])
async def get_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    user=Depends(require_authenticated_user),
):
    return await run_in_threadpool(list_user_notifications, user, unread_only=unread_only, limit=limit)


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def read_notification(notification_id: str, user=Depends(require_authenticated_user)):
    notification = await run_in_threadpool(mark_notification_read, notification_id, user)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return notification


@router.post("/notifications/read-all")
async def read_all_notifications(user=Depends(require_authenticated_user)):
    count = await run_in_threadpool(mark_all_notifications_read, user)
    return {"updated": count}
