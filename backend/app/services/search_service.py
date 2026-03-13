from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from app.config.settings import (
    AZURE_SEARCH_ENDPOINT,
    AZURE_SEARCH_KEY,
    AZURE_SEARCH_INDEX,
)

search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_SEARCH_INDEX,
    credential=AzureKeyCredential(AZURE_SEARCH_KEY)
)

def upload_documents_to_index(documents: list):
    result = search_client.upload_documents(documents=documents)
    return result