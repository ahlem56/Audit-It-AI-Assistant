from __future__ import annotations

import logging
import time
from io import BytesIO
from typing import Any

import requests

from app.agents.orchestrator_agent import route_request
from app.config.settings import WINDOWS_EXPORT_SERVICE_TIMEOUT_SECONDS, WINDOWS_EXPORT_SERVICE_URL
from app.models.export_models import ExportReportRequest
from app.services.word_export_service import build_report_docx

logger = logging.getLogger(__name__)


def _elapsed(started: float) -> float:
    return time.perf_counter() - started


def process_assistant_request(user_input: str, mission_id: str | None = None, *, user_id: str | None = None) -> dict[str, Any]:
    logger.info("Processing assistant request")
    return route_request(user_input, mission_id=mission_id, user_id=user_id)


def _build_export_with_windows_service(payload: ExportReportRequest, export_format: str, *, export_id: str | None = None) -> BytesIO:
    endpoint = f"{WINDOWS_EXPORT_SERVICE_URL}/export-{export_format}"
    started = time.perf_counter()
    logger.info("Report export timing [%s] Windows service request started format=%s endpoint=%s", export_id or "-", export_format, endpoint)
    try:
        response = requests.post(
            endpoint,
            json=payload.model_dump(mode="json"),
            headers={"X-Report-Export-Id": export_id} if export_id else None,
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
    logger.info(
        "Report export timing [%s] Windows service request completed in %.2fs format=%s bytes=%s",
        export_id or "-",
        _elapsed(started),
        export_format,
        len(response.content),
    )
    return output


def build_export_file(result: dict[str, Any], export_format: str = "pptx", *, export_id: str | None = None):
    total_started = time.perf_counter()
    validation_started = time.perf_counter()
    payload = ExportReportRequest.model_validate(result)
    logger.info("Report export timing [%s] export payload validated in %.2fs", export_id or "-", _elapsed(validation_started))
    normalized_format = export_format.strip().lower()
    if normalized_format == "docx":
        logger.info("Building DOCX export for generated report")
        output = build_report_docx(payload)
        logger.info("Report export timing DOCX export completed in %.2fs", _elapsed(total_started))
        return output

    if normalized_format in {"pptx", "pdf"}:
        if WINDOWS_EXPORT_SERVICE_URL:
            logger.info("Building %s export using Windows PowerPoint export service", normalized_format.upper())
            output = _build_export_with_windows_service(payload, normalized_format, export_id=export_id)
            logger.info("Report export timing [%s] %s export completed in %.2fs", export_id or "-", normalized_format.upper(), _elapsed(total_started))
            return output

        try:
            from app.services.export_service import build_report_pdf, build_report_pptx
        except Exception as exc:
            if normalized_format == "pptx":
                from app.services.docker_pptx_export_service import build_report_pptx_docker

                logger.info("Building Docker-compatible PPTX export for generated report")
                output = build_report_pptx_docker(payload)
                logger.info("Report export timing Docker-compatible PPTX export completed in %.2fs", _elapsed(total_started))
                return output
            raise RuntimeError(
                "PDF export requires Windows with Microsoft PowerPoint installed. "
                "Use PPTX or DOCX export in Docker/Linux deployments."
            ) from exc

        if normalized_format == "pdf":
            logger.info("Building PDF export for generated report")
            output = build_report_pdf(payload)
            logger.info("Report export timing PDF export completed in %.2fs", _elapsed(total_started))
            return output

        logger.info("Building PPTX export for generated report")
        output = build_report_pptx(payload)
        logger.info("Report export timing PPTX export completed in %.2fs", _elapsed(total_started))
        return output

    raise ValueError(f"Unsupported export format: {export_format}")
