from app.services.llm_clients import get_embeddings_client


def create_embedding(text: str):
    return get_embeddings_client().embed_query(text)
