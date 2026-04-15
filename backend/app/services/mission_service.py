from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models.audit_input import StructuredAuditInput
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
    }


def _audit_stats(audit_input: StructuredAuditInput) -> dict[str, int]:
    observations = audit_input.observations or []
    applications = {
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
        "applications_count": len(applications or set(audit_input.mission.applications or [])),
        "control_ids_count": len(control_ids),
    }


def create_mission(payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("Mission name is required.")

    mission_id = _normalize_mission_id(payload.get("mission_id"), name)
    if mission_exists(mission_id):
        raise ValueError(f"Mission '{mission_id}' already exists.")

    ensure_mission_dir(mission_id)
    mission = _default_mission_payload(
        mission_id=mission_id,
        name=name,
        client_name=(payload.get("client_name") or "").strip(),
        fiscal_year=(payload.get("fiscal_year") or "").strip(),
        status=(payload.get("status") or "Draft").strip() or "Draft",
    )
    _write_json(_mission_path(mission_id), mission)
    return mission


def get_all_missions() -> list[dict]:
    missions: list[dict] = []
    for mission_id in list_mission_ids():
        mission = get_mission(mission_id)
        if mission:
            missions.append(mission)
    missions.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return missions


def get_mission(mission_id: str) -> dict | None:
    path = _mission_path(mission_id)
    if not path.exists():
        return None
    return _read_json(path)


def update_mission(mission_id: str, payload: dict) -> dict:
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission '{mission_id}' was not found.")

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
    }
    for key, value in payload.items():
        if key in editable_fields and value is not None:
            mission[key] = value

    mission["updated_at"] = _timestamp()
    _write_json(_mission_path(mission_id), mission)
    return mission


def delete_mission(mission_id: str) -> dict:
    mission_path = _mission_dir(mission_id)
    if not mission_path.is_dir() or not _mission_path(mission_id).exists():
        raise ValueError(f"Mission '{mission_id}' was not found.")

    resolved_target = mission_path.resolve()
    resolved_root = MISSIONS_DIR.resolve()
    if resolved_target.parent != resolved_root:
        raise ValueError(f"Mission '{mission_id}' could not be deleted safely.")

    shutil.rmtree(resolved_target)
    return {"deleted": mission_id}


def save_mission_audit_input(mission_id: str, audit_input: StructuredAuditInput, uploaded_file_name: str | None = None) -> dict:
    mission = get_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission '{mission_id}' was not found.")

    ensure_mission_dir(mission_id)
    _audit_input_path(mission_id).write_text(
        audit_input.model_dump_json(indent=2),
        encoding="utf-8",
    )

    stats = _audit_stats(audit_input)
    updated_fields = {
        **stats,
        "uploaded_file_name": uploaded_file_name or mission.get("uploaded_file_name"),
        "parsing_status": "parsed",
    }
    if stats["observations_count"] > 0 and mission.get("status") == "Draft":
        updated_fields["status"] = "Ready"

    return update_mission(mission_id, updated_fields)


def load_mission_audit_input(mission_id: str) -> StructuredAuditInput | None:
    path = _audit_input_path(mission_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return StructuredAuditInput.model_validate(payload)


def load_mission_report_cache(mission_id: str) -> dict | None:
    path = _report_cache_path(mission_id)
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    result = payload.get("result")
    return result if isinstance(result, dict) else None


def save_mission_report_cache(mission_id: str, result: dict) -> dict:
    mission = get_mission(mission_id)
    if mission is None:
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
    return result
