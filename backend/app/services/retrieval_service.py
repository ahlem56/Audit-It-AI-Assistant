from __future__ import annotations

import logging

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.config.settings import AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX, AZURE_SEARCH_KEY
from app.services.embedding_service import embeddings

logger = logging.getLogger(__name__)

search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY),
)


def retrieve_documents(query: str, top_k: int = 5, mission_id: str | None = None):
    query_vector = embeddings.embed_query(query)
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
        results = search_client.search(**search_kwargs)
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
