from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

import requests

from app.agents.orchestrator_agent import route_request
from app.config.settings import WINDOWS_EXPORT_SERVICE_TIMEOUT_SECONDS, WINDOWS_EXPORT_SERVICE_URL
from app.models.export_models import ExportReportRequest
from app.services.word_export_service import build_report_docx

logger = logging.getLogger(__name__)


def process_assistant_request(user_input: str, mission_id: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
    logger.info("Processing assistant request")
    return route_request(user_input, mission_id=mission_id, user_id=user_id)


def _build_export_with_windows_service(payload: ExportReportRequest, export_format: str) -> BytesIO:
    endpoint = f"{WINDOWS_EXPORT_SERVICE_URL}/export-{export_format}"
    try:
        response = requests.post(
            endpoint,
            json=payload.model_dump(mode="json"),
            timeout=WINDOWS_EXPORT_SERVICE_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        detail = ""
        response = getattr(exc, "response", None)
        if response is not None:
            try:
                detail = response.json().get("detail", "")
            except Exception:
                detail = response.text
        message = detail or str(exc)
        raise RuntimeError(
            "Windows PowerPoint export service is unavailable or failed. "
            "Start it on the Windows host, then retry. "
            f"Details: {message}"
        ) from exc

    output = BytesIO(response.content)
    output.seek(0)
    return output


def build_export_file(result: dict[str, Any], export_format: str = "pptx"):
    payload = ExportReportRequest.model_validate(result)
    normalized_format = export_format.strip().lower()
    if normalized_format == "docx":
        logger.info("Building DOCX export for generated report")
        return build_report_docx(payload)

    if normalized_format in {"pptx", "pdf"}:
        if WINDOWS_EXPORT_SERVICE_URL:
            logger.info("Building %s export using Windows PowerPoint export service", normalized_format.upper())
            return _build_export_with_windows_service(payload, normalized_format)

        try:
            from app.services.export_service import build_report_pdf, build_report_pptx
        except Exception as exc:
            if normalized_format == "pptx":
                from app.services.docker_pptx_export_service import build_report_pptx_docker

                logger.info("Building Docker-compatible PPTX export for generated report")
                return build_report_pptx_docker(payload)
            raise RuntimeError(
                "PDF export requires Windows with Microsoft PowerPoint installed. "
                "Use PPTX or DOCX export in Docker/Linux deployments."
            ) from exc

        if normalized_format == "pdf":
            logger.info("Building PDF export for generated report")
            return build_report_pdf(payload)

        logger.info("Building PPTX export for generated report")
        return build_report_pptx(payload)

    raise ValueError(f"Unsupported export format: {export_format}")
