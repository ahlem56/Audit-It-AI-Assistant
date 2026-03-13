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
from app.utils.json_parser import extract_json_from_response
from app.models.agent_outputs import ObservationOutput

llm = AzureChatOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_deployment=GPT_DEPLOYMENT
)

def generate_observation(user_request: str):
    docs = retrieve_documents(user_request)
    cited_context, cited_docs = build_cited_context(docs)

    prompt = f"""
You are an IT Audit expert.

Using ONLY the provided context, generate a formal IT audit observation.

Return the result as VALID JSON only.
Do not add markdown.
Do not add explanations outside JSON.

Use this exact schema:
{{
  "title": "...",
  "condition": "...",
  "risk_impact": "...",
  "recommendation": "..."
}}

Each field must contain citations like [Source 1][Source 2] when relevant.

Context:
{cited_context}

User request:
{user_request}
"""

    response = llm.invoke(prompt)
    raw_text = normalize_citations(response.content)

    parsed_json = extract_json_from_response(raw_text)
    structured_output = ObservationOutput(**parsed_json)

    answer = f"""### Title
{structured_output.title}

### Condition
{structured_output.condition}

### Risk / Impact
{structured_output.risk_impact}

### Recommendation
{structured_output.recommendation}
"""

    return {
        "agent": "observation_agent",
        "request": user_request,
        "structured_output": structured_output.model_dump(),
        "answer": answer,
        "sources": format_sources(cited_docs)
    }