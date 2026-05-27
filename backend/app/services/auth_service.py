from __future__ import annotations

import base64
import imghdr
import json
import logging
import secrets
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import delete, or_, select

from app.config.settings import (
    AUTH_DEMO_USER_EMAIL,
    AUTH_DEMO_USER_NAME,
    AUTH_DEMO_USER_ORGANIZATION,
    AUTH_DEMO_USER_ROLE,
    AUTH_ENABLED,
    AUTH_ENTRA_CLIENT_ID,
    AUTH_ENTRA_CLIENT_SECRET,
    AUTH_ENTRA_METADATA_URL,
    AUTH_ENTRA_POST_LOGOUT_REDIRECT_URI,
    AUTH_ENTRA_REDIRECT_URI,
    AUTH_FRONTEND_BASE_URL,
    AUTH_MANAGER_EMAILS,
    AUTH_PROFILE_IMAGES_DIR,
    AUTH_SESSION_COOKIE_NAME,
    AUTH_SESSION_TTL_HOURS,
    AUTH_SQLITE_PATH,
    AZURE_STORAGE_CONNECTION_STRING,
    AZURE_STORAGE_CONTAINER_PROFILE_IMAGES,
    GRAPH_DELEGATED_SCOPES,
)
from app.db.models import AppUserRecord, AuthSessionRecord, AuthStateRecord
from app.db.session import get_db_session
from app.services.blob_service import delete_blob, download_blob, upload_blob
from app.services.sql_storage_service import azure_sql_enabled

logger = logging.getLogger(__name__)

_METADATA_CACHE: dict[str, Any] | None = None
_METADATA_FETCHED_AT: datetime | None = None
_METADATA_CACHE_TTL = timedelta(minutes=30)
_STATE_TTL = timedelta(minutes=15)
_LAST_AUTH_PURGE_ATTEMPT: datetime | None = None
_AUTH_PURGE_INTERVAL = timedelta(minutes=10)
_ALLOWED_AVATAR_IMAGE_TYPES = {
    "png": ".png",
    "jpeg": ".jpg",
    "webp": ".webp",
}
_AVATAR_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
}
_MAX_AVATAR_BYTES = 2 * 1024 * 1024
_OPENID_SCOPES = "openid profile email offline_access"


class AuthConfigurationError(RuntimeError):
    pass


class AuthenticationError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _now()).replace(microsecond=0).isoformat()


def _entra_login_scopes() -> str:
    return " ".join(
        scope
        for scope in f"{_OPENID_SCOPES} {GRAPH_DELEGATED_SCOPES}".split()
        if scope
    )


