from __future__ import annotations

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import SearchFieldDataType, SimpleField

from app.config.settings import AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX, AZURE_SEARCH_KEY


def _search_configured() -> bool:
    return bool(AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_INDEX and AZURE_SEARCH_KEY)


def _get_search_index_client() -> SearchIndexClient:
    if not _search_configured():
        raise RuntimeError("Azure AI Search is not configured.")
    return SearchIndexClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )


def _get_search_client() -> SearchClient:
    if not _search_configured():
        raise RuntimeError("Azure AI Search is not configured.")
    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )


def ensure_search_index_schema() -> None:
    search_index_client = _get_search_index_client()
    index = search_index_client.get_index(AZURE_SEARCH_INDEX)
    field_names = {field.name for field in index.fields}
    if "mission_id" in field_names:
        return

    index.fields.append(
        SimpleField(
            name="mission_id",
            type=SearchFieldDataType.String,
            filterable=True,
            sortable=False,
            facetable=False,
        )
    )
    search_index_client.create_or_update_index(index)


def upload_documents_to_index(documents: list):
    return _get_search_client().upload_documents(documents=documents)
