from __future__ import annotations

import logging
import time

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.models.export_models import ExportReportRequest
from app.services.export_service import build_report_pdf, build_report_pptx

logger = logging.getLogger(__name__)

app = FastAPI(title="Audit IT Windows PowerPoint Export Service")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "renderer": "windows-powerpoint"}


async def _stream_export(payload: ExportReportRequest, export_format: str) -> StreamingResponse:
    started = time.perf_counter()
    logger.info("Windows PowerPoint %s export started", export_format.upper())
    try:
        builder = build_report_pdf if export_format == "pdf" else build_report_pptx
        file_stream = await run_in_threadpool(builder, payload)
    except Exception as exc:
        logger.exception("Windows PowerPoint %s export failed", export_format.upper())
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    elapsed = time.perf_counter() - started
    logger.info("Windows PowerPoint %s export finished in %.1fs", export_format.upper(), elapsed)

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
async def export_pptx(payload: ExportReportRequest) -> StreamingResponse:
    return await _stream_export(payload, "pptx")


@app.post("/export-pdf")
async def export_pdf(payload: ExportReportRequest) -> StreamingResponse:
    return await _stream_export(payload, "pdf")
