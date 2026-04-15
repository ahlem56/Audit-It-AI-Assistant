from __future__ import annotations

import re
from typing import Optional

from app.agents.base import BaseAgent
from app.agents.priority_agent import classify_priority, enforce_min_priority
from app.models.audit_input import StructuredAuditInput
from app.services.llm_clients import get_chat_llm
from app.services.retrieval_service import retrieve_documents
from app.utils.citation_cleaner import normalize_citations
from app.utils.citation_formatter import build_cited_context
from app.utils.source_formatter import format_sources

llm = get_chat_llm()
_OBSERVATION_ID_RE = re.compile(r"\bOBS-\d+\b", re.IGNORECASE)
_INSUFFICIENT_EVIDENCE = "The available context does not provide enough evidence to answer this conclusively."
_MISSION_INSUFFICIENT_EVIDENCE = "The selected mission does not provide enough evidence to answer this conclusively."


class QAAgent(BaseAgent):
    def run(self, input_data: dict) -> dict:
        question = input_data["question"]
        docs = input_data.get("docs")
        mission_scoped = bool(input_data.get("mission_scoped"))
        if docs is None:
            if mission_scoped:
                docs = []
            else:
                docs = retrieve_documents(question)

        if not docs:
            return {
                "agent": "qa_agent",
                "question": question,
                "answer": _MISSION_INSUFFICIENT_EVIDENCE if mission_scoped else _INSUFFICIENT_EVIDENCE,
                "sources": [],
            }

        cited_context, cited_docs = build_cited_context(docs)

        prompt = f"""
You are a highly rigorous Audit assistant.

Answer the user's question using ONLY the provided context.

STRICT RULES:
1. Use ONLY facts explicitly stated in the context.
2. Do NOT infer, assume, generalize, or use outside knowledge.
3. If the answer is not clearly supported by the context, say: "The available context does not provide enough evidence to answer this conclusively."
4. If the context contains conflicting statements, explicitly mention the inconsistency.
5. Every factual statement must include citation(s) in the format [Source X] or [Source X][Source Y].
6. Do NOT cite a source unless it directly supports the statement.
7. Keep the answer concise, precise, and evidence-based.
8. Do NOT use markdown tables unless the user explicitly asks for a table.

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
            "sources": format_sources(cited_docs),
        }


def _mission_document_name(audit_input: StructuredAuditInput) -> str:
    return audit_input.mission.titre_mission or audit_input.mission.mission_id or "mission_audit_input.json"


def _build_mission_overview_doc(audit_input: StructuredAuditInput) -> dict:
    mission = audit_input.mission
    content = "\n".join(
        [
            f"Mission ID: {mission.mission_id}",
            f"Titre mission: {mission.titre_mission}",
            f"Entite auditee: {mission.entite_auditee}",
            f"Type mission: {mission.type_mission}",
            f"Periode: {mission.periode}",
            f"Applications: {', '.join(mission.applications or [])}",
            f"Processus couverts: {', '.join(mission.processus_couverts or [])}",
            f"Intervenants: {', '.join(mission.intervenants or [])}",
        ]
    )
    return {
        "document_name": _mission_document_name(audit_input),
        "chunk_id": 0,
        "score": 1.0,
        "content": content,
    }


def _observation_source(audit_input: StructuredAuditInput, observation) -> dict:
    mission_title = _mission_document_name(audit_input)
    content = "\n".join(
        [
            f"Observation ID: {observation.observation_id}",
            f"Reference Controle: {observation.controle_ref}",
            f"Application: {observation.application}",
            f"Titre: {observation.titre_observation}",
            f"Constat: {observation.constat}",
            f"Procedure compensatoire: {observation.procedure_compensatoire}",
            f"Priority: {observation.priority or ''}",
            f"Priority justification: {observation.priority_justification or ''}",
        ]
    )
    return {
        "source_id": "Source 1",
        "document_name": mission_title,
        "chunk_id": None,
        "score": None,
        "excerpt": content[:300],
    }


def _build_observation_doc(audit_input: StructuredAuditInput, observation, *, chunk_id: int) -> dict:
    content = "\n".join(
        [
            f"Observation ID: {observation.observation_id}",
            f"Domaine controle: {observation.domaine_controle}",
            f"Categorie controle: {observation.categorie_controle}",
            f"Reference controle: {observation.controle_ref}",
            f"Application: {observation.application}",
            f"Couche: {observation.couche}",
            f"Titre observation: {observation.titre_observation}",
            f"Constat: {observation.constat}",
            f"Risque associe: {observation.risque_associe}",
            f"Impact potentiel: {observation.impact_potentiel}",
            f"Procedure compensatoire: {observation.procedure_compensatoire}",
            f"Cause racine: {observation.cause_racine}",
            f"Recommandation proposee: {observation.recommandation_proposee}",
            f"Commentaire auditeur: {observation.commentaire_auditeur}",
            f"Priorite: {observation.priority or _determine_priority(observation)}",
            f"Justification priorite: {observation.priority_justification}",
        ]
    )
    return {
        "document_name": _mission_document_name(audit_input),
        "chunk_id": chunk_id,
        "score": 1.0,
        "content": content,
    }


def _build_report_docs(audit_input: StructuredAuditInput, report_result: dict | None) -> list[dict]:
    if not report_result:
        return []

    structured = report_result.get("structured_output")
    if not isinstance(structured, dict):
        return []

    docs: list[dict] = []
    summary_content = "\n".join(
        [
            f"Executive summary: {structured.get('executive_summary', '')}",
            f"General synthesis: {structured.get('general_synthesis', '')}",
            f"Conclusion: {structured.get('conclusion', '')}",
            f"Priority insight: {structured.get('priority_insight', '')}",
            f"Strategic priorities: {' | '.join(structured.get('strategic_priorities', []) or [])}",
        ]
    )
    if summary_content.strip():
        docs.append(
            {
                "document_name": f"{_mission_document_name(audit_input)} - report summary",
                "chunk_id": 10_000,
                "score": 1.0,
                "content": summary_content,
            }
        )

    for index, finding in enumerate(structured.get("detailed_findings", []) or [], start=10_100):
        if not isinstance(finding, dict):
            continue
        content = "\n".join(
            [
                f"Observation ID: {finding.get('observation_id', '')}",
                f"Reference: {finding.get('reference', '')}",
                f"Application: {finding.get('application', '')}",
                f"Title: {finding.get('title', '')}",
                f"Finding: {finding.get('finding', '')}",
                f"Risk impact: {finding.get('risk_impact', '')}",
                f"Impact detail: {finding.get('impact_detail', '')}",
                f"Root cause: {finding.get('root_cause', '')}",
                f"Recommendation: {finding.get('recommendation', '')}",
                f"Priority: {finding.get('priority', '')}",
                f"Priority justification: {finding.get('priority_justification', '')}",
                f"Management summary: {finding.get('management_summary', '')}",
            ]
        )
        docs.append(
            {
                "document_name": f"{_mission_document_name(audit_input)} - report finding",
                "chunk_id": index,
                "score": 1.0,
                "content": content,
            }
        )

    return docs


def _build_mission_docs(audit_input: StructuredAuditInput, report_result: dict | None = None) -> list[dict]:
    docs = [_build_mission_overview_doc(audit_input)]
    for index, observation in enumerate(audit_input.observations, start=1):
        docs.append(_build_observation_doc(audit_input, observation, chunk_id=index))
    docs.extend(_build_report_docs(audit_input, report_result))
    return docs


def _run_qa_from_docs(question: str, docs: list[dict], *, mission_scoped: bool = False) -> dict:
    return QAAgent().run({"question": question, "docs": docs, "mission_scoped": mission_scoped})


def _determine_priority(observation) -> str:
    existing = (observation.priority or "").strip()
    if existing:
        return existing

    priority_input = {
        "reference": observation.controle_ref,
        "title": observation.titre_observation,
        "condition": observation.constat,
        "constat": observation.constat,
        "application": observation.application,
        "category": observation.categorie_controle,
        "impact": observation.impact_potentiel,
        "impact_potentiel": observation.impact_potentiel,
    }
    computed = classify_priority(priority_input)
    enforced = enforce_min_priority(priority_input, computed)

    text = " ".join(
        [
            observation.titre_observation or "",
            observation.constat or "",
            observation.procedure_compensatoire or "",
            observation.commentaire_auditeur or "",
        ]
    ).lower()
    if observation.controle_ref.upper().strip() == "APD-03" and any(
        marker in text
        for marker in ("compte générique", "comptes génériques", "compte generique", "comptes generiques", "sap_all", "administrateur")
    ):
        return "High"

    return enforced


def _build_observation_answer(question: str, observation) -> str:
    priority = _determine_priority(observation)
    justification = (observation.priority_justification or "").strip()
    if justification:
        return (
            f"{observation.observation_id} est classée {priority} car {justification.rstrip('.')}."
            f" [Source 1]"
        )

    facts: list[str] = []
    if observation.constat:
        facts.append(observation.constat.strip())
    if observation.procedure_compensatoire:
        facts.append(f"Élément compensatoire déclaré: {observation.procedure_compensatoire.strip()}")
    if observation.commentaire_auditeur:
        facts.append(f"Élément probant auditeur: {observation.commentaire_auditeur.strip()}")

    evidence = " ".join(facts)
    if evidence:
        return (
            f"{observation.observation_id} est classée {priority} au vu des éléments disponibles: "
            f"{evidence} [Source 1]"
        )

    return (
        f"{observation.observation_id} est classée {priority}, mais l'input structuré ne contient pas de justification "
        f"détaillée supplémentaire. [Source 1]"
    )


def answer_mission_question(question: str, audit_input: StructuredAuditInput | None) -> dict | None:
    if audit_input is None:
        return None

    match = _OBSERVATION_ID_RE.search(question or "")
    if match is None:
        return None

    observation_id = match.group(0).upper()
    observation = next(
        (item for item in audit_input.observations if (item.observation_id or "").strip().upper() == observation_id),
        None,
    )
    if observation is None:
        return None

    return {
        "agent": "qa_agent",
        "question": question,
        "answer": _build_observation_answer(question, observation),
        "sources": [_observation_source(audit_input, observation)],
    }


def answer_question(
    question: str,
    docs: Optional[list[dict]] = None,
    *,
    audit_input: StructuredAuditInput | None = None,
    report_result: dict | None = None,
    mission_scoped: bool = False,
) -> dict:
    mission_result = answer_mission_question(question, audit_input)
    if mission_result is not None:
        return mission_result

    if audit_input is not None:
        mission_docs = _build_mission_docs(audit_input, report_result)
        mission_response = _run_qa_from_docs(question, mission_docs, mission_scoped=True)
        if mission_response.get("answer", "").strip() != _INSUFFICIENT_EVIDENCE:
            return mission_response
        if docs:
            combined_docs = mission_docs + docs
            return _run_qa_from_docs(question, combined_docs, mission_scoped=True)
        return mission_response

    return QAAgent().run({"question": question, "docs": docs, "mission_scoped": mission_scoped})
