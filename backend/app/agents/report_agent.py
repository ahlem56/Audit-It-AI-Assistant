from __future__ import annotations

from typing import Optional

from langchain_openai import AzureChatOpenAI

from app.config.settings import (
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    GPT_DEPLOYMENT,
)
from app.models.agent_outputs import SourceReference
from app.services.audit_input_service import load_latest_audit_input
from app.services.report_composer_service import compose_audit_report
from app.services.french_polish_service import polish_report_payload
from app.services.retrieval_service import retrieve_documents
from app.utils.citation_cleaner import normalize_citations
from app.utils.citation_formatter import build_cited_context
from app.utils.json_parser import extract_json_from_response
from app.utils.source_formatter import format_sources


llm = AzureChatOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_deployment=GPT_DEPLOYMENT,
)


def _build_structured_answer(structured_output) -> str:
    priority_overview = ", ".join(
        f"{item.priority}: {item.count}" for item in structured_output.priority_summary
    ) or "Aucune observation classee."

    findings_preview = []
    for finding in structured_output.detailed_findings[:5]:
        findings_preview.append(
            f"- {finding.reference} | {finding.application} | {finding.title} | Priorite: {finding.priority}"
        )

    findings_block = "\n".join(findings_preview) if findings_preview else "- Aucun point releve."

    return f"""## Executive Summary
{structured_output.executive_summary}

## General Synthesis
{structured_output.general_synthesis}

## Priority Overview
{priority_overview}

## Key Findings
{findings_block}

## Conclusion
{structured_output.conclusion}
""" 


def _compose_structured_report_payload(user_request: str, audit_input) -> dict:
    structured_output = compose_audit_report(audit_input)
    polished_payload = polish_report_payload(structured_output.model_dump())
    structured_output = type(structured_output).model_validate(polished_payload)
    answer = _build_structured_answer(structured_output)
    return {
        "agent": "report_agent",
        "request": user_request,
        "structured_output": structured_output.model_dump(),
        "answer": answer,
        "sources": [],
    }


def _fallback_report(user_request: str, docs: Optional[list[dict]] = None) -> dict:
    if docs is None:
        docs = retrieve_documents(user_request)

    cited_context, cited_docs = build_cited_context(docs)
    prompt = f"""
You are a highly rigorous Audit expert.

Your task is to generate a concise audit report using ONLY the provided context.

STRICT RULES:
1. Use ONLY facts explicitly stated in the context.
2. Do NOT invent deficiencies, control failures, or recommendations not grounded in the context.
3. If evidence is insufficient, say so explicitly.
4. Return VALID JSON only. No markdown. No commentary.

OUTPUT SCHEMA:
{{
  "executive_summary": "...",
  "general_synthesis": "...",
  "conclusion": "..."
}}

Context:
{cited_context}

User request:
{user_request}
"""
    response = llm.invoke(prompt)
    raw_text = normalize_citations(response.content)
    parsed_json = extract_json_from_response(raw_text)

    answer = f"""## Executive Summary
{parsed_json.get("executive_summary", "")}

## General Synthesis
{parsed_json.get("general_synthesis", "")}

## Conclusion
{parsed_json.get("conclusion", "")}
"""

    return {
        "agent": "report_agent",
        "request": user_request,
        "structured_output": {
            "cover_title": "Rapport d'audit IT",
            "cover_subtitle": "",
            "client_name": "",
            "report_period": "",
            "report_date": "",
            "table_of_contents": [],
            "preamble": "",
            "objectives": [],
            "stakeholders": [],
            "scope_summary": "",
            "applications": [],
            "covered_processes": [],
            "audit_approach": [],
            "covered_controls": [],
            "control_matrix": [],
            "key_figures": [],
            "executive_highlights": [],
            "strengths": [],
            "watch_points": [],
            "maturity_assessment": "",
            "priority_insight": "",
            "strategic_priorities": [],
            "process_summaries": [],
            "general_synthesis": parsed_json.get("general_synthesis", ""),
            "priority_summary": [],
            "detailed_findings": [],
            "detailed_recommendations": [],
            "prior_recommendations_follow_up": [],
            "appendices": [],
            "executive_summary": parsed_json.get("executive_summary", ""),
            "conclusion": parsed_json.get("conclusion", ""),
        },
        "answer": answer,
        "sources": format_sources(cited_docs),
    }


def generate_audit_report(
    user_request: str,
    docs: Optional[list[dict]] = None,
    audit_input=None,
):
    if audit_input is None:
        # Compatibility fallback for the older single-mission flow.
        audit_input = load_latest_audit_input()

    if audit_input and audit_input.observations:
        return _compose_structured_report_payload(user_request, audit_input)

    fallback = _fallback_report(user_request, docs=docs)
    if not fallback["sources"]:
        fallback["sources"] = [
            SourceReference(
                source_id="structured_input_missing",
                document_name="latest_audit_input.json",
                excerpt="No structured audit input was available; the report used retrieval fallback.",
            )
        ]
    return fallback
