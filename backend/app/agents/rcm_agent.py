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
from app.models.agent_outputs import RCMOutput

llm = AzureChatOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_deployment=GPT_DEPLOYMENT
)

def generate_rcm(user_request: str):
    docs = retrieve_documents(user_request)
    cited_context, cited_docs = build_cited_context(docs)

    prompt = f"""
You are an IT Audit expert.

Using ONLY the provided context, generate a Risk Control Matrix (RCM).

Return the result as VALID JSON only.
Do not add markdown.
Do not add explanations outside JSON.

Use this exact schema:
{{
  "rows": [
    {{
      "process_domain": "...",
      "risk": "...",
      "control": "...",
      "test_procedure": "...",
      "expected_evidence": "...",
      "source_reference": "[Source 1]"
    }}
  ]
}}

Context:
{cited_context}

User request:
{user_request}
"""

    response = llm.invoke(prompt)
    raw_text = normalize_citations(response.content)

    parsed_json = extract_json_from_response(raw_text)
    structured_output = RCMOutput(**parsed_json)

    # Build readable markdown table
    lines = [
        "| Process / Domain | Risk | Control | Test Procedure | Expected Evidence | Source Reference |",
        "|---|---|---|---|---|---|"
    ]

    for row in structured_output.rows:
        lines.append(
            f"| {row.process_domain} | {row.risk} | {row.control} | {row.test_procedure} | {row.expected_evidence} | {row.source_reference} |"
        )

    answer = "\n".join(lines)

    return {
        "agent": "rcm_agent",
        "request": user_request,
        "structured_output": structured_output.model_dump(),
        "answer": answer,
        "sources": format_sources(cited_docs)
    }