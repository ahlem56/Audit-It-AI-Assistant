from __future__ import annotations

import logging
from typing import Any

from app.agents.orchestrator_agent import route_request
from app.models.export_models import ExportReportRequest
from app.services.export_service import build_report_pdf, build_report_pptx
from app.services.word_export_service import build_report_docx

logger = logging.getLogger(__name__)


def process_assistant_request(user_input: str, mission_id: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
    logger.info("Processing assistant request")
    return route_request(user_input, mission_id=mission_id, user_id=user_id)


def build_export_file(result: dict[str, Any], export_format: str = "pptx"):
    payload = ExportReportRequest.model_validate(result)
    normalized_format = export_format.strip().lower()
    if normalized_format == "pdf":
        logger.info("Building PDF export for generated report")
        return build_report_pdf(payload)
    if normalized_format == "docx":
        logger.info("Building DOCX export for generated report")
        return build_report_docx(payload)

    logger.info("Building PPTX export for generated report")
    return build_report_pptx(payload)
