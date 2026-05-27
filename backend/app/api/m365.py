from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.upload import _process_uploaded_file
from app.services.auth_service import (
    AuthenticationError,
    AuthConfigurationError,
    get_graph_access_token_for_request,
    require_authenticated_user,
)
from app.services.graph_service import (
    GraphRequestError,
    download_drive_item,
    get_me,
    list_drive_children,
    list_my_drive_root,
)
from app.services.mission_service import get_mission, update_mission

router = APIRouter(prefix="/m365")
logger = logging.getLogger(__name__)


class M365IngestDriveItemRequest(BaseModel):
    mission_id: str = Field(..., min_length=1)
    drive_id: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)


def _graph_token_or_401(request: Request) -> str:
    try:
        return get_graph_access_token_for_request(request)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AuthConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/me")
async def microsoft_365_me(request: Request, user=Depends(require_authenticated_user)):
    access_token = _graph_token_or_401(request)
    try:
        return await run_in_threadpool(get_me, access_token)
    except GraphRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/my-drive/root")
async def microsoft_365_my_drive_root(request: Request, user=Depends(require_authenticated_user)):
    access_token = _graph_token_or_401(request)
    try:
        return await run_in_threadpool(list_my_drive_root, access_token)
    except GraphRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/drives/{drive_id}/items/{item_id}/children")
async def microsoft_365_drive_children(
    drive_id: str,
    item_id: str,
    request: Request,
    user=Depends(require_authenticated_user),
):
    access_token = _graph_token_or_401(request)
    try:
        return await run_in_threadpool(list_drive_children, access_token, drive_id, item_id)
    except GraphRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/drives/{drive_id}/items/{item_id}/content")
async def microsoft_365_drive_item_content(
    drive_id: str,
    item_id: str,
    request: Request,
    user=Depends(require_authenticated_user),
):
    access_token = _graph_token_or_401(request)
    try:
        content = await run_in_threadpool(download_drive_item, access_token, drive_id, item_id)
    except GraphRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=content, media_type="application/octet-stream")


@router.post("/ingest-drive-item")
async def microsoft_365_ingest_drive_item(
    payload: M365IngestDriveItemRequest,
    request: Request,
    user=Depends(require_authenticated_user),
):
    mission = await run_in_threadpool(get_mission, payload.mission_id, user_id=user["user_id"])
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found.")

    access_token = _graph_token_or_401(request)
    try:
        content = await run_in_threadpool(download_drive_item, access_token, payload.drive_id, payload.item_id)
        await run_in_threadpool(update_mission, payload.mission_id, {"parsing_status": "parsing"}, user_id=user["user_id"])
        return await run_in_threadpool(
            _process_uploaded_file,
            payload.filename,
            content,
            payload.mission_id,
            user["user_id"],
        )
    except ValueError as exc:
        try:
            await run_in_threadpool(update_mission, payload.mission_id, {"parsing_status": "error"}, user_id=user["user_id"])
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GraphRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Microsoft 365 ingestion failed")
        try:
            await run_in_threadpool(update_mission, payload.mission_id, {"parsing_status": "error"}, user_id=user["user_id"])
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Microsoft 365 ingestion failed: {exc}") from exc
