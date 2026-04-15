from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.services.blob_service import upload_file
from app.services.audit_input_service import save_latest_audit_input
from app.services.indexing_service import prepare_documents_for_index
from app.services.mission_service import get_mission, save_mission_audit_input, update_mission
from app.services.rag_service import split_documents
from app.services.search_service import upload_documents_to_index
from app.utils.document_parser import load_document
from app.utils.structured_audit_parser import parse_audit_workbook

router = APIRouter()
logger = logging.getLogger(__name__)


def _process_uploaded_file(file_name: str, content: bytes, mission_id: str) -> dict:
    upload_file(file_name, content)

    suffix = Path(file_name).suffix
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name

        if suffix.lower() in {".xlsx", ".xlsm"}:
            structured_input = parse_audit_workbook(temp_file_path)
            save_mission_audit_input(mission_id, structured_input, uploaded_file_name=file_name)
            # Compatibility note: keep the legacy single-file snapshot for older flows until all clients migrate.
            save_latest_audit_input(structured_input)
        else:
            update_mission(
                mission_id,
                {
                    "uploaded_file_name": file_name,
                    "parsing_status": "parsed",
                },
            )

        docs = load_document(temp_file_path)
        chunks = split_documents(docs)
        indexed_docs = prepare_documents_for_index(chunks, file_name, mission_id)
        upload_documents_to_index(indexed_docs)

        return {
            "message": "Document uploaded and indexed successfully",
            "filename": file_name,
            "chunks_indexed": len(indexed_docs),
            "structured_observations": len(structured_input.observations) if suffix.lower() in {".xlsx", ".xlsm"} else None,
        }
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@router.post("/upload")
async def upload_document(
    mission_id: str,
    file: UploadFile = File(...),
):
    try:
        mission = await run_in_threadpool(get_mission, mission_id)
        if mission is None:
            raise HTTPException(status_code=404, detail="Mission not found.")
        content = await file.read()
        await run_in_threadpool(update_mission, mission_id, {"parsing_status": "parsing"})
        return await run_in_threadpool(_process_uploaded_file, file.filename, content, mission_id)
    except ValueError as exc:
        logger.warning("Unsupported upload rejected: %s", exc)
        try:
            await run_in_threadpool(update_mission, mission_id, {"parsing_status": "error"})
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Upload/indexing failed")
        try:
            await run_in_threadpool(update_mission, mission_id, {"parsing_status": "error"})
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Upload/indexing failed: {exc}",
        ) from exc
