from __future__ import annotations

import json
from typing import Iterable

from app.domain.itgc_control_catalog import CONTROL_CATALOG
from app.models.audit_input import AuditObservation
from app.models.observation_reasoning import ObservationReasoning
from app.models.priority_reasoning import PriorityReasoning
from app.services.llm_clients import get_chat_llm
from app.utils.json_parser import extract_json_from_response


# NOTE: These prompts are formatted via .format(...). Any literal JSON braces must be escaped.
_OBSERVATION_REASONING_PROMPT = """
Tu es un auditeur ITGC senior (style cabinet type PwC).

Objectif: pour CHAQUE observation, produire une analyse d'audit structurÃ©e et actionnable.

RÃ¨gles:
1) Base-toi uniquement sur les informations fournies dans l'observation (constat, procÃ©dure compensatoire, commentaire auditeur, controle_ref, application).
2) Standardise l'analyse selon le catalogue de contrÃ´les fourni (CONTROL_CATALOG). Les risques et recommandations doivent Ãªtre cohÃ©rents avec le controle_ref.
3) Tu peux infÃ©rer le risque / impact / cause racine de faÃ§on gÃ©nÃ©rique (ITGC), mais la justification de prioritÃ© doit citer des faits du constat (chiffres, occurrences, taille d'Ã©chantillon, absence explicite, etc.).
4) Ne jamais inventer des Ã©lÃ©ments probants (dates, nombres, outils) qui ne figurent pas dans l'observation.
5) La prioritÃ© doit Ãªtre une des valeurs: Critical, High, Medium, Low.
6) Le ton de la recommandation doit Ãªtre formel, concret, et orientÃ© contrÃ´le (verbe d'action + mÃ©canisme de preuve).
7) Si le controle_ref n'est pas reconnu, appliquer les bonnes pratiques ITGC les plus proches sans inventer de spÃ©cificitÃ©s.

SchÃ©ma JSON attendu (liste, 1 Ã©lÃ©ment par observation, sans markdown):
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

Regles de qualite Big Four:
- Ne repete pas le constat; transforme les faits en analyse.
- Separe le scenario de risque, l'impact metier, l'impact controle interne, l'impact conformite, la cause racine et les facteurs aggravants.
- Reprends les faits chiffres disponibles dans l'analyse lorsque c'est pertinent.
- La recommandation doit etre auditable: action immediate, action structurelle, responsable, preuve attendue et mecanisme de suivi.
- Evite toute recommandation vague si elle ne precise pas owner, preuve et controle de suivi.

Champs additionnels obligatoires dans chaque objet JSON:
"risk_scenario", "business_impact", "control_impact", "compliance_impact", "aggravating_factors",
"immediate_action", "structural_action", "owner", "evidence_expected", "follow_up_mechanism".

Exemple attendu APD post-depart:
- risk_scenario: "Le maintien de comptes actifs apres depart sur l'application critique expose l'entite a l'utilisation non autorisee d'identifiants appartenant a d'anciens collaborateurs."
- business_impact: "L'exposition est accrue lorsque des connexions post-depart portent sur des comptes clients ou operations sensibles, pouvant conduire a des operations non legitimes, une consultation de donnees sensibles et une perte de tracabilite."
- control_impact: "Le controle de cycle de vie des habilitations ne permet pas de garantir la revocation exhaustive et rapide des acces."
- root_cause: "Absence de rapprochement formel, tracable et periodique entre mouvements RH et comptes actifs applicatifs."
- recommendation: "Formaliser un processus RH/IT de revocation des acces, avec notification systematique des departs, delai cible de desactivation, accuse de traitement IT, rapprochement periodique RH/comptes actifs et conservation des preuves."

Observations:
{observations_json}

CONTROL_CATALOG (standard attendu):
{control_catalog_json}
""".strip()


