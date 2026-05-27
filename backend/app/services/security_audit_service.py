from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Request
from sqlalchemy import select

from app.config.settings import DATA_DIR
from app.db.models import SecurityAuditEventRecord
from app.db.session import get_db_session
from app.services.sql_storage_service import azure_sql_enabled

AUDIT_LOG_PATH = DATA_DIR / "security_audit_events.jsonl"
GENESIS_HASH = "0" * 64


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    return {
        str(key): value
        for key, value in metadata.items()
        if value is not None
    }


def _client_ip(request: Request | None) -> str:
    if request is None:
        return ""
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else ""


def _user_agent(request: Request | None) -> str:
    if request is None:
        return ""
    return request.headers.get("user-agent", "")[:500]


def _canonical_event_payload(event: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in event.items()
        if key != "hash"
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event_hash(event: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_event_payload(event).encode("utf-8")).hexdigest()


def _last_local_hash() -> str:
    if not AUDIT_LOG_PATH.exists():
        return GENESIS_HASH
    last_line = ""
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                last_line = line
    if not last_line:
        return GENESIS_HASH
    try:
        return str(json.loads(last_line).get("hash") or GENESIS_HASH)
    except json.JSONDecodeError:
        return GENESIS_HASH


def _last_sql_hash() -> str:
    if not azure_sql_enabled():
        return GENESIS_HASH
    with get_db_session() as session:
        record = session.execute(
            select(SecurityAuditEventRecord)
            .order_by(SecurityAuditEventRecord.timestamp.desc())
            .limit(1)
        ).scalar_one_or_none()
        return record.hash if record else GENESIS_HASH


def _store_local_event(event: dict[str, Any]) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def _store_sql_event(event: dict[str, Any]) -> None:
    with get_db_session() as session:
        session.add(
            SecurityAuditEventRecord(
                event_id=event["event_id"],
                timestamp=event["timestamp"],
                user_id=event.get("user_id") or None,
                user_email=event.get("user_email") or None,
                organization_id=event.get("organization_id") or None,
                mission_id=event.get("mission_id") or None,
                action=event["action"],
                resource_type=event.get("resource_type") or None,
                resource_id=event.get("resource_id") or None,
                ip_address=event.get("ip_address") or None,
                user_agent=event.get("user_agent") or None,
                status=event.get("status") or "success",
                metadata_json=json.dumps(event.get("metadata_json") or {}, ensure_ascii=False, sort_keys=True),
                hash=event["hash"],
                previous_hash=event.get("previous_hash") or GENESIS_HASH,
            )
        )


def log_security_event(
    *,
    action: str,
    user: dict[str, Any] | None = None,
    request: Request | None = None,
    mission_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status: str = "success",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous_hash = _last_sql_hash() if azure_sql_enabled() else _last_local_hash()
    event = {
        "event_id": uuid.uuid4().hex,
        "timestamp": _timestamp(),
        "user_id": str((user or {}).get("user_id") or ""),
        "user_email": str((user or {}).get("email") or ""),
        "organization_id": str((user or {}).get("organization") or ""),
        "mission_id": mission_id or "",
        "action": action,
        "resource_type": resource_type or "",
        "resource_id": resource_id or "",
        "ip_address": _client_ip(request),
        "user_agent": _user_agent(request),
        "status": status,
        "metadata_json": _normalize_metadata(metadata),
        "previous_hash": previous_hash,
    }
    event["hash"] = _event_hash(event)
    if azure_sql_enabled():
        _store_sql_event(event)
    else:
        _store_local_event(event)
    return event


def _read_local_events(limit: int) -> list[dict[str, Any]]:
    if not AUDIT_LOG_PATH.exists():
        return []
    events: list[dict[str, Any]] = []
    with AUDIT_LOG_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return list(reversed(events))[:limit]


def _read_sql_events(limit: int) -> list[dict[str, Any]]:
    with get_db_session() as session:
        records = session.execute(
            select(SecurityAuditEventRecord)
            .order_by(SecurityAuditEventRecord.timestamp.desc())
            .limit(limit)
        ).scalars().all()
        return [
            {
                "event_id": record.event_id,
                "timestamp": record.timestamp,
                "user_id": record.user_id or "",
                "user_email": record.user_email or "",
                "organization_id": record.organization_id or "",
                "mission_id": record.mission_id or "",
                "action": record.action,
                "resource_type": record.resource_type or "",
                "resource_id": record.resource_id or "",
                "ip_address": record.ip_address or "",
                "user_agent": record.user_agent or "",
                "status": record.status,
                "metadata_json": json.loads(record.metadata_json or "{}"),
                "hash": record.hash,
                "previous_hash": record.previous_hash or GENESIS_HASH,
            }
            for record in records
        ]


def list_security_events(limit: int = 100) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 500))
    return _read_sql_events(bounded_limit) if azure_sql_enabled() else _read_local_events(bounded_limit)


def verify_event_chain(events: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = list(reversed(events))
    previous_hash = GENESIS_HASH
    for index, event in enumerate(ordered):
        expected_previous = previous_hash
        if event.get("previous_hash") != expected_previous:
            return {
                "valid": False,
                "checked_events": index + 1,
                "reason": "Previous hash mismatch.",
            }
        expected_hash = _event_hash(event)
        if event.get("hash") != expected_hash:
            return {
                "valid": False,
                "checked_events": index + 1,
                "reason": "Event hash mismatch.",
            }
        previous_hash = str(event.get("hash") or "")
    return {
        "valid": True,
        "checked_events": len(ordered),
        "reason": "Audit chain is intact.",
    }
