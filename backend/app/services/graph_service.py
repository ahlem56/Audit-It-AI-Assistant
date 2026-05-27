from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.config.settings import GRAPH_BASE_URL


class GraphRequestError(RuntimeError):
    pass


def _graph_url(path: str) -> str:
    if path.startswith("https://"):
        return path
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{GRAPH_BASE_URL}{normalized_path}"


def graph_request(access_token: str, path: str, *, method: str = "GET", data: dict[str, Any] | None = None) -> bytes:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    payload = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(data).encode("utf-8")

    request = urllib.request.Request(_graph_url(path), data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GraphRequestError(f"Microsoft Graph request failed: {exc.code} {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise GraphRequestError(f"Microsoft Graph request failed: {exc.reason}") from exc


def download_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/octet-stream"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GraphRequestError(f"Microsoft Graph download failed: {exc.code} {detail or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise GraphRequestError(f"Microsoft Graph download failed: {exc.reason}") from exc


def graph_json(access_token: str, path: str, *, method: str = "GET", data: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = graph_request(access_token, path, method=method, data=data)
    return json.loads(raw.decode("utf-8"))


def get_me(access_token: str) -> dict[str, Any]:
    return graph_json(access_token, "/me?$select=id,displayName,userPrincipalName,mail")


def list_my_drive_root(access_token: str) -> dict[str, Any]:
    return graph_json(
        access_token,
        "/me/drive/root/children?$select=id,name,size,webUrl,file,folder,parentReference,lastModifiedDateTime",
    )


def list_drive_children(access_token: str, drive_id: str, item_id: str = "root") -> dict[str, Any]:
    safe_drive_id = urllib.parse.quote(drive_id, safe="")
    if item_id == "root":
        path = f"/drives/{safe_drive_id}/root/children"
    else:
        safe_item_id = urllib.parse.quote(item_id, safe="")
        path = f"/drives/{safe_drive_id}/items/{safe_item_id}/children"
    return graph_json(
        access_token,
        f"{path}?$select=id,name,size,webUrl,file,folder,parentReference,lastModifiedDateTime",
    )


def download_drive_item(access_token: str, drive_id: str, item_id: str) -> bytes:
    safe_drive_id = urllib.parse.quote(drive_id, safe="")
    safe_item_id = urllib.parse.quote(item_id, safe="")
    try:
        metadata = graph_json(access_token, f"/drives/{safe_drive_id}/items/{safe_item_id}")
    except GraphRequestError:
        metadata = graph_json(access_token, f"/me/drive/items/{safe_item_id}")
    download_url = str(metadata.get("@microsoft.graph.downloadUrl") or "").strip()
    if not download_url:
        try:
            return graph_request(access_token, f"/drives/{safe_drive_id}/items/{safe_item_id}/content")
        except GraphRequestError:
            return graph_request(access_token, f"/me/drive/items/{safe_item_id}/content")
    return download_bytes(download_url)
