from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.models import VectorizedQuery

from app.config.settings import (
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX,
)
from app.services.embedding_service import embeddings

search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY)
)

def retrieve_documents(query: str, top_k: int = 5):
    query_vector = embeddings.embed_query(query)

    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k,
        fields="content_vector"
    )

    results = search_client.search(
        search_text="",
        vector_queries=[vector_query],
        top=top_k
    )

    documents = []

    for r in results:
        documents.append({
            "content": r.get("content", ""),
            "document_name": r.get("document_name", "unknown"),
            "chunk_id": r.get("chunk_id", None),
            "score": r.get("@search.score", None)
        })

    return documents