from __future__ import annotations

import logging

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient

from app.config.settings import AZURE_STORAGE_CONNECTION_STRING, AZURE_STORAGE_CONTAINER_RAW

logger = logging.getLogger(__name__)

blob_service_client = BlobServiceClient.from_connection_string(
    AZURE_STORAGE_CONNECTION_STRING
)


def ensure_container_exists(container_name: str):
    container_client = blob_service_client.get_container_client(container_name)
    try:
        container_client.create_container()
        logger.info("Created blob container '%s'", container_name)
    except ResourceExistsError:
        return container_client
    return container_client


def upload_file(filename: str, data: bytes):
    ensure_container_exists(AZURE_STORAGE_CONTAINER_RAW)
    blob_client = blob_service_client.get_blob_client(
        container=AZURE_STORAGE_CONTAINER_RAW,
        blob=filename,
    )
    blob_client.upload_blob(data, overwrite=True)
