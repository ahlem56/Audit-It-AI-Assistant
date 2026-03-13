from azure.storage.blob import BlobServiceClient
from app.config.settings import (
    AZURE_STORAGE_CONNECTION_STRING,
    AZURE_STORAGE_CONTAINER_RAW,
)

blob_service_client = BlobServiceClient.from_connection_string(
    AZURE_STORAGE_CONNECTION_STRING
)

def upload_file(filename: str, data: bytes):
    blob_client = blob_service_client.get_blob_client(
        container=AZURE_STORAGE_CONTAINER_RAW,
        blob=filename
    )
    blob_client.upload_blob(data, overwrite=True)