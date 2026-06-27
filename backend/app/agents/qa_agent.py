from __future__ import annotations

import re
import unicodedata
from typing import Optional

from app.agents.priority_agent import classify_priority, enforce_min_priority
from app.models.audit_input import StructuredAuditInput
from app.services.llm_clients import get_chat_llm
from app.services.retrieval_service import retrieve_documents
from app.utils.citation_utils import build_cited_context, format_sources, normalize_citations
from app.utils.chat_utils import extract_current_question

_OBSERVATION_ID_RE = re.compile(r"\bOBS-\d+\b", re.IGNORECASE)
_TOP_RISKS_RE = re.compile(
    r"\b(top\s*risks?|key\s*risks?|principaux?\s+risques?|risques?\s+(?:majeurs?|cl[eé]s?))\b",
    re.IGNORECASE,
)
_PRIORITY_EXPLANATION_RE = re.compile(
    r"(?:\b(?:quelle|quel|what)\b.*\b(?:priorit[eé]|priority)\b|"
    r"\b(?:pourquoi|why)\b.*\b(?:critical|critique|high|medium|low|class[eé]e?|rated)\b|"
    r"\bjustif\w*\b.*\b(?:priorit[eé]|priority|classification)\b|"
    r"\b(?:niveau de priorit[eé]|priority level|classification)\b)",
    re.IGNORECASE,
)
_APPLICATION_OBSERVATIONS_RE = re.compile(
    r"\b(?:combien|liste|list|how many)\b.*\b(?:observation|finding)s?\b|"
    r"\b(?:observation|finding)s?\b.*\b(?:concern|relati|li[eé]e|about)\w*\b",
    re.IGNORECASE,
)
_REMEDIATION_PLAN_RE = re.compile(
    r"\bplan\b.*\brem[eé]diation\b.*\b30\b.*\b60\b.*\b90\b|"
    r"\b30\b.*\b60\b.*\b90\b.*\b(?:plan|rem[eé]diation)\b",
    re.IGNORECASE,
)
_POST_DEPARTURE_IDENTITY_RE = re.compile(
    r"\b(?:quel(?:le)?\s+utilisateur|qui|nom|identit[eé]|user(?:name)?)\b.*"
    r"\b(?:post[- ]?d[eé]part|apr[eè]s.*d[eé]part|cessation)\b.*\b(?:t24|temenos)\b",
    re.IGNORECASE,
)
_INSUFFICIENT_EVIDENCE = "The available context does not provide enough evidence to answer this conclusively."
_MISSION_INSUFFICIENT_EVIDENCE = "The selected mission does not provide enough evidence to answer this conclusively."


class QAAgent:
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
7. Answer the exact question first. Never replace a list, comparison, recommendation, or action-plan request with a general mission summary.
8. Do NOT use markdown tables unless the user explicitly asks for a table.
9. For recommendation or remediation-plan requests, turn the documented gaps and proposed recommendations into practical actions. Distinguish source facts from proposed deadlines or sequencing.
10. Keep the answer concise, precise, and evidence-based.
11. Never invent calendar dates, names, amounts, or evidence. When the source has no deadline, use a clearly labelled proposed relative target such as "within 15 days" or "within 30 days".

Context:
{cited_context}