def _db_connection() -> sqlite3.Connection:
    AUTH_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(AUTH_SQLITE_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def _auth_uses_sql() -> bool:
    return azure_sql_enabled()


def _record_to_dict(record: Any | None) -> dict[str, Any] | None:
    if record is None:
        return None
    if isinstance(record, dict):
        return record
    if isinstance(record, sqlite3.Row):
        return {key: record[key] for key in record.keys()}
    return {
        column.name: getattr(record, column.name)
        for column in record.__table__.columns
    }


def init_auth_storage() -> None:
    if _profile_images_use_blob_storage():
        logger.info(
            "Profile images will be stored in Azure Blob container '%s'.",
            AZURE_STORAGE_CONTAINER_PROFILE_IMAGES,
        )
    else:
        logger.warning("Profile images will be stored locally because Azure Blob Storage is not configured.")

    if _auth_uses_sql():
        purge_expired_auth_records()
        AUTH_PROFILE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        return

    with _db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_users (
                user_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                email_normalized TEXT NOT NULL UNIQUE,
                first_name TEXT NOT NULL DEFAULT '',
                last_name TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                organization TEXT NOT NULL DEFAULT '',
                job_title TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'auditor',
                auth_provider TEXT NOT NULL DEFAULT 'entra_external_id',
                entra_subject TEXT NOT NULL UNIQUE,
                entra_oid TEXT,
                entra_tid TEXT,
                profile_image_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT,
                raw_claims TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(app_users)").fetchall()
        }
        if "profile_image_path" not in columns:
            connection.execute("ALTER TABLE app_users ADD COLUMN profile_image_path TEXT")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_states (
                state_token TEXT PRIMARY KEY,
                nonce TEXT NOT NULL,
                next_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                session_token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                user_agent TEXT NOT NULL DEFAULT '',
                graph_access_token TEXT,
                graph_refresh_token TEXT,
                graph_token_expires_at TEXT,
                FOREIGN KEY (user_id) REFERENCES app_users(user_id) ON DELETE CASCADE
            )
            """
        )
        session_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(auth_sessions)").fetchall()
        }
        for column_name in ("graph_access_token", "graph_refresh_token", "graph_token_expires_at"):
            if column_name not in session_columns:
                connection.execute(f"ALTER TABLE auth_sessions ADD COLUMN {column_name} TEXT")
        connection.commit()
    purge_expired_auth_records()
    AUTH_PROFILE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def purge_expired_auth_records() -> None:
    now = _timestamp()
    if _auth_uses_sql():
        with get_db_session() as session:
            session.execute(delete(AuthStateRecord).where(AuthStateRecord.expires_at < now))
            session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.expires_at < now))
        return

    with _db_connection() as connection:
        connection.execute("DELETE FROM auth_states WHERE expires_at < ?", (now,))
        connection.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (now,))
        connection.commit()


def purge_expired_auth_records_best_effort() -> None:
    global _LAST_AUTH_PURGE_ATTEMPT

    current_time = _now()
    if _LAST_AUTH_PURGE_ATTEMPT and current_time - _LAST_AUTH_PURGE_ATTEMPT < _AUTH_PURGE_INTERVAL:
        return
    _LAST_AUTH_PURGE_ATTEMPT = current_time

    try:
        purge_expired_auth_records()
    except Exception as exc:
        logger.warning("Skipping expired auth cleanup after storage error: %s", exc)


def _demo_user() -> dict[str, Any]:
    name_parts = [part for part in AUTH_DEMO_USER_NAME.split(" ", 1) if part]
    first_name = name_parts[0] if name_parts else "Demo"
    last_name = name_parts[1] if len(name_parts) > 1 else "Auditor"
    return {
        "user_id": "local-demo-user",
        "email": AUTH_DEMO_USER_EMAIL,
        "first_name": first_name,
        "last_name": last_name,
        "display_name": AUTH_DEMO_USER_NAME,
        "organization": AUTH_DEMO_USER_ORGANIZATION,
        "job_title": "Auditor",
        "role": "manager" if AUTH_DEMO_USER_ROLE == "manager" else "auditor",
        "auth_provider": "demo",
        "last_login_at": _timestamp(),
        "profile_image_url": None,
    }


def _profile_image_public_url(row: Any | None) -> str | None:
    if row is None:
        return None
    row_data = _record_to_dict(row) or {}
    profile_image_path = str(row_data.get("profile_image_path") or "").strip()
    if not profile_image_path:
        return None
    cache_buster = urllib.parse.quote(str(row_data.get("updated_at") or ""))
    return f"/api/auth/me/avatar?v={cache_buster}" if cache_buster else "/api/auth/me/avatar"


def _profile_image_absolute_path(profile_image_path: str) -> Path:
    return AUTH_PROFILE_IMAGES_DIR / profile_image_path


def _delete_profile_image_file(profile_image_path: str | None) -> None:
    if not profile_image_path:
        return
    try:
        _profile_image_absolute_path(profile_image_path).unlink(missing_ok=True)
    except OSError:
        pass


def _profile_image_uses_blob(profile_image_path: str) -> bool:
    return profile_image_path.startswith("blob:")


def _profile_images_use_blob_storage() -> bool:
    return bool(AZURE_STORAGE_CONNECTION_STRING and AZURE_STORAGE_CONTAINER_PROFILE_IMAGES)


def _profile_image_blob_name(profile_image_path: str) -> str:
    return profile_image_path.removeprefix("blob:")


def _delete_profile_image(profile_image_path: str | None) -> None:
    if not profile_image_path:
        return
    if _profile_image_uses_blob(profile_image_path):
        delete_blob(AZURE_STORAGE_CONTAINER_PROFILE_IMAGES, _profile_image_blob_name(profile_image_path))
        return
    _delete_profile_image_file(profile_image_path)


def get_my_profile_image(user_id: str) -> tuple[bytes, str]:
    row = _ensure_user_row(user_id)
    row_data = _record_to_dict(row) or {}
    profile_image_path = str(row_data.get("profile_image_path") or "").strip()
    if not profile_image_path:
        raise ValueError("No profile image found for this user.")

    extension = Path(_profile_image_blob_name(profile_image_path)).suffix.lower()
    content_type = _AVATAR_CONTENT_TYPES.get(extension, "application/octet-stream")

    if _profile_image_uses_blob(profile_image_path):
        return download_blob(AZURE_STORAGE_CONTAINER_PROFILE_IMAGES, _profile_image_blob_name(profile_image_path)), content_type

    absolute_path = _profile_image_absolute_path(profile_image_path)
    if not absolute_path.exists():
        raise ValueError("No profile image found for this user.")
    return absolute_path.read_bytes(), content_type


def _fetch_json(url: str, *, data: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request_headers = {"Accept": "application/json", **(headers or {})}
    payload = None
    if data is not None:
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        payload = urllib.parse.urlencode(data).encode("utf-8")

    request = urllib.request.Request(url, data=payload, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise AuthConfigurationError(f"Auth request failed for {url}: {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise AuthConfigurationError(f"Auth request failed for {url}: {exc.reason}") from exc


def _get_metadata() -> dict[str, Any]:
    global _METADATA_CACHE, _METADATA_FETCHED_AT

    if not AUTH_ENTRA_METADATA_URL:
        raise AuthConfigurationError("AUTH_ENTRA_METADATA_URL is missing.")
    if not AUTH_ENTRA_CLIENT_ID:
        raise AuthConfigurationError("AUTH_ENTRA_CLIENT_ID is missing.")
    if not AUTH_ENTRA_CLIENT_SECRET:
        raise AuthConfigurationError("AUTH_ENTRA_CLIENT_SECRET is missing.")

    if _METADATA_CACHE and _METADATA_FETCHED_AT and _now() - _METADATA_FETCHED_AT < _METADATA_CACHE_TTL:
        return _METADATA_CACHE

    metadata = _fetch_json(AUTH_ENTRA_METADATA_URL)
    _METADATA_CACHE = metadata
    _METADATA_FETCHED_AT = _now()
    return metadata


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise AuthenticationError("Invalid ID token received from Entra.")
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload + padding)
    return json.loads(decoded.decode("utf-8"))


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _role_for_email(email: str) -> str:
    return "manager" if _normalize_email(email) in AUTH_MANAGER_EMAILS else "auditor"


def _safe_next_path(next_path: str | None) -> str:
    candidate = (next_path or "/").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    return candidate


def _frontend_url(path: str) -> str:
    safe_path = _safe_next_path(path)
    return f"{AUTH_FRONTEND_BASE_URL}{safe_path}"


def get_auth_public_config() -> dict[str, Any]:
    logout_url = f"{AUTH_FRONTEND_BASE_URL}/login"
    return {
        "enabled": AUTH_ENABLED,
        "provider": "entra_external_id" if AUTH_ENABLED else "disabled",
        "login_url": "/api/auth/entra/login",
        "signup_url": "/api/auth/entra/login?prompt=create",
        "logout_url": logout_url,
        "password_sign_in_enabled": True,
        "microsoft_sign_in_enabled": True,
    }


def _store_state(state_token: str, nonce: str, next_path: str) -> None:
    now = _now()
    if _auth_uses_sql():
        with get_db_session() as session:
            existing = session.get(AuthStateRecord, state_token)
            if existing:
                session.delete(existing)
                session.flush()
            session.add(
                AuthStateRecord(
                    state_token=state_token,
                    nonce=nonce,
                    next_path=_safe_next_path(next_path),
                    created_at=_timestamp(now),
                    expires_at=_timestamp(now + _STATE_TTL),
                )
            )
        return

    with _db_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO auth_states (state_token, nonce, next_path, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                state_token,
                nonce,
                _safe_next_path(next_path),
                _timestamp(now),
                _timestamp(now + _STATE_TTL),
            ),
        )
        connection.commit()


def begin_entra_login(*, prompt: str | None = None, next_path: str | None = None) -> str:
    if not AUTH_ENABLED:
        return _frontend_url(_safe_next_path(next_path))

    metadata = _get_metadata()
    authorization_endpoint = metadata.get("authorization_endpoint")
    if not authorization_endpoint:
        raise AuthConfigurationError("The Entra metadata document does not expose an authorization endpoint.")

    state_token = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    _store_state(state_token, nonce, _safe_next_path(next_path))

    params = {
        "client_id": AUTH_ENTRA_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": AUTH_ENTRA_REDIRECT_URI,
        "response_mode": "query",
        "scope": _entra_login_scopes(),
        "state": state_token,
        "nonce": nonce,
    }
    if prompt:
        params["prompt"] = prompt

    return f"{authorization_endpoint}?{urllib.parse.urlencode(params)}"


def _pop_state(state_token: str) -> dict[str, Any] | sqlite3.Row | None:
    if _auth_uses_sql():
        with get_db_session() as session:
            record = session.get(AuthStateRecord, state_token)
            row = _record_to_dict(record)
            if record:
                session.delete(record)
            return row

    with _db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM auth_states WHERE state_token = ?",
            (state_token,),
        ).fetchone()
        connection.execute("DELETE FROM auth_states WHERE state_token = ?", (state_token,))
        connection.commit()
    return row


def _extract_email(claims: dict[str, Any]) -> str:
    candidates = [
        claims.get("email"),
        claims.get("preferred_username"),
        claims.get("upn"),
    ]
    emails = claims.get("emails")
    if isinstance(emails, list) and emails:
        candidates.append(emails[0])

    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    raise AuthenticationError("The authenticated Entra account did not return an email address.")


def _upsert_app_user(claims: dict[str, Any]) -> dict[str, Any]:
    email = _extract_email(claims)
    normalized_email = _normalize_email(email)
    display_name = str(claims.get("name") or "").strip()
    first_name = str(claims.get("given_name") or "").strip()
    last_name = str(claims.get("family_name") or "").strip()
    subject = str(claims.get("sub") or "").strip()
    entra_oid = str(claims.get("oid") or "").strip()
    entra_tid = str(claims.get("tid") or "").strip()
    if not subject:
        raise AuthenticationError("The Entra ID token did not include a stable subject claim.")

    now = _timestamp()
    role = _role_for_email(email)

    if _auth_uses_sql():
        with get_db_session() as session:
            existing = session.execute(
                select(AppUserRecord).where(
                    or_(
                        AppUserRecord.entra_subject == subject,
                        AppUserRecord.email_normalized == normalized_email,
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.email = email
                existing.email_normalized = normalized_email
                existing.first_name = first_name
                existing.last_name = last_name
                existing.display_name = display_name
                existing.auth_provider = "entra_external_id"
                existing.entra_subject = subject
                existing.entra_oid = entra_oid
                existing.entra_tid = entra_tid
                existing.role = role
                existing.updated_at = now
                existing.last_login_at = now
                existing.raw_claims = json.dumps(claims, ensure_ascii=False)
                user_id = existing.user_id
            else:
                user_id = uuid.uuid4().hex
                session.add(
                    AppUserRecord(
                        user_id=user_id,
                        email=email,
                        email_normalized=normalized_email,
                        first_name=first_name,
                        last_name=last_name,
                        display_name=display_name,
                        organization="",
                        job_title="",
                        role=role,
                        auth_provider="entra_external_id",
                        entra_subject=subject,
                        entra_oid=entra_oid,
                        entra_tid=entra_tid,
                        created_at=now,
                        updated_at=now,
                        last_login_at=now,
                        raw_claims=json.dumps(claims, ensure_ascii=False),
                    )
                )
            session.flush()
            row = session.get(AppUserRecord, user_id)
            return _row_to_user(row)

    with _db_connection() as connection:
        existing = connection.execute(
            "SELECT * FROM app_users WHERE entra_subject = ? OR email_normalized = ?",
            (subject, normalized_email),
        ).fetchone()

        if existing:
            connection.execute(
                """
                UPDATE app_users
                SET email = ?,
                    email_normalized = ?,
                    first_name = ?,
                    last_name = ?,
                    display_name = ?,
                    auth_provider = 'entra_external_id',
                    entra_subject = ?,
                    entra_oid = ?,
                    entra_tid = ?,
                    role = ?,
                    updated_at = ?,
                    last_login_at = ?,
                    raw_claims = ?
                WHERE user_id = ?
                """,
                (
                    email,
                    normalized_email,
                    first_name,
                    last_name,
                    display_name,
                    subject,
                    entra_oid,
                    entra_tid,
                    role,
                    now,
                    now,
                    json.dumps(claims, ensure_ascii=False),
                    existing["user_id"],
                ),
            )
            user_id = existing["user_id"]
        else:
            user_id = uuid.uuid4().hex
            connection.execute(
                """
                INSERT INTO app_users (
                    user_id,
                    email,
                    email_normalized,
                    first_name,
                    last_name,
                    display_name,
                    organization,
                    job_title,
                    role,
                    auth_provider,
                    entra_subject,
                    entra_oid,
                    entra_tid,
                    created_at,
                    updated_at,
                    last_login_at,
                    raw_claims
                )
                VALUES (?, ?, ?, ?, ?, ?, '', '', ?, 'entra_external_id', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    email,
                    normalized_email,
                    first_name,
                    last_name,
                    display_name,
                    role,
                    subject,
                    entra_oid,
                    entra_tid,
                    now,
                    now,
                    now,
                    json.dumps(claims, ensure_ascii=False),
                ),
            )

        connection.commit()
        row = connection.execute("SELECT * FROM app_users WHERE user_id = ?", (user_id,)).fetchone()

    return _row_to_user(row)


