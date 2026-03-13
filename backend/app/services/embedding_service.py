from langchain_openai import AzureOpenAIEmbeddings
from app.config.settings import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_API_VERSION,
    EMBEDDING_DEPLOYMENT,
)

embeddings = AzureOpenAIEmbeddings(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_deployment=EMBEDDING_DEPLOYMENT
)

def create_embedding(text: str):
    return embeddings.embed_query(text)