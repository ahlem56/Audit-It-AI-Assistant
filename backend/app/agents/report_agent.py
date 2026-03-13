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
from app.models.agent_outputs import AuditReportOutput

llm = AzureChatOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_deployment=GPT_DEPLOYMENT
)

def generate_audit_report(user_request: str):
    docs = retrieve_documents(user_request)
    cited_context, cited_docs = build_cited_context(docs)

    prompt = f"""
You are an IT Audit expert.

Using ONLY the provided context, generate a structured IT audit report.

Return the result as VALID JSON only.
Do not add markdown.
Do not add explanations outside JSON.

Use this exact schema:
{{
  "executive_summary": "...",
  "scope": "...",
  "key_risks_identified": "...",
  "controls_observed": "...",
  "main_observations": "...",
  "recommendations": "...",
  "conclusion": "..."
}}

Each field should include citations like [Source 1][Source 2] where relevant.

Context:
{cited_context}

User request:
{user_request}
"""

    response = llm.invoke(prompt)
    raw_text = normalize_citations(response.content)

    parsed_json = extract_json_from_response(raw_text)
    structured_output = AuditReportOutput(**parsed_json)

    answer = f"""## Executive Summary
{structured_output.executive_summary}

## Scope
{structured_output.scope}

## Key Risks Identified
{structured_output.key_risks_identified}

## Controls Observed
{structured_output.controls_observed}

## Main Observations
{structured_output.main_observations}

## Recommendations
{structured_output.recommendations}

## Conclusion
{structured_output.conclusion}
"""

    return {
        "agent": "report_agent",
        "request": user_request,
        "structured_output": structured_output.model_dump(),
        "answer": answer,
        "sources": format_sources(cited_docs)
    }