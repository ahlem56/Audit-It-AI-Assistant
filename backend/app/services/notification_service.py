from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select

from app.db.models import NotificationRecord
from app.db.session import get_db_session
from app.services.sql_storage_service import azure_sql_enabled

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
NOTIFICATIONS_PATH = DATA_DIR / "notifications.json"


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def _actor_user_id(actor: dict[str, Any] | None) -> str:
    return str((actor or {}).get("user_id") or "").strip()


def _actor_email(actor: dict[str, Any] | None) -> str:
    return _normalize_email(str((actor or {}).get("email") or ""))


def _read_local_notifications() -> list[dict[str, Any]]:
    if not NOTIFICATIONS_PATH.exists():
        return []
    try:
        payload = json.loads(NOTIFICATIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _write_local_notifications(notifications: list[dict[str, Any]]) -> None:
    NOTIFICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    NOTIFICATIONS_PATH.write_text(
        json.dumps(notifications, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _notification_to_dict(record: NotificationRecord) -> dict[str, Any]:
    return {
        "notification_id": record.notification_id,
        "recipient_user_id": record.recipient_user_id,
        "recipient_email": record.recipient_email or "",
        "actor_user_id": record.actor_user_id,
        "actor_email": record.actor_email,
        "type": record.type,
        "title": record.title,
        "message": record.message,
        "mission_id": record.mission_id,
        "related_entity_type": record.related_entity_type,
        "related_entity_id": record.related_entity_id,
        "is_read": bool(record.is_read),
        "created_at": record.created_at,
        "read_at": record.read_at,
    }


def mission_recipients(mission: dict[str, Any], *, include_owner: bool = True) -> list[dict[str, str]]:
    recipients: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(user_id: str | None = None, email: str | None = None) -> None:
        normalized_email = _normalize_email(email)
        normalized_user_id = str(user_id or "").strip()
        if not normalized_email and not normalized_user_id:
            return
        key = (normalized_user_id, normalized_email)
        if key in seen:
            return
        seen.add(key)
        recipients.append({"user_id": normalized_user_id, "email": normalized_email})

    if include_owner:
        add(mission.get("owner_user_id"), mission.get("owner_email"))
    for email in mission.get("invited_auditor_emails") or []:
        add(email=str(email))
    return recipients


def create_notifications(
    *,
    recipients: list[dict[str, str]],
    type: str,
    title: str,
    message: str,
    mission_id: str | None = None,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
    actor: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    actor_user_id = _actor_user_id(actor)
    actor_email = _actor_email(actor)
    now = _timestamp()
    payloads: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for recipient in recipients:
        recipient_user_id = str(recipient.get("user_id") or "").strip()
        recipient_email = _normalize_email(recipient.get("email"))
        if not recipient_user_id and not recipient_email:
            continue
        if recipient_user_id and recipient_user_id == actor_user_id:
            continue
        if recipient_email and recipient_email == actor_email:
            continue
        key = (recipient_user_id, recipient_email)
        if key in seen:
            continue
        seen.add(key)
        payloads.append(
            {
                "notification_id": uuid.uuid4().hex,
                "recipient_user_id": recipient_user_id or None,
                "recipient_email": recipient_email,
                "actor_user_id": actor_user_id or None,
                "actor_email": actor_email or None,
                "type": type,
                "title": title,
                "message": message,
                "mission_id": mission_id,
                "related_entity_type": related_entity_type,
                "related_entity_id": related_entity_id,
                "is_read": False,
                "created_at": now,
                "read_at": None,
            }
        )

    if not payloads:
        return []

    if azure_sql_enabled():
        with get_db_session() as session:
            records = [NotificationRecord(**payload) for payload in payloads]
            session.add_all(records)
            session.flush()
            return [_notification_to_dict(record) for record in records]

    notifications = _read_local_notifications()
    notifications.extend(payloads)
    _write_local_notifications(notifications)
    return payloads


def list_user_notifications(user: dict[str, Any], *, unread_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    user_id = str(user.get("user_id") or "").strip()
    email = _normalize_email(user.get("email"))

    if azure_sql_enabled():
        with get_db_session() as session:
            conditions = []
            if user_id:
                conditions.append(NotificationRecord.recipient_user_id == user_id)
            if email:
                conditions.append(NotificationRecord.recipient_email == email)
            if not conditions:
                return []
            query = select(NotificationRecord).where(or_(*conditions))
            if unread_only:
                query = query.where(NotificationRecord.is_read == False)  # noqa: E712
            records = session.execute(
                query.order_by(NotificationRecord.created_at.desc()).limit(limit)
            ).scalars().all()
            return [_notification_to_dict(record) for record in records]

    notifications = [
        notification
        for notification in _read_local_notifications()
        if (user_id and notification.get("recipient_user_id") == user_id)
        or (email and _normalize_email(notification.get("recipient_email")) == email)
    ]
    if unread_only:
        notifications = [notification for notification in notifications if not notification.get("is_read")]
    notifications.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return notifications[:limit]


def mark_notification_read(notification_id: str, user: dict[str, Any]) -> dict[str, Any] | None:
    user_id = str(user.get("user_id") or "").strip()
    email = _normalize_email(user.get("email"))
    now = _timestamp()

    if azure_sql_enabled():
        with get_db_session() as session:
            record = session.get(NotificationRecord, notification_id)
            if record is None:
                return None
            if record.recipient_user_id != user_id and _normalize_email(record.recipient_email) != email:
                return None
            record.is_read = True
            record.read_at = now
            session.flush()
            return _notification_to_dict(record)

    notifications = _read_local_notifications()
    updated: dict[str, Any] | None = None
    for notification in notifications:
        if notification.get("notification_id") != notification_id:
            continue
        if notification.get("recipient_user_id") != user_id and _normalize_email(notification.get("recipient_email")) != email:
            continue
        notification["is_read"] = True
        notification["read_at"] = now
        updated = notification
        break
    if updated is not None:
        _write_local_notifications(notifications)
    return updated


def mark_all_notifications_read(user: dict[str, Any]) -> int:
    user_id = str(user.get("user_id") or "").strip()
    email = _normalize_email(user.get("email"))
    now = _timestamp()

    if azure_sql_enabled():
        with get_db_session() as session:
            conditions = []
            if user_id:
                conditions.append(NotificationRecord.recipient_user_id == user_id)
            if email:
                conditions.append(NotificationRecord.recipient_email == email)
            if not conditions:
                return 0
            records = session.execute(
                select(NotificationRecord).where(or_(*conditions), NotificationRecord.is_read == False)  # noqa: E712
            ).scalars().all()
            for record in records:
                record.is_read = True
                record.read_at = now
            return len(records)

    notifications = _read_local_notifications()
    count = 0
    for notification in notifications:
        is_recipient = (
            user_id and notification.get("recipient_user_id") == user_id
        ) or (
            email and _normalize_email(notification.get("recipient_email")) == email
        )
        if is_recipient and not notification.get("is_read"):
            notification["is_read"] = True
            notification["read_at"] = now
            count += 1
    if count:
        _write_local_notifications(notifications)
    return count
