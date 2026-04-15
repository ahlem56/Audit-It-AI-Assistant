from __future__ import annotations

import logging
from typing import Any

from app.agents.orchestrator_agent import route_request
from app.models.export_models import ExportReportRequest
from app.services.export_service import build_report_pptx

logger = logging.getLogger(__name__)


def process_assistant_request(user_input: str, mission_id: str | None = None) -> dict[str, Any]:
    logger.info("Processing assistant request")
    return route_request(user_input, mission_id=mission_id)


def build_export_file(result: dict[str, Any]):
    payload = ExportReportRequest.model_validate(result)
    logger.info("Building PPTX export for generated report")
    return build_report_pptx(payload)
