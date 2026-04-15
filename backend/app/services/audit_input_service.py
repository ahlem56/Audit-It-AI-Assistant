from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.models.audit_input import StructuredAuditInput

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
LATEST_AUDIT_INPUT_PATH = DATA_DIR / "latest_audit_input.json"


def save_latest_audit_input(audit_input: StructuredAuditInput) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_AUDIT_INPUT_PATH.write_text(
        audit_input.model_dump_json(indent=2),
        encoding="utf-8",
    )


def load_latest_audit_input() -> Optional[StructuredAuditInput]:
    if not LATEST_AUDIT_INPUT_PATH.exists():
        return None
    payload = json.loads(LATEST_AUDIT_INPUT_PATH.read_text(encoding="utf-8"))
    return StructuredAuditInput.model_validate(payload)
