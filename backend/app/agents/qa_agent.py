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

def answer_question(question: str):
    docs = retrieve_documents(question)

    cited_context, cited_docs = build_cited_context(docs)

    prompt = f"""
You are an IT Audit assistant.

Answer the user's question using ONLY the provided context.
When you use information from the context, cite the relevant source using [Source X].
If the answer is not clearly in the context, say so.

Context:
{cited_context}

Question:
{question}
"""

    response = llm.invoke(prompt)

    answer = normalize_citations(response.content)

    return {
        "agent": "qa_agent",
        "question": question,
        "answer": answer,
        "sources": format_sources(cited_docs)
    }