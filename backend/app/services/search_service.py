from __future__ import annotations

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

from app.config.settings import AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX, AZURE_SEARCH_KEY

search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY),
)


def upload_documents_to_index(documents: list):
    return search_client.upload_documents(documents=documents)
