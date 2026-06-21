from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config.settings import AUTH_ENABLED
from app.models.audit_input import StructuredAuditInput
from app.services.auth_service import get_user_by_id
from app.services.notification_service import create_notifications, mission_recipients
from app.services.security_audit_service import log_security_event
from app.services.sql_storage_service import (
    azure_sql_enabled,
    create_mission as create_sql_mission,
    delete_mission as delete_sql_mission,
    get_mission as get_sql_mission,
    load_audit_input as load_sql_audit_input,
    load_latest_report_version,
    list_missions as list_sql_missions,
    save_report_version,
    sync_observations,
    update_mission as update_sql_mission,
)
from app.utils.file_naming import slugify

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
MISSIONS_DIR = DATA_DIR / "missions"


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _mission_dir(mission_id: str) -> Path:
    return MISSIONS_DIR / mission_id


def _mission_path(mission_id: str) -> Path:
    return _mission_dir(mission_id) / "mission.json"


def _audit_input_path(mission_id: str) -> Path:
    return _mission_dir(mission_id) / "audit_input.json"


def _report_cache_path(mission_id: str) -> Path:
    return _mission_dir(mission_id) / "report_cache.json"


def ensure_mission_dir(mission_id: str) -> Path:
    path = _mission_dir(mission_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def mission_exists(mission_id: str) -> bool:
    return _mission_path(mission_id).exists()


def list_mission_ids() -> list[str]:
    if not MISSIONS_DIR.exists():
        return []
    return sorted(path.name for path in MISSIONS_DIR.iterdir() if path.is_dir())


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_mission_id(mission_id: Optional[str], name: str) -> str:
    value = slugify(mission_id or name, max_length=80)
    return value or f"mission_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _default_mission_payload(*, mission_id: str, name: str, client_name: str = "", fiscal_year: str = "", status: str = "Draft") -> dict:
    now = _timestamp()
    return {
        "mission_id": mission_id,
        "name": name,
        "client_name": client_name,
        "fiscal_year": fiscal_year,
        "status": status,
        "created_at": now,
        "updated_at": now,
        "uploaded_file_name": None,
        "parsing_status": "not_uploaded",
        "observations_count": 0,
        "applications_count": 0,
        "control_ids_count": 0,
        "report_generated_at": None,
        "exported_at": None,
        "owner_user_id": "",
        "owner_email": "",
        "invited_auditor_emails": [],
    }


def _load_mission_record(mission_id: str) -> dict | None:
    path = _mission_path(mission_id)
    if not path.exists():
        return None
    return _read_json(path)


def _recover_mission_record_from_audit_input(
    mission_id: str,
    *,
    owner_user: dict[str, Any] | None = None,
) -> dict | None:
    path = _audit_input_path(mission_id)
    if not path.exists():
        return None

    try:
        audit_input = StructuredAuditInput.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return None

    mission_info = audit_input.mission
    recovered = _default_mission_payload(
        mission_id=mission_id,
        name=mission_info.titre_mission or mission_id,
        client_name=mission_info.entite_auditee or "",
        fiscal_year=mission_info.periode or "",
        status="Ready" if audit_input.observations else "Draft",
    )
    recovered.update(_audit_stats(audit_input))
    recovered.update(get_mission_owner_fields(owner_user))
    recovered["parsing_status"] = "parsed"
    recovered["audit_input_json"] = audit_input.model_dump_json()
    recovered["audit_input_cache_key"] = _audit_input_cache_key(audit_input)
    _write_json(_mission_path(mission_id), recovered)
    return recovered


def _audit_stats(audit_input: StructuredAuditInput) -> dict[str, int]:
    observations = audit_input.observations or []
    scoped_applications = {
        application.strip()
        for application in audit_input.mission.applications or []
        if application.strip()
    }
    observation_applications = {
        (observation.application or "").strip()
        for observation in observations
        if (observation.application or "").strip()
    }
    control_ids = {
        (observation.controle_ref or "").strip()
        for observation in observations
        if (observation.controle_ref or "").strip()
    }
    return {
        "observations_count": len(observations),
        "applications_count": len(scoped_applications or observation_applications),
        "control_ids_count": len(control_ids),
    }


def _observation_ids(audit_input: StructuredAuditInput | None) -> set[str]:
    if audit_input is None:
        return set()
    return {
        str(observation.observation_id or "").strip()
        for observation in audit_input.observations or []
        if str(observation.observation_id or "").strip()
    }


def _count_validated_observations(audit_input: StructuredAuditInput | None) -> tuple[int, int]:
    if audit_input is None:
        return 0, 0

    observations = audit_input.observations or []
    validated_count = sum(
        1
        for observation in observations
        if str(observation.statut_validation or "").strip().lower() == "validated"
    )
    return validated_count, len(observations)


def _audit_input_cache_key(audit_input: StructuredAuditInput | None) -> str:
    if audit_input is None:
        return "sql-audit:"
    payload = audit_input.model_dump_json()
    return f"sql-audit:{hashlib.sha1(payload.encode('utf-8')).hexdigest()}"


def _load_report_cache_metadata(mission_id: str) -> dict | None:
    path = _report_cache_path(mission_id)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    result = payload.get("result")
    cached_input_mtime = payload.get("audit_input_mtime_ns")
    if result is None:
        return None

    return {
        "cached_at": payload.get("cached_at"),
        "audit_input_mtime_ns": cached_input_mtime,
    }


def _has_current_report_cache(mission_id: str) -> bool:
    audit_input_path = _audit_input_path(mission_id)
    cache_metadata = _load_report_cache_metadata(mission_id)
    if cache_metadata is None:
        return False
    if not audit_input_path.exists():
        return False
    return cache_metadata.get("audit_input_mtime_ns") == audit_input_path.stat().st_mtime_ns


def _build_mission_workflow(mission: dict) -> dict:
    mission_id = mission["mission_id"]
    audit_input = load_mission_audit_input(
        mission_id,
        user_id=str(mission.get("owner_user_id") or "").strip() or None,
    )
    validated_count, total_observations = _count_validated_observations(audit_input)
    has_observations = (mission.get("observations_count") or 0) > 0
    all_observations_validated = total_observations > 0 and validated_count == total_observations
    report_generated = _has_current_report_cache(mission_id)
    exported_at = mission.get("exported_at")
    has_parsed_source_data = (
        str(mission.get("parsing_status") or "").strip().lower() == "parsed"
        and audit_input is not None
        and has_observations
    )
    # Workflow milestones are monotonic: durable parsed data or a completed
    # downstream deliverable proves that the source-data step already occurred.
    has_uploaded_workbook = bool(
        mission.get("uploaded_file_name")
        or has_parsed_source_data
        or all_observations_validated
        or report_generated
        or exported_at
    )

    step_states = [
        {
            "key": "mission_created",
            "label": "Create mission",
            "state": "completed",
            "status_label": "Completed",
            "description": "Mission workspace is created and ready for source documents.",
        },
        {
            "key": "workbook_uploaded",
            "label": "Upload Excel",
            "state": "completed" if has_uploaded_workbook else "in_progress",
            "status_label": "Completed" if has_uploaded_workbook else "In progress",
            "description": (
                "Workbook uploaded and parsed successfully."
                if has_uploaded_workbook
                else "Upload the ITGC workbook to populate the mission data."
            ),
        },
        {
            "key": "observations_validated",
            "label": "Validate observations",
            "state": (
                "completed"
                if all_observations_validated
                else "in_progress"
                if has_uploaded_workbook and has_observations
                else "coming_next"
            ),
            "status_label": (
                "Completed"
                if all_observations_validated
                else "In progress"
                if has_uploaded_workbook and has_observations
                else "Coming next"
            ),
            "description": (
                f"{validated_count} of {total_observations} observations validated."
                if has_uploaded_workbook and has_observations
                else "Validation starts once observations are loaded from the workbook."
            ),
        },
        {
            "key": "report_generated",
            "label": "Generate report",
            "state": (
                "completed"
                if report_generated
                else "in_progress"
                if has_uploaded_workbook and has_observations
                else "coming_next"
            ),
            "status_label": (
                "Completed"
                if report_generated
                else "In progress"
                if has_uploaded_workbook and has_observations
                else "Coming next"
            ),
            "description": (
                "A fresh report draft is available for review."
                if report_generated
                else "Generate or refresh the report draft after reviewing observations."
                if has_uploaded_workbook and has_observations
                else "Report generation becomes available after observations are ready."
            ),
        },
        {
            "key": "pptx_exported",
            "label": "Export PPTX",
            "state": (
                "completed"
                if exported_at
                else "in_progress"
                if report_generated
                else "coming_next"
            ),
            "status_label": (
                "Completed" if exported_at else "In progress" if report_generated else "Coming next"
            ),
            "description": (
                f"PPTX exported on {exported_at}."
                if exported_at
                else "Export the PowerPoint once the report draft is approved."
                if report_generated
                else "PPTX export unlocks after generating the report."
            ),
        },
    ]

    if not has_uploaded_workbook:
        next_best_action = "Upload the ITGC workbook to populate observations and unlock the review workflow."
    elif not has_observations:
        next_best_action = "The workbook is present, but usable observations are not loaded yet. Review the parsing results and retry if needed."
    elif not all_observations_validated:
        next_best_action = "Validate the observations so the report draft can reflect the latest auditor review."
    elif not report_generated:
        next_best_action = "Generate the report draft to prepare the final deliverable."
    elif not exported_at:
        next_best_action = "Export the PPTX once the report draft is approved."
    else:
        next_best_action = "The mission workflow is complete. You can export again anytime if a refreshed deck is needed."

    return {
        "steps": step_states,
        "next_best_action": next_best_action,
        "validated_observations_count": validated_count,
        "total_observations_count": total_observations,
        "report_generated": report_generated,
        "exported_at": exported_at,
    }


def _enrich_mission(mission: dict) -> dict:
    enriched = dict(mission)
    enriched["invited_auditor_emails"] = _normalize_invited_emails(enriched.get("invited_auditor_emails"))
    audit_input = load_mission_audit_input(
        str(enriched.get("mission_id") or ""),
        user_id=str(enriched.get("owner_user_id") or "").strip() or None,
    )
    if audit_input is not None:
        enriched.update(_audit_stats(audit_input))
    enriched["workflow"] = _build_mission_workflow(mission)
    return enriched


def _normalize_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def _normalize_invited_emails(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        email = _normalize_email(str(item))
        if email and email not in seen:
            seen.add(email)
            result.append(email)
    return result


def _user_role(user: dict[str, Any] | None = None, user_role: str | None = None) -> str:
    return str((user or {}).get("role") or user_role or "").strip().lower()


def _user_email(user: dict[str, Any] | None = None, user_email: str | None = None) -> str:
    return _normalize_email(str((user or {}).get("email") or user_email or ""))


def _user_id(user: dict[str, Any] | None = None, user_id: str | None = None) -> str:
    return str((user or {}).get("user_id") or user_id or "").strip()


def _mission_owned_by(mission: dict, user_id: str | None) -> bool:
    if not AUTH_ENABLED:
        # In local demo mode, treat the workspace as single-user and expose
        # existing missions regardless of the recorded owner metadata.
        return True
    owner_user_id = str(mission.get("owner_user_id") or "").strip()
    return bool(user_id) and owner_user_id == user_id


def _mission_accessible_by(
    mission: dict,
    *,
    user: dict[str, Any] | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
) -> bool:
    if not AUTH_ENABLED:
        return True
    if user is None and user_id and (not user_email or not user_role):
        user = get_user_by_id(user_id)
    resolved_user_id = _user_id(user, user_id)
    if _mission_owned_by(mission, resolved_user_id):
        return True
    return bool(_user_email(user, user_email)) and _user_email(user, user_email) in _normalize_invited_emails(
        mission.get("invited_auditor_emails")
    )


def _mission_manageable_by(
    mission: dict,
    *,
    user: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> bool:
    if not AUTH_ENABLED:
        return True
    if user is None and user_id:
        user = get_user_by_id(user_id)
    return _user_role(user) == "manager" and _mission_owned_by(mission, _user_id(user, user_id))


def _mission_data_accessible_by(mission: dict, user_id: str | None) -> bool:
    if not AUTH_ENABLED:
        return True
    user = get_user_by_id(user_id) if user_id else None
    return _mission_accessible_by(mission, user=user, user_id=user_id)


def _adopt_mission_for_matching_email(mission_id: str, mission: dict, user_id: str | None) -> dict:
    if not AUTH_ENABLED or not user_id:
        return mission

    owner_user_id = str(mission.get("owner_user_id") or "").strip()
    if not owner_user_id or owner_user_id == user_id:
        return mission

    owner_email = _normalize_email(mission.get("owner_email"))
    if not owner_email:
        return mission

    user = get_user_by_id(user_id)
    user_email = _normalize_email(user.get("email") if user else "")
    if not user_email or user_email != owner_email:
        return mission

    updated = dict(mission)
    updated["owner_user_id"] = user_id
    updated["owner_email"] = user.get("email") or mission.get("owner_email") or ""
    updated["updated_at"] = _timestamp()
    _write_json(_mission_path(mission_id), updated)
    return updated


def get_mission_owner_fields(user: dict[str, Any] | None) -> dict[str, str]:
    if not user:
        return {"owner_user_id": "", "owner_email": ""}
    return {
        "owner_user_id": str(user.get("user_id") or "").strip(),
        "owner_email": str(user.get("email") or "").strip(),
    }


def user_can_manage_mission(mission_id: str, user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    mission = get_mission(mission_id, user=user)
    return bool(mission) and _mission_manageable_by(mission, user=user)


def create_mission(payload: dict, owner_user: dict[str, Any] | None = None) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("Mission name is required.")

    mission_id = _normalize_mission_id(payload.get("mission_id"), name)
    if azure_sql_enabled():
        existing = get_sql_mission(mission_id)
        if existing is not None:
            raise ValueError(f"Mission '{mission_id}' already exists.")
    elif mission_exists(mission_id):
        raise ValueError(f"Mission '{mission_id}' already exists.")

    mission = _default_mission_payload(
        mission_id=mission_id,
        name=name,
        client_name=(payload.get("client_name") or "").strip(),
        fiscal_year=(payload.get("fiscal_year") or "").strip(),
        status=(payload.get("status") or "Draft").strip() or "Draft",
    )
    mission.update(get_mission_owner_fields(owner_user))
    ensure_mission_dir(mission_id)
    _write_json(_mission_path(mission_id), mission)
    if azure_sql_enabled():
        create_sql_mission(mission)
    return _enrich_mission(mission)


def get_all_missions(
    *,
    user: dict[str, Any] | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
) -> list[dict]:
    if user is None and user_id and (not user_email or not user_role):
        user = get_user_by_id(user_id)
    resolved_user_id = _user_id(user, user_id) or None
    resolved_user_email = _user_email(user, user_email) or None
    resolved_user_role = _user_role(user, user_role) or None
    if azure_sql_enabled():
        missions = [
            _enrich_mission(mission)
            for mission in list_sql_missions(
                user_id=resolved_user_id,
                user_email=resolved_user_email,
                user_role=resolved_user_role,
            )
        ]
        missions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return missions
    missions: list[dict] = []
    for mission_id in list_mission_ids():
        mission = get_mission(
            mission_id,
            user=user,
            user_id=resolved_user_id,
            user_email=resolved_user_email,
            user_role=resolved_user_role,
        )
        if mission:
            missions.append(mission)
    missions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return missions


def get_mission(
    mission_id: str,
    *,
    user: dict[str, Any] | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
) -> dict | None:
    if user is None and user_id and (not user_email or not user_role):
        user = get_user_by_id(user_id)
    resolved_user_id = _user_id(user, user_id) or None
    resolved_user_email = _user_email(user, user_email) or None
    resolved_user_role = _user_role(user, user_role) or None
    if azure_sql_enabled():
        mission = get_sql_mission(
            mission_id,
            user_id=resolved_user_id,
            user_email=resolved_user_email,
            user_role=resolved_user_role,
        )
        return _enrich_mission(mission) if mission else None
    mission = _load_mission_record(mission_id) or _recover_mission_record_from_audit_input(
        mission_id,
        owner_user=user,
    )
    if mission is None:
        return None
    mission = _adopt_mission_for_matching_email(mission_id, mission, resolved_user_id)
    if not _mission_accessible_by(
        mission,
        user=user,
        user_id=resolved_user_id,
        user_email=resolved_user_email,
        user_role=resolved_user_role,
    ):
        return None
    return _enrich_mission(mission)


def update_mission(
    mission_id: str,
    payload: dict,
    *,
    user: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> dict:
    if user is None and user_id:
        user = get_user_by_id(user_id)
    resolved_user_id = _user_id(user, user_id) or None
    resolved_user_email = _user_email(user) or None
    resolved_user_role = _user_role(user) or None
    mission = (
        get_sql_mission(
            mission_id,
            user_id=resolved_user_id,
            user_email=resolved_user_email,
            user_role=resolved_user_role,
        )
        if azure_sql_enabled()
        else _load_mission_record(mission_id)
    )
    if mission is None:
        raise ValueError(f"Mission '{mission_id}' was not found.")
    if not azure_sql_enabled():
        mission = _adopt_mission_for_matching_email(mission_id, mission, resolved_user_id)
    if not _mission_accessible_by(
        mission,
        user=user,
        user_id=resolved_user_id,
        user_email=resolved_user_email,
        user_role=resolved_user_role,
    ):
        raise ValueError(f"Mission '{mission_id}' was not found.")

    previous_status = str(mission.get("status") or "").strip()
    editable_fields = {
        "name",
        "client_name",
        "fiscal_year",
        "status",
        "uploaded_file_name",
        "parsing_status",
        "observations_count",
        "applications_count",
        "control_ids_count",
        "report_generated_at",
        "exported_at",
        "owner_user_id",
        "owner_email",
        "invited_auditor_emails",
        "audit_input_json",
        "audit_input_cache_key",
    }
    nullable_fields = {"uploaded_file_name", "report_generated_at", "exported_at"}
    for key, value in payload.items():
        if key in editable_fields and (value is not None or key in nullable_fields):
            mission[key] = value
    mission["invited_auditor_emails"] = _normalize_invited_emails(mission.get("invited_auditor_emails"))

    mission["updated_at"] = _timestamp()
    if azure_sql_enabled():
        updated = update_sql_mission(mission_id, mission, user_id=resolved_user_id)
        if updated is None:
            raise ValueError(f"Mission '{mission_id}' was not found.")
        mission = updated
    else:
        _write_json(_mission_path(mission_id), mission)
    current_status = str(mission.get("status") or "").strip()
    status_changed_by_user = (
        "status" in payload
        and current_status
        and current_status != previous_status
        and "report_generated_at" not in payload
        and "exported_at" not in payload
        and "uploaded_file_name" not in payload
    )
    if status_changed_by_user:
        create_notifications(
            recipients=mission_recipients(mission),
            type="mission_status_changed",
            title="Mission status updated",
            message=f"Mission {mission.get('name') or mission_id} is now {current_status}.",
            mission_id=mission_id,
            related_entity_type="mission",
            related_entity_id=mission_id,
            actor=user,
        )
    return _enrich_mission(mission)


def invite_auditor_to_mission(mission_id: str, auditor_email: str, *, manager_user: dict[str, Any]) -> dict:
    if _user_role(manager_user) != "manager":
        raise PermissionError("Manager role required.")

    email = _normalize_email(auditor_email)
    if not email or "@" not in email:
        raise ValueError("A valid auditor email is required.")

    mission = _load_mission_record(mission_id)
    if azure_sql_enabled():
        mission = get_sql_mission(
            mission_id,
            user_id=_user_id(manager_user),
            user_email=_user_email(manager_user),
            user_role=_user_role(manager_user),
        )
    if mission is None:
        raise ValueError(f"Mission '{mission_id}' was not found.")
    if not _mission_manageable_by(mission, user=manager_user):
        raise PermissionError("Only the manager who created this mission can manage invitations.")

    invited = _normalize_invited_emails(mission.get("invited_auditor_emails"))
    was_already_invited = email in invited
    if email not in invited:
        invited.append(email)

    updated = update_mission(
        mission_id,
        {"invited_auditor_emails": invited},
        user=manager_user,
    )
    if not was_already_invited:
        create_notifications(
            recipients=[{"email": email}],
            type="mission_assigned",
            title="New audit mission assigned",
            message=f"You have been assigned to mission: {updated.get('name') or mission_id}.",
            mission_id=mission_id,
            related_entity_type="mission",
            related_entity_id=mission_id,
            actor=manager_user,
        )
    return updated


def delete_mission(mission_id: str, *, user: dict[str, Any] | None = None, user_id: str | None = None) -> dict:
    if user is None and user_id:
        user = get_user_by_id(user_id)
    resolved_user_id = _user_id(user, user_id) or None
    if azure_sql_enabled():
        mission = get_sql_mission(
            mission_id,
            user_id=resolved_user_id,
            user_email=_user_email(user) or None,
            user_role=_user_role(user) or None,
        )
        if mission is None:
            raise ValueError(f"Mission '{mission_id}' was not found.")
        if not _mission_manageable_by(mission, user=user, user_id=resolved_user_id):
            raise ValueError(f"Mission '{mission_id}' was not found.")
        delete_sql_mission(mission_id, user_id=resolved_user_id)
        mission_path = _mission_dir(mission_id)
        if mission_path.is_dir():
            resolved_target = mission_path.resolve()
            resolved_root = MISSIONS_DIR.resolve()
            if resolved_target.parent != resolved_root:
                raise ValueError(f"Mission '{mission_id}' could not be deleted safely.")
            shutil.rmtree(resolved_target)
        return {"deleted": mission_id}

    mission_path = _mission_dir(mission_id)
    if not mission_path.is_dir() or not _mission_path(mission_id).exists():
        raise ValueError(f"Mission '{mission_id}' was not found.")
    mission = _load_mission_record(mission_id)
    if mission is not None:
        mission = _adopt_mission_for_matching_email(mission_id, mission, resolved_user_id)
    if mission is None or not _mission_manageable_by(mission, user=user, user_id=resolved_user_id):
        raise ValueError(f"Mission '{mission_id}' was not found.")

    resolved_target = mission_path.resolve()
    resolved_root = MISSIONS_DIR.resolve()
    if resolved_target.parent != resolved_root:
        raise ValueError(f"Mission '{mission_id}' could not be deleted safely.")

    shutil.rmtree(resolved_target)
    return {"deleted": mission_id}


def save_mission_audit_input(
    mission_id: str,
    audit_input: StructuredAuditInput,
    uploaded_file_name: str | None = None,
    *,
    user_id: str | None = None,
) -> dict:
    if azure_sql_enabled():
        user = get_user_by_id(user_id) if user_id else None
        mission = get_sql_mission(
            mission_id,
            user_id=user_id,
            user_email=_user_email(user) or None,
            user_role=_user_role(user) or None,
        )
    else:
        mission = _load_mission_record(mission_id)
    if mission is not None and not azure_sql_enabled():
        mission = _adopt_mission_for_matching_email(mission_id, mission, user_id)
    if mission is None:
        raise ValueError(f"Mission '{mission_id}' was not found.")
    if not _mission_data_accessible_by(mission, user_id):
        raise ValueError(f"Mission '{mission_id}' was not found.")

    previous_audit_input = load_mission_audit_input(mission_id, user_id=user_id)
    previous_ids = _observation_ids(previous_audit_input)
    new_ids = _observation_ids(audit_input) - previous_ids

    ensure_mission_dir(mission_id)
    _audit_input_path(mission_id).write_text(
        audit_input.model_dump_json(indent=2),
        encoding="utf-8",
    )
    if azure_sql_enabled():
        sync_observations(mission_id, audit_input)
    report_cache_path = _report_cache_path(mission_id)
    if report_cache_path.exists():
        report_cache_path.unlink()

    stats = _audit_stats(audit_input)
    updated_fields = {
        **stats,
        "uploaded_file_name": uploaded_file_name or mission.get("uploaded_file_name"),
        "parsing_status": "parsed",
        "report_generated_at": None,
        "exported_at": None,
        "audit_input_json": audit_input.model_dump_json(),
        "audit_input_cache_key": _audit_input_cache_key(audit_input),
    }
    updated_fields["status"] = "Ready" if stats["observations_count"] > 0 else "Draft"

    updated_mission = update_mission(mission_id, updated_fields, user_id=user_id)
    if new_ids:
        actor = get_user_by_id(user_id) if user_id else None
        count = len(new_ids)
        plural = "s" if count != 1 else ""
        create_notifications(
            recipients=mission_recipients(updated_mission),
            type="observation_created",
            title="New observation added" if count == 1 else "New observations added",
            message=f"{count} new observation{plural} were added to mission {updated_mission.get('name') or mission_id}.",
            mission_id=mission_id,
            related_entity_type="observation",
            related_entity_id=",".join(sorted(new_ids)),
            actor=actor,
        )
    return updated_mission


def load_mission_audit_input(mission_id: str, *, user_id: str | None = None) -> StructuredAuditInput | None:
    mission = _load_mission_record(mission_id)
    if mission is not None:
        mission = _adopt_mission_for_matching_email(mission_id, mission, user_id)
    path = _audit_input_path(mission_id)
    local_access_allowed = mission is not None and (
        _mission_owned_by(mission, user_id) or _mission_data_accessible_by(mission, user_id)
    )
    if local_access_allowed and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return StructuredAuditInput.model_validate(payload)

    if azure_sql_enabled():
        user = get_user_by_id(user_id) if user_id else None
        return load_sql_audit_input(
            mission_id,
            user_id=user_id,
            user_email=_user_email(user) or None,
            user_role=_user_role(user) or None,
        )

    if not local_access_allowed:
        return None
    return None


def load_mission_report_cache(mission_id: str, *, user_id: str | None = None) -> dict | None:
    mission = _load_mission_record(mission_id)
    if mission is not None:
        mission = _adopt_mission_for_matching_email(mission_id, mission, user_id)
    if azure_sql_enabled():
        user = get_user_by_id(user_id) if user_id else None
        mission = get_sql_mission(
            mission_id,
            user_id=user_id,
            user_email=_user_email(user) or None,
            user_role=_user_role(user) or None,
        )
        if mission is None:
            return None
        result = load_latest_report_version(mission_id)
        if result is None:
            return None
        expected_mtime = str(mission.get("audit_input_cache_key") or "").strip()
        if not expected_mtime:
            expected_mtime = _audit_input_cache_key(load_mission_audit_input(mission_id, user_id=user_id))
        if result.get("audit_input_mtime_ns") != expected_mtime:
            return None
        return result

    if mission is None or not _mission_data_accessible_by(mission, user_id):
        return None
    path = _report_cache_path(mission_id)
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    result = payload.get("result")
    return result if isinstance(result, dict) else None


def save_mission_report_cache(mission_id: str, result: dict, *, user_id: str | None = None) -> dict:
    mission = _load_mission_record(mission_id)
    if mission is not None:
        mission = _adopt_mission_for_matching_email(mission_id, mission, user_id)

    if azure_sql_enabled():
        user = get_user_by_id(user_id) if user_id else None
        mission = get_sql_mission(
            mission_id,
            user_id=user_id,
            user_email=_user_email(user) or None,
            user_role=_user_role(user) or None,
        )
        if mission is None:
            raise ValueError(f"Mission '{mission_id}' was not found.")

        audit_input_mtime_ns = str(mission.get("audit_input_cache_key") or "").strip()
        if not audit_input_mtime_ns:
            audit_input_mtime_ns = _audit_input_cache_key(load_mission_audit_input(mission_id, user_id=user_id))
        payload = {
            "cached_at": _timestamp(),
            "audit_input_mtime_ns": audit_input_mtime_ns,
            "result": result,
        }
        quality_gate = result.get("structured_output", {}).get("quality_gate")
        save_report_version(
            mission_id,
            cached_at=payload["cached_at"],
            audit_input_mtime_ns=str(payload["audit_input_mtime_ns"]),
            structured_output=result.get("structured_output", {}),
            quality_gate=quality_gate if isinstance(quality_gate, dict) else None,
        )
        updated_mission = update_mission(
            mission_id,
            {
                "report_generated_at": payload["cached_at"],
                "status": "Ready",
            },
            user_id=user_id,
        )
        actor = get_user_by_id(user_id) if user_id else None
        create_notifications(
            recipients=mission_recipients(updated_mission),
            type="report_generated",
            title="Report draft ready",
            message=f"The report draft for mission {updated_mission.get('name') or mission_id} is ready for review.",
            mission_id=mission_id,
            related_entity_type="report",
            related_entity_id=mission_id,
            actor=actor,
        )
        log_security_event(
            action="REPORT_GENERATED",
            user=actor,
            mission_id=mission_id,
            resource_type="report",
            resource_id=mission_id,
            metadata={"cached_at": payload["cached_at"]},
        )
        return result

    if mission is None:
        raise ValueError(f"Mission '{mission_id}' was not found.")
    if not _mission_data_accessible_by(mission, user_id):
        raise ValueError(f"Mission '{mission_id}' was not found.")

    audit_input_path = _audit_input_path(mission_id)
    if not audit_input_path.exists():
        raise ValueError(f"Mission '{mission_id}' audit input was not found.")

    payload = {
        "cached_at": _timestamp(),
        "audit_input_mtime_ns": audit_input_path.stat().st_mtime_ns,
        "result": result,
    }
    _report_cache_path(mission_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    updated_mission = update_mission(
        mission_id,
        {
            "report_generated_at": payload["cached_at"],
            "status": "Ready",
        },
        user_id=user_id,
    )
    actor = get_user_by_id(user_id) if user_id else None
    create_notifications(
        recipients=mission_recipients(updated_mission),
        type="report_generated",
        title="Report draft ready",
        message=f"The report draft for mission {updated_mission.get('name') or mission_id} is ready for review.",
        mission_id=mission_id,
        related_entity_type="report",
        related_entity_id=mission_id,
        actor=actor,
    )
    log_security_event(
        action="REPORT_GENERATED",
        user=actor,
        mission_id=mission_id,
        resource_type="report",
        resource_id=mission_id,
        metadata={"cached_at": payload["cached_at"]},
    )
    if azure_sql_enabled():
        quality_gate = result.get("structured_output", {}).get("quality_gate")
        save_report_version(
            mission_id,
            cached_at=payload["cached_at"],
            audit_input_mtime_ns=str(payload["audit_input_mtime_ns"]),
            structured_output=result.get("structured_output", {}),
            quality_gate=quality_gate if isinstance(quality_gate, dict) else None,
        )
    return result
