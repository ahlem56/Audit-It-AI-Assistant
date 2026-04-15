from __future__ import annotations

import json
from typing import Iterable

from app.domain.itgc_control_catalog import CONTROL_CATALOG
from app.models.audit_input import AuditObservation
from app.models.priority_reasoning import PriorityReasoning
from app.services.llm_clients import get_chat_llm
from app.utils.json_parser import extract_json_from_response


# NOTE: formatted using .format(...). Escape JSON braces.
_PROMPT = """
Tu es un auditeur ITGC senior.

Tâche: classer la priorité d'une observation en te comportant comme un auditeur (raisonnement + cohérence),
et NON comme un moteur de mots-clés.

Tu dois retourner une priorité parmi: Critical, High, Medium, Low.

Règles d'audit (guidelines, non exhaustives):
- Accès non autorisé / comptes actifs post-départ avec activité -> High ou Critical
- Conflits SoD avec exposition financière ou transactions auto-validées -> Critical (ou High si faible exposition)
- Comptes privilégiés/DBA partagés en production -> au moins High
- PRA/PCA non testé depuis > 12 mois sur application critique -> au moins High
- Retard de correctifs critiques / vulnérabilités -> au moins High
- Absence de recertification d'accès privilégiés depuis > 12 mois -> High
- Faiblesses de contrôle sans impact immédiat, mais significatives -> Medium
- Écarts mineurs / faible exposition -> Low

Contraintes:
1) Utilise uniquement les éléments fournis dans l'observation (constat, procédure compensatoire, contrôle, contexte).
2) La justification doit citer des faits du constat (chiffres, %, occurrences, durée, taille d'échantillon, absence explicite).
3) Ne jamais inventer des preuves.

Sortie attendue: JSON (liste, 1 élément par observation, sans markdown)
[
  {{
    "observation_id": "...",
    "priority": "Critical|High|Medium|Low",
    "priority_justification": "1 phrase courte, factuelle, reliant la priorité aux éléments probants du constat."
  }}
]

Observations:
{observations_json}

CONTROL_CATALOG (pour contexte de criticité):
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


def infer_priority_reasoning(observations: Iterable[AuditObservation]) -> dict[str, PriorityReasoning]:
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
        raise ValueError("Priority reasoning agent did not return a JSON list.")

    result: dict[str, PriorityReasoning] = {}
    for row in parsed:
        model = PriorityReasoning.model_validate(row)
        if model.observation_id:
            result[model.observation_id] = model
    return result