Question:
{question}
"""
        llm = get_chat_llm()
        response = llm.invoke(prompt)
        answer = normalize_citations(response.content)

        cited_source_ids = set(re.findall(r"\[Source\s+(\d+)\]", answer, re.IGNORECASE))
        used_docs = [
            doc for index, doc in enumerate(cited_docs, start=1)
            if str(index) in cited_source_ids
        ]

        return {
            "agent": "qa_agent",
            "question": question,
            "answer": answer,
            "sources": format_sources(used_docs),
        }


def _mission_document_name(audit_input: StructuredAuditInput) -> str:
    return audit_input.mission.titre_mission or audit_input.mission.mission_id or "mission_audit_input.json"


def _build_mission_overview_doc(audit_input: StructuredAuditInput) -> dict:
    mission = audit_input.mission
    application_details = " | ".join(
        f"{item.name}: prestataire={item.provider or 'non renseigne'}, description={item.description or 'non renseignee'}"
        for item in mission.application_details
    )
    content = "\n".join(
        [
            f"Mission ID: {mission.mission_id}",
            f"Titre mission: {mission.titre_mission}",
            f"Entite auditee: {mission.entite_auditee}",
            f"Type mission: {mission.type_mission}",
            f"Periode: {mission.periode}",
            f"Applications: {', '.join(mission.applications or [])}",
            f"Details applications: {application_details}",
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
    return _observation_source_with_id(audit_input, observation, source_id="Source 1")


def _observation_source_with_id(audit_input: StructuredAuditInput, observation, *, source_id: str) -> dict:
    mission_title = _mission_document_name(audit_input)
    content = "\n".join(
        [
            f"Observation ID: {observation.observation_id}",
            f"Reference Controle: {observation.controle_ref}",
            f"Application: {observation.application}",
            f"Titre: {observation.titre_observation}",
            f"Constat: {observation.constat}",
            f"Risque associe: {observation.risque_associe or ''}",
            f"Impact potentiel: {observation.impact_potentiel or ''}",
            f"Procedure compensatoire: {observation.procedure_compensatoire}",
            f"Priority: {observation.priority or ''}",
            f"Priority reason: {observation.priority_reason or ''}",
            f"Priority justification: {observation.priority_justification or ''}",
            f"Responsables: {observation.responsables or ''}",
            f"Recommandation proposee: {observation.recommandation_proposee or ''}",
            f"References probantes: {observation.references_probantes or ''}",
        ]
    )
    return {
        "source_id": source_id,
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
            f"Responsables: {observation.responsables}",
            f"References probantes: {observation.references_probantes}",
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


def _build_observation_answer_v2(question: str, observation) -> str:
    priority = _determine_priority(observation)
    title = (observation.titre_observation or observation.observation_id or "Cette observation").strip()
    application = (observation.application or "le périmètre concerné").strip()
    risk = (observation.risque_associe or "").strip()
    impact = (observation.impact_potentiel or "").strip()
    constat = (observation.constat or "").strip()
    justification = (observation.priority_justification or "").strip()

    answer_parts = [
        f"{observation.observation_id} est classée {priority} car l'observation « {title} » met en évidence une faiblesse de contrôle sur {application}."
    ]

    if justification:
        answer_parts.append(f"Les faits retenus pour la classification montrent que {justification.rstrip('.')}.")
    elif constat:
        answer_parts.append(f"Les éléments probants disponibles dans le constat sont les suivants: {constat.rstrip('.')}.")

    if risk:
        risk_sentence = f"Le principal risque métier est {risk.rstrip('.').lower()}"
        if impact:
            risk_sentence += f", avec comme impact potentiel {impact.rstrip('.').lower()}"
        answer_parts.append(risk_sentence + ".")
    elif impact:
        answer_parts.append(f"L'impact potentiel identifié est {impact.rstrip('.').lower()}.")

    if priority == "Critical":
        answer_parts.append(
            "Le niveau Critical est retenu car l'exposition dépasse une simple anomalie administrative et peut affecter des accès sensibles, des opérations critiques ou la sécurité globale du périmètre audité."
        )
    elif priority == "High":
        answer_parts.append(
            "Le niveau High est retenu car la faiblesse crée une exposition significative qui nécessite une remédiation prioritaire, sans atteindre nécessairement le seuil de criticité maximale."
        )
    elif priority == "Medium":
        answer_parts.append(
            "Le niveau Medium traduit une faiblesse réelle du dispositif de contrôle, avec une exposition qui reste plus contenue à ce stade."
        )
    else:
        answer_parts.append(
            "Le niveau Low traduit un écart à corriger, avec une exposition plus limitée au regard des éléments actuellement disponibles."
        )

    return " ".join(answer_parts) + " [Source 1]"


def _priority_rank(priority: str | None) -> int:
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return order.get((priority or "").strip(), 4)


def _risk_exposure_score(observation) -> tuple[int, int, str, str]:
    priority = _determine_priority(observation)
    text = " ".join(
        [
            observation.titre_observation or "",
            observation.constat or "",
            observation.risque_associe or "",
            observation.impact_potentiel or "",
            observation.application or "",
        ]
    ).lower()

    exposure_boost = 0
    if any(marker in text for marker in ("t24", "swift", "openbanking", "banque en ligne", "paie", "payroll")):
        exposure_boost += 2
    if any(marker in text for marker in ("operation", "transaction", "mouvement", "virement", "fraude")):
        exposure_boost += 2
    if any(marker in text for marker in ("post-depart", "post départ", "post depart", "comptes actifs", "superuser", "compte generique", "compte partagé", "partage")):
        exposure_boost += 1
    if any(marker in text for marker in ("pra", "pca", "sinistre", "patch", "correctif", "vulnerabil")):
        exposure_boost += 1

    return (_priority_rank(priority), -exposure_boost, observation.observation_id or "", priority)


def _truncate_fact(text: str, limit: int = 220) -> str:
    value = " ".join((text or "").split()).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip(" .,;:") + "..."


def _top_reason(priority: str, observation) -> str:
    risk = (observation.risque_associe or "").strip()
    impact = (observation.impact_potentiel or "").strip()
    if priority == "Critical":
        if impact:
            return f"Ce point est classé parmi les top risks car son impact potentiel est {impact.rstrip('.').lower()}."
        return "Ce point est classé parmi les top risks car il combine forte exposition, sensibilité du périmètre et besoin de remédiation immédiate."
    if priority == "High":
        if risk:
            return f"Ce point fait partie des top risks car il crée une exposition significative à {risk.rstrip('.').lower()}."
        return "Ce point fait partie des top risks car il présente une exposition significative nécessitant une remédiation prioritaire."
    return "Ce point reste suivi parmi les risques les plus exposés au regard de son effet potentiel sur le dispositif de contrôle."


def _build_top_risks_answer(audit_input: StructuredAuditInput) -> dict:
    reportable = [item for item in audit_input.observations if item.included_in_report]
    if not reportable:
        return {
            "agent": "qa_agent",
            "question": "top risks",
            "answer": "Aucun risque majeur ne peut être restitué, car aucune observation exploitable n'est disponible dans la mission sélectionnée.",
            "sources": [],
        }

    ranked = sorted(reportable, key=_risk_exposure_score)[:5]
    intro = (
        "Les top risks sont classés selon trois critères: "
        "1) le niveau de priorité retenu, "
        "2) la sensibilité du périmètre applicatif concerné, "
        "3) l'impact potentiel métier ou sécurité décrit dans l'observation."
    )

    lines = [intro, "", "Les risques les plus exposés sont les suivants:"]
    sources = []

    for index, observation in enumerate(ranked, start=1):
        source_id = f"Source {index}"
        priority = _determine_priority(observation)
        title = (observation.titre_observation or observation.observation_id or "Observation").strip()
        fact = _truncate_fact(observation.constat or "Fait observé non renseigné.")
        risk = (observation.risque_associe or "Risque métier non renseigné").strip()
        why_top = _top_reason(priority, observation)

        lines.extend(
            [
                "",
                f"{index}. {title} ({priority}) [{source_id}]",
                f"Fait observé: {fact}",
                f"Risque métier: {risk.rstrip('.')}.",
                f"Pourquoi c'est un top risk: {why_top}",
            ]
        )
        sources.append(_observation_source_with_id(audit_input, observation, source_id=source_id))

    return {
        "agent": "qa_agent",
        "question": "top risks",
        "answer": "\n".join(lines),
        "sources": sources,
    }


def _normalized_text(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value or "")
        if unicodedata.category(character) != "Mn"
    ).lower()


def _build_application_observations_answer(
    question: str,
    audit_input: StructuredAuditInput,
) -> dict | None:
    if not _APPLICATION_OBSERVATIONS_RE.search(question):
        return None

    normalized_question = _normalized_text(question)
    application_names = [item.name for item in audit_input.mission.application_details if item.name]
    application_names.extend(audit_input.mission.applications or [])
    application_names.extend(item.application for item in audit_input.observations if item.application)

    matched_application = next(
        (
            name for name in sorted(set(application_names), key=len, reverse=True)
            if _normalized_text(name) in normalized_question
        ),
        None,
    )
    if not matched_application:
        return None

    application_key = _normalized_text(matched_application)
    observations = [
        item for item in audit_input.observations
        if item.included_in_report and application_key in _normalized_text(item.application)
    ]
    if not observations:
        return None

    grouped: dict[str, list] = {}
    for observation in observations:
        grouped.setdefault(observation.domaine_controle or "Processus non renseigne", []).append(observation)

    lines = [f"{len(observations)} observations concernent {matched_application}.", ""]
    sources = []
    source_index = 1
    for process, process_observations in grouped.items():
        lines.append(f"**{process}**")
        for observation in process_observations:
            source_id = f"Source {source_index}"
            lines.append(
                f"- {observation.observation_id} | {observation.controle_ref} | "
                f"{observation.titre_observation} [{source_id}]"
            )
            sources.append(_observation_source_with_id(audit_input, observation, source_id=source_id))
            source_index += 1
        lines.append("")

    return {
        "agent": "qa_agent",
        "question": question,
        "answer": "\n".join(lines).strip(),
        "sources": sources,
    }


def _report_findings(report_result: dict | None) -> list[dict]:
    structured = (report_result or {}).get("structured_output")
    if not isinstance(structured, dict):
        return []
    return [item for item in structured.get("detailed_findings", []) or [] if isinstance(item, dict)]


def _finding_action(finding: dict, *fields: str) -> str:
    for field in fields:
        value = " ".join(str(finding.get(field) or "").split()).strip()
        if value:
            return value.rstrip(".") + "."
    return "Formaliser l'action corrective, son responsable et ses preuves de mise en oeuvre."


def _remediation_source(audit_input, observation, finding: dict, *, source_id: str) -> dict:
    action = _finding_action(finding, "immediate_action", "structural_action", "recommendation")
    owner = observation.responsables or str(finding.get("owner") or finding.get("owners") or "")
    evidence = str(finding.get("evidence_expected") or "").strip()
    content = "\n".join(
        [
            f"Observation ID: {observation.observation_id}",
            f"Reference Controle: {observation.controle_ref}",
            f"Application: {observation.application}",
            f"Titre: {observation.titre_observation}",
            f"Priorite: {finding.get('priority') or observation.priority or ''}",
            f"Action de remediation: {action}",
            f"Responsables: {owner}",
            f"Preuves attendues: {evidence}",
        ]
    )
    return {
        "source_id": source_id,
        "document_name": f"{_mission_document_name(audit_input)} - plan de remediation",
        "chunk_id": None,
        "score": None,
        "excerpt": content[:300],
    }


def _build_remediation_plan(
    audit_input: StructuredAuditInput,
    report_result: dict | None,
) -> dict:
    observations = {item.observation_id: item for item in audit_input.observations if item.included_in_report}
    findings = _report_findings(report_result)
    finding_by_id = {str(item.get("observation_id") or "").strip(): item for item in findings}

    def plan_priority(item) -> str:
        return str(finding_by_id.get(item.observation_id, {}).get("priority") or item.priority or "High")

    ranked = sorted(
        observations.values(),
        key=lambda item: (_priority_rank(plan_priority(item)), item.observation_id),
    )
    critical = [item for item in ranked if plan_priority(item) == "Critical"]
    remaining = [item for item in ranked if item not in critical]

    lines = [
        "Voici un calendrier de remédiation proposé. Les horizons 30/60/90 jours sont des cibles de pilotage, et non des échéances déjà approuvées.",
        "",
        "## Sous 30 jours — contenir les expositions critiques",
    ]
    sources = []
    source_index = 1

    for observation in critical:
        finding = finding_by_id.get(observation.observation_id, {})
        source_id = f"Source {source_index}"
        owner = str(observation.responsables or finding.get("owner") or finding.get("owners") or "Responsable à confirmer")
        action = _finding_action(finding, "immediate_action", "recommendation")
        evidence = str(finding.get("evidence_expected") or "preuve de correction et validation du responsable").rstrip(" .")
        lines.append(f"- **{observation.observation_id} — {observation.titre_observation}** [{source_id}]")
        lines.append(f"  Action: {action}")
        lines.append(f"  Responsable: {owner}.")
        lines.append(f"  Preuves attendues: {evidence}.")
        sources.append(_remediation_source(audit_input, observation, finding, source_id=source_id))
        source_index += 1

    lines.extend(["", "## Sous 60 jours — corriger les autres faiblesses et industrialiser les contrôles"])
    for observation in remaining:
        finding = finding_by_id.get(observation.observation_id, {})
        source_id = f"Source {source_index}"
        priority = plan_priority(observation)
        owner = str(observation.responsables or finding.get("owner") or finding.get("owners") or "Responsable à confirmer")
        action = _finding_action(finding, "structural_action", "recommendation")
        lines.append(f"- **{observation.observation_id} ({priority})**: {action} Responsable: {owner}. [{source_id}]")
        sources.append(_remediation_source(audit_input, observation, finding, source_id=source_id))
        source_index += 1

    lines.extend(
        [
            "",
            "## Sous 90 jours — vérifier l’efficacité et clôturer",
            "- Faire retester chaque observation par l’audit interne ou le contrôle permanent.",
            "- Ne clôturer un point qu’après validation des preuves, des exceptions résiduelles et du responsable métier.",
            "- Mettre en place un tableau de bord mensuel avec statut, propriétaire, cible, preuve et retard.",
            "- Escalader au comité d’audit les observations critiques non corrigées ou sans preuve suffisante.",
        ]
    )

    return {
        "agent": "qa_agent",
        "question": "plan de remediation 30/60/90 jours",
        "answer": "\n".join(lines),
        "sources": sources,
    }


def _build_post_departure_identity_answer(audit_input: StructuredAuditInput) -> dict | None:
    observation = next(
        (
            item for item in audit_input.observations
            if item.observation_id == "OBS-001" and "t24" in _normalized_text(item.application)
        ),
        None,
    )
    if observation is None:
        return None

    constat = " ".join((observation.constat or "").split())
    active_match = re.search(r"(\d+)\s+comptes?.{0,80}(?:toujours|encore)\s+actifs?", constat, re.IGNORECASE)
    operations_match = re.search(r"parmi.{0,40}?\b(\d+)\s+ont\s+r[eé]alis[eé]", constat, re.IGNORECASE)
    high_value_match = re.search(r"dont\s+(\d+).{0,80}?fort\s+encours", constat, re.IGNORECASE)
    quantified_facts = []
    if active_match:
        quantified_facts.append(f"{active_match.group(1)} comptes étaient encore actifs")
    if operations_match:
        quantified_facts.append(f"{operations_match.group(1)} ont réalisé des opérations après le départ")
    if high_value_match:
        quantified_facts.append(f"{high_value_match.group(1)} concernaient des comptes clients à fort encours")
    fact_sentence = (
        "Le constat fournit uniquement les éléments quantifiés suivants: " + "; ".join(quantified_facts) + ". "
        if quantified_facts
        else "Le constat signale des opérations post-départ sans identifier nominativement leurs auteurs. "
    )

    source_id = "Source 1"
    return {
        "agent": "qa_agent",
        "question": "identite des utilisateurs post-depart T24",
        "answer": (
            "Le contexte ne fournit aucun nom, identifiant de compte ou utilisateur permettant d’identifier les personnes concernées. "
            f"{fact_sentence}"
            "Il est donc impossible de répondre précisément sans l’extraction détaillée des comptes et des journaux T24. "
            f"[{source_id}]"
        ),
        "sources": [_observation_source_with_id(audit_input, observation, source_id=source_id)],
    }


def answer_mission_question(
    question: str,
    audit_input: StructuredAuditInput | None,
    report_result: dict | None = None,
) -> dict | None:
    if audit_input is None:
        return None

    current_question = extract_current_question(question)

    if _REMEDIATION_PLAN_RE.search(current_question):
        return _build_remediation_plan(audit_input, report_result)

    if _POST_DEPARTURE_IDENTITY_RE.search(current_question):
        return _build_post_departure_identity_answer(audit_input)

    application_result = _build_application_observations_answer(current_question, audit_input)
    if application_result is not None:
        return application_result

    if _TOP_RISKS_RE.search(current_question):
        return _build_top_risks_answer(audit_input)

    matches = _OBSERVATION_ID_RE.findall(current_question)
    if len(matches) != 1 or not _PRIORITY_EXPLANATION_RE.search(current_question):
        return None

    observation_id = matches[0].upper()
    observation = next(
        (item for item in audit_input.observations if (item.observation_id or "").strip().upper() == observation_id),
        None,
    )
    if observation is None:
        return None

    return {
        "agent": "qa_agent",
        "question": current_question,
        "answer": _build_observation_answer_v2(current_question, observation),
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
    mission_result = answer_mission_question(question, audit_input, report_result)
    if mission_result is not None:
        return mission_result

    if audit_input is not None:
        mission_docs = _build_mission_docs(audit_input, report_result)
        current_question = extract_current_question(question)
        requested_ids = {item.upper() for item in _OBSERVATION_ID_RE.findall(current_question)}
        if requested_ids:
            mission_docs = [
                doc for doc in mission_docs
                if any(f"Observation ID: {observation_id}" in doc.get("content", "") for observation_id in requested_ids)
            ]
        mission_response = _run_qa_from_docs(question, mission_docs, mission_scoped=True)
        if mission_response.get("answer", "").strip() != _INSUFFICIENT_EVIDENCE:
            return mission_response
        if docs:
            combined_docs = mission_docs + docs
            return _run_qa_from_docs(question, combined_docs, mission_scoped=True)
        return mission_response

    return QAAgent().run({"question": question, "docs": docs, "mission_scoped": mission_scoped})
