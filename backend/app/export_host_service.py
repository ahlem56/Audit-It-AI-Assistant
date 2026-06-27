from __future__ import annotations

import logging
import sys
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.models.export_models import ExportReportRequest
from app.services.export_service import build_report_pdf, build_report_pptx, set_report_export_id


def _configure_console_logging() -> None:
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        root_logger.addHandler(handler)

    root_logger.setLevel(logging.INFO)
    for handler in root_logger.handlers:
        handler.setLevel(logging.INFO)
    logging.getLogger("app").setLevel(logging.INFO)
    logging.getLogger("app.services.export_service").setLevel(logging.INFO)
    logging.getLogger("app.export_host_service").setLevel(logging.INFO)


_configure_console_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Audit IT Windows PowerPoint Export Service")
logger.info("Report export timing Windows PowerPoint export service logging is enabled")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "renderer": "windows-powerpoint"}


async def _stream_export(payload: ExportReportRequest, export_format: str, request: Request) -> StreamingResponse:
    export_id = request.headers.get("x-report-export-id") or "-"
    started = time.perf_counter()
    logger.info("Report export timing [%s] Windows PowerPoint service started format=%s", export_id, export_format.upper())
    try:
        builder = build_report_pdf if export_format == "pdf" else build_report_pptx
        build_started = time.perf_counter()
        set_report_export_id(export_id)
        file_stream = await run_in_threadpool(builder, payload)
        file_size = len(file_stream.getvalue()) if hasattr(file_stream, "getvalue") else None
        logger.info(
            "Report export timing [%s] Windows PowerPoint service build completed in %.2fs format=%s bytes=%s",
            export_id,
            time.perf_counter() - build_started,
            export_format.upper(),
            file_size,
        )
    except Exception as exc:
        logger.exception("Report export timing [%s] Windows PowerPoint service failed format=%s", export_id, export_format.upper())
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    elapsed = time.perf_counter() - started
    logger.info("Report export timing [%s] Windows PowerPoint service returning response in %.2fs format=%s", export_id, elapsed, export_format.upper())

    extension = "pdf" if export_format == "pdf" else "pptx"
    media_type = (
        "application/pdf"
        if export_format == "pdf"
        else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    return StreamingResponse(
        file_stream,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="audit-report.{extension}"'},
    )


@app.post("/export-pptx")
async def export_pptx(payload: ExportReportRequest, request: Request) -> StreamingResponse:
    return await _stream_export(payload, "pptx", request)


@app.post("/export-pdf")
async def export_pdf(payload: ExportReportRequest, request: Request) -> StreamingResponse:
    return await _stream_export(payload, "pdf", request)
