from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env")

from app.models.audit_input import StructuredAuditInput
from app.services.mission_service import list_mission_ids
from app.services.sql_storage_service import (
    _azure_sql_configured,
    azure_sql_enabled,
    create_feedback,
    create_mission,
    get_mission,
    init_azure_sql_storage,
    save_report_version,
    sync_observations,
    update_mission,
)

MISSIONS_DIR = ROOT_DIR / "app" / "data" / "missions"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _migrate_mission(mission_id: str) -> None:
    mission_dir = MISSIONS_DIR / mission_id
    mission_path = mission_dir / "mission.json"
    audit_input_path = mission_dir / "audit_input.json"
    feedbacks_path = mission_dir / "feedbacks.json"
    report_cache_path = mission_dir / "report_cache.json"

    if not mission_path.exists():
        return

    mission_payload = _read_json(mission_path)
    existing = get_mission(mission_id)
    if existing is None:
        create_mission(mission_payload)
    else:
        update_mission(mission_id, mission_payload)

    if audit_input_path.exists():
        audit_input = StructuredAuditInput.model_validate(_read_json(audit_input_path))
        sync_observations(mission_id, audit_input)

    if feedbacks_path.exists():
        feedbacks = _read_json(feedbacks_path)
        for feedback in feedbacks:
            create_feedback(feedback)

    if report_cache_path.exists() and audit_input_path.exists():
        report_cache = _read_json(report_cache_path)
        result = report_cache.get("result") or {}
        structured_output = result.get("structured_output") or {}
        quality_gate = structured_output.get("quality_gate")
        save_report_version(
            mission_id,
            cached_at=str(report_cache.get("cached_at") or mission_payload.get("updated_at")),
            audit_input_mtime_ns=str(report_cache.get("audit_input_mtime_ns") or audit_input_path.stat().st_mtime_ns),
            structured_output=structured_output,
            quality_gate=quality_gate if isinstance(quality_gate, dict) else None,
        )


def main() -> None:
    if not _azure_sql_configured():
        raise RuntimeError("Azure SQL is not configured in backend/.env.")

    init_azure_sql_storage()
    if not azure_sql_enabled():
        raise RuntimeError("Azure SQL initialization failed. Check backend logs and connection settings.")
    for mission_id in list_mission_ids():
        _migrate_mission(mission_id)
    print("Local mission data migration completed.")


if __name__ == "__main__":
    main()
