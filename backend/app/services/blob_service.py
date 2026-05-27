from __future__ import annotations

import logging

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import ContentSettings
from azure.storage.blob import BlobServiceClient

from app.config.settings import AZURE_STORAGE_CONNECTION_STRING, AZURE_STORAGE_CONTAINER_RAW

logger = logging.getLogger(__name__)


def _get_blob_service_client() -> BlobServiceClient:
    if not AZURE_STORAGE_CONNECTION_STRING:
        raise RuntimeError("Azure Blob Storage is not configured.")
    return BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)


def ensure_container_exists(container_name: str):
    blob_service_client = _get_blob_service_client()
    container_client = blob_service_client.get_container_client(container_name)
    try:
        container_client.create_container()
        logger.info("Created blob container '%s'", container_name)
    except ResourceExistsError:
        return container_client
    return container_client


def upload_file(filename: str, data: bytes):
    blob_service_client = _get_blob_service_client()
    ensure_container_exists(AZURE_STORAGE_CONTAINER_RAW)
    blob_client = blob_service_client.get_blob_client(
        container=AZURE_STORAGE_CONTAINER_RAW,
        blob=filename,
    )
    blob_client.upload_blob(data, overwrite=True)


def upload_blob(container_name: str, blob_name: str, data: bytes, *, content_type: str | None = None) -> None:
    blob_service_client = _get_blob_service_client()
    ensure_container_exists(container_name)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    kwargs = {"overwrite": True}
    if content_type:
        kwargs["content_settings"] = ContentSettings(content_type=content_type)
    blob_client.upload_blob(data, **kwargs)


def download_blob(container_name: str, blob_name: str) -> bytes:
    blob_service_client = _get_blob_service_client()
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    return blob_client.download_blob().readall()


def delete_blob(container_name: str, blob_name: str) -> None:
    blob_service_client = _get_blob_service_client()
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    try:
        blob_client.delete_blob()
    except ResourceNotFoundError:
        return
