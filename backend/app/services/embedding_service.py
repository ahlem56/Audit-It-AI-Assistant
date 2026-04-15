from app.services.llm_clients import get_embeddings_client

embeddings = get_embeddings_client()


def create_embedding(text: str):
    return embeddings.embed_query(text)
