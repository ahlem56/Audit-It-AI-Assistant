from __future__ import annotations

import json
from typing import Iterable

from app.domain.itgc_control_catalog import CONTROL_CATALOG
from app.models.audit_input import AuditObservation
from app.models.observation_reasoning import ObservationReasoning
from app.services.llm_clients import get_chat_llm
from app.utils.json_parser import extract_json_from_response

# NOTE: This prompt is formatted via .format(...). Any literal JSON braces must be escaped.
_PROMPT = """
Tu es un auditeur ITGC senior (style cabinet type PwC).

Objectif: pour CHAQUE observation, produire une analyse d'audit structurée et actionnable.

Règles:
1) Base-toi uniquement sur les informations fournies dans l'observation (constat, procédure compensatoire, commentaire auditeur, controle_ref, application).
2) Standardise l'analyse selon le catalogue de contrôles fourni (CONTROL_CATALOG). Les risques et recommandations doivent être cohérents avec le controle_ref.
3) Tu peux inférer le risque / impact / cause racine de façon générique (ITGC), mais la justification de priorité doit citer des faits du constat (chiffres, occurrences, taille d'échantillon, absence explicite, etc.).
4) Ne jamais inventer des éléments probants (dates, nombres, outils) qui ne figurent pas dans l'observation.
5) La priorité doit être une des valeurs: Critical, High, Medium, Low.
6) Le ton de la recommandation doit être formel, concret, et orienté contrôle (verbe d'action + mécanisme de preuve).
7) Si le controle_ref n'est pas reconnu, appliquer les bonnes pratiques ITGC les plus proches sans inventer de spécificités.

Schéma JSON attendu (liste, 1 élément par observation, sans markdown):
[
  {{
    "observation_id": "...",
    "risk": "...",
    "impact": "...",
    "root_cause": "...",
    "priority": "Critical|High|Medium|Low",
    "priority_justification": "...",
    "recommendation": "...",
    "recommendation_objective": "...",
    "recommendation_steps": ["...", "..."]
  }}
]

Observations:
{observations_json}

CONTROL_CATALOG (standard attendu):
{control_catalog_json}
""".strip()


def _obs_to_dict(observation: AuditObservation) -> dict:
    return {
        "observation_id": observation.observation_id,
        "controle_ref": observation.controle_ref,
        "domaine_controle": observation.domaine_controle,
        "categorie_controle": observation.categorie_controle,
        "application": observation.application,
        "titre_observation": observation.titre_observation,
        "constat": observation.constat,
        "procedure_compensatoire": observation.procedure_compensatoire,
        "commentaire_auditeur": observation.commentaire_auditeur,
        "controle_attendu": observation.controle_attendu,
        "impact_potentiel": observation.impact_potentiel,
    }


def infer_observation_reasoning(observations: Iterable[AuditObservation]) -> dict[str, ObservationReasoning]:
    items = list(observations)
    if not items:
        return {}

    llm = get_chat_llm()
    payload = [_obs_to_dict(obs) for obs in items]
    control_refs = {obs.controle_ref.upper().strip() for obs in items if obs.controle_ref}
    subset = {ref: CONTROL_CATALOG.get(ref, {}) for ref in sorted(control_refs) if ref in CONTROL_CATALOG}
    if not subset:
        subset = CONTROL_CATALOG

    prompt = _PROMPT.format(
        observations_json=json.dumps(payload, ensure_ascii=False, indent=2),
        control_catalog_json=json.dumps(subset, ensure_ascii=False, indent=2),
    )

    response = llm.invoke(prompt)
    parsed = extract_json_from_response(response.content)
    if not isinstance(parsed, list):
        raise ValueError("Observation reasoning agent did not return a JSON list.")

    result: dict[str, ObservationReasoning] = {}
    for row in parsed:
        model = ObservationReasoning.model_validate(row)
        if model.observation_id:
            result[model.observation_id] = model
    return result

