from langchain_openai import AzureChatOpenAI
from app.config.settings import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_API_VERSION,
    GPT_DEPLOYMENT,
)
from app.services.retrieval_service import retrieve_documents
from app.utils.citation_formatter import build_cited_context
from app.utils.source_formatter import format_sources
from app.utils.citation_cleaner import normalize_citations

llm = AzureChatOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_deployment=GPT_DEPLOYMENT
)

def rag_answer(question: str):
    docs = retrieve_documents(question)

    cited_context, cited_docs = build_cited_context(docs)

    prompt = f"""
You are an IT Audit assistant.

Answer using ONLY the provided context.
Cite sources using this STRICT format:

[Source 1]
[Source 2]

If multiple sources are used together, write them like this:

[Source 1][Source 2]

DO NOT use commas or semicolons like:
[Source 1, Source 2]
[Source 1; Source 2]
If the answer is not clearly available in the context, say so.

Context:
{cited_context}

Question:
{question}
"""

    response = llm.invoke(prompt)

    answer = normalize_citations(response.content)

    return {
        "answer": answer,
        "sources": format_sources(cited_docs)
    }