def _row_to_user(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row_data = _record_to_dict(row) or {}
    return {
        "user_id": row_data["user_id"],
        "email": row_data["email"],
        "first_name": row_data["first_name"],
        "last_name": row_data["last_name"],
        "display_name": row_data["display_name"],
        "organization": row_data["organization"],
        "job_title": row_data["job_title"],
        "role": row_data["role"],
        "auth_provider": row_data["auth_provider"],
        "last_login_at": row_data["last_login_at"],
        "profile_image_url": _profile_image_public_url(row),
    }


def _get_user_row(user_id: str) -> Any | None:
    if _auth_uses_sql():
        with get_db_session() as session:
            row = session.get(AppUserRecord, user_id)
            return _record_to_dict(row)

    with _db_connection() as connection:
        return connection.execute("SELECT * FROM app_users WHERE user_id = ?", (user_id,)).fetchone()


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    return _row_to_user(_get_user_row(user_id))


def _ensure_user_row(user_id: str) -> Any:
    row = _get_user_row(user_id)
    if row is None:
        raise ValueError("Authenticated user was not found.")
    return row


def _graph_token_expires_at(token_response: dict[str, Any], now: datetime) -> str | None:
    access_token = str(token_response.get("access_token") or "").strip()
    if not access_token:
        return None
    expires_in = int(token_response.get("expires_in") or 0)
    if expires_in <= 0:
        expires_in = 3600
    return _timestamp(now + timedelta(seconds=max(expires_in - 120, 60)))


def _create_session(user_id: str, user_agent: str = "", token_response: dict[str, Any] | None = None) -> str:
    session_token = secrets.token_urlsafe(48)
    now = _now()
    expires_at = now + timedelta(hours=AUTH_SESSION_TTL_HOURS)
    token_data = token_response or {}
    graph_access_token = str(token_data.get("access_token") or "").strip() or None
    graph_refresh_token = str(token_data.get("refresh_token") or "").strip() or None
    graph_token_expires_at = _graph_token_expires_at(token_data, now)
    if _auth_uses_sql():
        with get_db_session() as session:
            session.add(
                AuthSessionRecord(
                    session_token=session_token,
                    user_id=user_id,
                    created_at=_timestamp(now),
                    expires_at=_timestamp(expires_at),
                    last_seen_at=_timestamp(now),
                    user_agent=user_agent[:500],
                    graph_access_token=graph_access_token,
                    graph_refresh_token=graph_refresh_token,
                    graph_token_expires_at=graph_token_expires_at,
                )
            )
        return session_token

    with _db_connection() as connection:
        connection.execute(
            """
            INSERT INTO auth_sessions (
                session_token,
                user_id,
                created_at,
                expires_at,
                last_seen_at,
                user_agent,
                graph_access_token,
                graph_refresh_token,
                graph_token_expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_token,
                user_id,
                _timestamp(now),
                _timestamp(expires_at),
                _timestamp(now),
                user_agent[:500],
                graph_access_token,
                graph_refresh_token,
                graph_token_expires_at,
            ),
        )
        connection.commit()
    return session_token


def complete_entra_login(*, code: str, state_token: str, user_agent: str = "") -> tuple[dict[str, Any], str, str]:
    metadata = _get_metadata()
    state_row = _pop_state(state_token)
    if state_row is None:
        raise AuthenticationError("This sign-in session is missing or has expired. Please try again.")

    expires_at = datetime.fromisoformat(state_row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < _now():
        raise AuthenticationError("This sign-in session expired. Please try again.")

    token_endpoint = metadata.get("token_endpoint")
    if not token_endpoint:
        raise AuthConfigurationError("The Entra metadata document does not expose a token endpoint.")

    token_response = _fetch_json(
        token_endpoint,
        data={
            "grant_type": "authorization_code",
            "client_id": AUTH_ENTRA_CLIENT_ID,
            "client_secret": AUTH_ENTRA_CLIENT_SECRET,
            "code": code,
            "redirect_uri": AUTH_ENTRA_REDIRECT_URI,
            "scope": _entra_login_scopes(),
        },
    )

    id_token = str(token_response.get("id_token") or "").strip()
    if not id_token:
        raise AuthenticationError("The Entra token response did not include an ID token.")

    claims = _decode_jwt_payload(id_token)
    if str(claims.get("aud") or "") != AUTH_ENTRA_CLIENT_ID:
        raise AuthenticationError("The Entra ID token audience does not match this application.")
    if str(claims.get("nonce") or "") != str(state_row["nonce"]):
        raise AuthenticationError("The Entra ID token nonce did not match the sign-in request.")

    exp = int(claims.get("exp") or 0)
    if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < _now():
        raise AuthenticationError("The Entra ID token is expired.")

    user = _upsert_app_user(claims)
    session_token = _create_session(user["user_id"], user_agent=user_agent, token_response=token_response)
    return user, session_token, state_row["next_path"]


def get_logout_redirect_url() -> str:
    if not AUTH_ENABLED:
        return f"{AUTH_FRONTEND_BASE_URL}/login"

    try:
        metadata = _get_metadata()
    except AuthConfigurationError:
        return AUTH_ENTRA_POST_LOGOUT_REDIRECT_URI

    endpoint = str(metadata.get("end_session_endpoint") or "").strip()
    if not endpoint:
        return AUTH_ENTRA_POST_LOGOUT_REDIRECT_URI

    params = {"post_logout_redirect_uri": AUTH_ENTRA_POST_LOGOUT_REDIRECT_URI}
    return f"{endpoint}?{urllib.parse.urlencode(params)}"


def clear_session(session_token: str | None) -> None:
    if not session_token:
        return
    if _auth_uses_sql():
        with get_db_session() as session:
            record = session.get(AuthSessionRecord, session_token)
            if record:
                session.delete(record)
        return

    with _db_connection() as connection:
        connection.execute("DELETE FROM auth_sessions WHERE session_token = ?", (session_token,))
        connection.commit()


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _refresh_graph_token(refresh_token: str) -> dict[str, Any]:
    metadata = _get_metadata()
    token_endpoint = metadata.get("token_endpoint")
    if not token_endpoint:
        raise AuthConfigurationError("The Entra metadata document does not expose a token endpoint.")

    return _fetch_json(
        token_endpoint,
        data={
            "grant_type": "refresh_token",
            "client_id": AUTH_ENTRA_CLIENT_ID,
            "client_secret": AUTH_ENTRA_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "scope": _entra_login_scopes(),
        },
    )


def get_graph_access_token_for_request(request: Request) -> str:
    if not AUTH_ENABLED:
        raise AuthenticationError("Microsoft 365 ingestion requires Entra authentication to be enabled.")

    session_token = request.cookies.get(AUTH_SESSION_COOKIE_NAME)
    if not session_token:
        raise AuthenticationError("Authentication required.")

    if _auth_uses_sql():
        with get_db_session() as session:
            record = session.get(AuthSessionRecord, session_token)
            if record is None:
                raise AuthenticationError("Authentication required.")

            expires_at = _parse_timestamp(record.expires_at)
            if expires_at and expires_at < _now():
                session.delete(record)
                raise AuthenticationError("This session expired. Please sign in again.")

            token_expires_at = _parse_timestamp(record.graph_token_expires_at)
            if record.graph_access_token and token_expires_at and token_expires_at > _now():
                return record.graph_access_token

            if not record.graph_refresh_token:
                raise AuthenticationError("Microsoft 365 access was not granted. Please sign out and sign in again.")

            token_response = _refresh_graph_token(record.graph_refresh_token)
            access_token = str(token_response.get("access_token") or "").strip()
            if not access_token:
                raise AuthenticationError("Microsoft 365 token refresh failed.")
            record.graph_access_token = access_token
            record.graph_refresh_token = str(token_response.get("refresh_token") or "").strip() or record.graph_refresh_token
            record.graph_token_expires_at = _graph_token_expires_at(token_response, _now())
            return access_token

    with _db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM auth_sessions WHERE session_token = ?",
            (session_token,),
        ).fetchone()
        if row is None:
            raise AuthenticationError("Authentication required.")

        expires_at = _parse_timestamp(row["expires_at"])
        if expires_at and expires_at < _now():
            connection.execute("DELETE FROM auth_sessions WHERE session_token = ?", (session_token,))
            connection.commit()
            raise AuthenticationError("This session expired. Please sign in again.")

        token_expires_at = _parse_timestamp(row["graph_token_expires_at"])
        if row["graph_access_token"] and token_expires_at and token_expires_at > _now():
            return row["graph_access_token"]

        refresh_token = str(row["graph_refresh_token"] or "").strip()
        if not refresh_token:
            raise AuthenticationError("Microsoft 365 access was not granted. Please sign out and sign in again.")

        token_response = _refresh_graph_token(refresh_token)
        access_token = str(token_response.get("access_token") or "").strip()
        if not access_token:
            raise AuthenticationError("Microsoft 365 token refresh failed.")
        refreshed_refresh_token = str(token_response.get("refresh_token") or "").strip() or refresh_token
        connection.execute(
            """
            UPDATE auth_sessions
            SET graph_access_token = ?,
                graph_refresh_token = ?,
                graph_token_expires_at = ?
            WHERE session_token = ?
            """,
            (
                access_token,
                refreshed_refresh_token,
                _graph_token_expires_at(token_response, _now()),
                session_token,
            ),
        )
        connection.commit()
        return access_token


def get_authenticated_user(request: Request) -> dict[str, Any] | None:
    if not AUTH_ENABLED:
        return _demo_user()

    session_token = request.cookies.get(AUTH_SESSION_COOKIE_NAME)
    if not session_token:
        return None

    purge_expired_auth_records_best_effort()
    if _auth_uses_sql():
        with get_db_session() as session:
            record = session.execute(
                select(AuthSessionRecord, AppUserRecord)
                .join(AppUserRecord, AppUserRecord.user_id == AuthSessionRecord.user_id)
                .where(AuthSessionRecord.session_token == session_token)
            ).first()
            if record is None:
                return None

            session_record, user_record = record
            expires_at = datetime.fromisoformat(session_record.expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < _now():
                session.delete(session_record)
                return None

            session_record.last_seen_at = _timestamp()
            return _row_to_user(user_record)

    with _db_connection() as connection:
        row = connection.execute(
            """
            SELECT u.*, s.expires_at
            FROM auth_sessions s
            JOIN app_users u ON u.user_id = s.user_id
            WHERE s.session_token = ?
            """,
            (session_token,),
        ).fetchone()
        if row is None:
            return None

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < _now():
            connection.execute("DELETE FROM auth_sessions WHERE session_token = ?", (session_token,))
            connection.commit()
            return None

        connection.execute(
            "UPDATE auth_sessions SET last_seen_at = ? WHERE session_token = ?",
            (_timestamp(), session_token),
        )
        connection.commit()
        return _row_to_user(row)


async def require_authenticated_user(request: Request) -> dict[str, Any]:
    user = get_authenticated_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def user_is_manager(user: dict[str, Any] | None) -> bool:
    return str((user or {}).get("role") or "").strip().lower() == "manager"


async def require_manager_user(request: Request) -> dict[str, Any]:
    user = await require_authenticated_user(request)
    if not user_is_manager(user):
        raise HTTPException(status_code=403, detail="Manager role required.")
    return user


def update_my_profile(user_id: str, *, organization: str | None = None, job_title: str | None = None) -> dict[str, Any]:
    if _auth_uses_sql():
        with get_db_session() as session:
            row = session.get(AppUserRecord, user_id)
            if row is None:
                raise ValueError("Authenticated user was not found.")
            row.organization = ((organization if organization is not None else row.organization) or "").strip()
            row.job_title = ((job_title if job_title is not None else row.job_title) or "").strip()
            row.updated_at = _timestamp()
            session.flush()
            return _row_to_user(row)

    with _db_connection() as connection:
        row = _ensure_user_row(user_id)

        current_organization = organization if organization is not None else row["organization"]
        current_job_title = job_title if job_title is not None else row["job_title"]

        connection.execute(
            """
            UPDATE app_users
            SET organization = ?, job_title = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (
                (current_organization or "").strip(),
                (current_job_title or "").strip(),
                _timestamp(),
                user_id,
            ),
        )
        connection.commit()
        updated = connection.execute("SELECT * FROM app_users WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_user(updated)


def save_my_profile_image(user_id: str, *, content: bytes, original_filename: str | None = None) -> dict[str, Any]:
    if not content:
        raise ValueError("Profile image file is empty.")
    if len(content) > _MAX_AVATAR_BYTES:
        raise ValueError("Profile image must be 2 MB or smaller.")

    detected_type = imghdr.what(None, h=content)
    extension = _ALLOWED_AVATAR_IMAGE_TYPES.get(detected_type or "")
    if not extension:
        raise ValueError("Unsupported image format. Please upload a PNG, JPG, or WEBP file.")

    existing = _ensure_user_row(user_id)
    existing_data = _record_to_dict(existing) or {}
    _delete_profile_image(existing_data.get("profile_image_path"))

    safe_stem = f"{user_id}_{secrets.token_hex(8)}"
    relative_name = f"{safe_stem}{extension}"
    profile_image_path = relative_name
    if _profile_images_use_blob_storage():
        blob_name = f"{user_id}/{relative_name}"
        upload_blob(
            AZURE_STORAGE_CONTAINER_PROFILE_IMAGES,
            blob_name,
            content,
            content_type=_AVATAR_CONTENT_TYPES.get(extension),
        )
        profile_image_path = f"blob:{blob_name}"
    else:
        destination = _profile_image_absolute_path(relative_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

    if _auth_uses_sql():
        with get_db_session() as session:
            row = session.get(AppUserRecord, user_id)
            if row is None:
                raise ValueError("Authenticated user was not found.")
            row.profile_image_path = profile_image_path
            row.updated_at = _timestamp()
            session.flush()
            return _row_to_user(row)

    with _db_connection() as connection:
        connection.execute(
            """
            UPDATE app_users
            SET profile_image_path = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (
                profile_image_path,
                _timestamp(),
                user_id,
            ),
        )
        connection.commit()
        updated = connection.execute("SELECT * FROM app_users WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_user(updated)


def delete_my_profile_image(user_id: str) -> dict[str, Any]:
    existing = _ensure_user_row(user_id)
    existing_data = _record_to_dict(existing) or {}
    _delete_profile_image(existing_data.get("profile_image_path"))

    if _auth_uses_sql():
        with get_db_session() as session:
            row = session.get(AppUserRecord, user_id)
            if row is None:
                raise ValueError("Authenticated user was not found.")
            row.profile_image_path = None
            row.updated_at = _timestamp()
            session.flush()
            return _row_to_user(row)

    with _db_connection() as connection:
        connection.execute(
            """
            UPDATE app_users
            SET profile_image_path = NULL, updated_at = ?
            WHERE user_id = ?
            """,
            (
                _timestamp(),
                user_id,
            ),
        )
        connection.commit()
        updated = connection.execute("SELECT * FROM app_users WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_user(updated)
