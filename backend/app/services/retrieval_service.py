from __future__ import annotations

import logging

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.config.settings import AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX, AZURE_SEARCH_KEY
from app.services.embedding_service import create_embedding

logger = logging.getLogger(__name__)


def _search_configured() -> bool:
    return bool(AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_INDEX and AZURE_SEARCH_KEY)


def _get_search_client() -> SearchClient:
    if not _search_configured():
        raise RuntimeError("Azure AI Search is not configured.")
    return SearchClient(
        endpoint=AZURE_SEARCH_ENDPOINT,
        index_name=AZURE_SEARCH_INDEX,
        credential=AzureKeyCredential(AZURE_SEARCH_KEY),
    )


def retrieve_documents(query: str, top_k: int = 5, mission_id: str | None = None, *, allow_global: bool = False):
    if not mission_id and not allow_global:
        logger.warning("Blocked unscoped retrieval request. A mission_id is required for RAG access.")
        return []
    if not _search_configured():
        logger.warning("Azure AI Search is not configured. Returning no retrieval documents.")
        return []

    query_vector = create_embedding(query)
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k,
        fields="content_vector",
    )
    search_kwargs = {
        "search_text": query,
        "vector_queries": [vector_query],
        "top": top_k,
    }
    if mission_id:
        escaped_mission_id = mission_id.replace("'", "''")
        search_kwargs["filter"] = f"mission_id eq '{escaped_mission_id}'"

    try:
        results = _get_search_client().search(**search_kwargs)
    except Exception:
        if mission_id:
            logger.exception("Mission-scoped retrieval failed for mission_id=%s", mission_id)
            return []
        raise

    documents = []
    for result in results:
        documents.append(
            {
                "content": result.get("content", ""),
                "document_name": result.get("document_name", "unknown"),
                "chunk_id": result.get("chunk_id"),
                "score": result.get("@search.score"),
                "mission_id": result.get("mission_id"),
            }
        )
    return documents