_PRIORITY_REASONING_PROMPT = """
Tu es un auditeur ITGC senior.

TÃ¢che: classer la prioritÃ© d'une observation en te comportant comme un auditeur (raisonnement + cohÃ©rence),
et NON comme un moteur de mots-clÃ©s.

Tu dois retourner une prioritÃ© parmi: Critical, High, Medium, Low.

RÃ¨gles d'audit (guidelines, non exhaustives):
- AccÃ¨s non autorisÃ© / comptes actifs post-dÃ©part avec activitÃ© -> High ou Critical
- Conflits SoD avec exposition financiÃ¨re ou transactions auto-validÃ©es -> Critical (ou High si faible exposition)
- Comptes privilÃ©giÃ©s/DBA partagÃ©s en production -> au moins High
- PRA/PCA non testÃ© depuis > 12 mois sur application critique -> au moins High
- Retard de correctifs critiques / vulnÃ©rabilitÃ©s -> au moins High
- Absence de recertification d'accÃ¨s privilÃ©giÃ©s depuis > 12 mois -> High
- Faiblesses de contrÃ´le sans impact immÃ©diat, mais significatives -> Medium
- Ã‰carts mineurs / faible exposition -> Low

Contraintes:
1) Utilise uniquement les Ã©lÃ©ments fournis dans l'observation (constat, procÃ©dure compensatoire, contrÃ´le, contexte).
2) La justification doit citer des faits du constat (chiffres, %, occurrences, durÃ©e, taille d'Ã©chantillon, absence explicite).
3) Ne jamais inventer des preuves.

Sortie attendue: JSON (liste, 1 Ã©lÃ©ment par observation, sans markdown)
[
  {{
    "observation_id": "...",
    "priority": "Critical|High|Medium|Low",
    "priority_justification": "1 phrase courte, factuelle, reliant la prioritÃ© aux Ã©lÃ©ments probants du constat."
  }}
]

Observations:
{observations_json}

CONTROL_CATALOG (pour contexte de criticitÃ©):
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


def _control_catalog_subset(observations: Iterable[AuditObservation]) -> dict:
    control_refs = {obs.controle_ref.upper().strip() for obs in observations if obs.controle_ref}
    subset = {ref: CONTROL_CATALOG.get(ref, {}) for ref in sorted(control_refs) if ref in CONTROL_CATALOG}
    return subset or CONTROL_CATALOG


def _invoke_reasoning_prompt(prompt_template: str, observations: list[AuditObservation]) -> list:
    llm = get_chat_llm()
    payload = [_obs_to_dict(obs) for obs in observations]
    prompt = prompt_template.format(
        observations_json=json.dumps(payload, ensure_ascii=False, indent=2),
        control_catalog_json=json.dumps(_control_catalog_subset(observations), ensure_ascii=False, indent=2),
    )
    parsed = extract_json_from_response(llm.invoke(prompt).content)
    if isinstance(parsed, dict):
        for key in ("observations", "reasoning", "items", "results", "data"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
    if not isinstance(parsed, list):
        raise ValueError("Reasoning agent did not return a JSON list.")
    return parsed


def infer_observation_reasoning(observations: Iterable[AuditObservation]) -> dict[str, ObservationReasoning]:
    items = list(observations)
    if not items:
        return {}

    result: dict[str, ObservationReasoning] = {}
    for row in _invoke_reasoning_prompt(_OBSERVATION_REASONING_PROMPT, items):
        model = ObservationReasoning.model_validate(row)
        if model.observation_id:
            result[model.observation_id] = model
    return result


def infer_priority_reasoning(observations: Iterable[AuditObservation]) -> dict[str, PriorityReasoning]:
    items = list(observations)
    if not items:
        return {}

    result: dict[str, PriorityReasoning] = {}
    for row in _invoke_reasoning_prompt(_PRIORITY_REASONING_PROMPT, items):
        model = PriorityReasoning.model_validate(row)
        if model.observation_id:
            result[model.observation_id] = model
    return result
