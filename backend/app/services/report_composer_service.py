from __future__ import annotations

from collections import Counter, defaultdict
import unicodedata
import logging
import re

from app.agents.priority_agent import classify_priority, enforce_min_priority
from app.agents.priority_agent import VALID_PRIORITIES
from app.agents.observation_reasoning_agent import infer_observation_reasoning
from app.agents.priority_reasoning_agent import infer_priority_reasoning
from app.services.observation_reasoning_validator import validate_reasoning
from app.services.priority_reasoning_validator import validate_priority_reasoning
from app.services.recommendation_validator import validate_recommendation
from app.utils.french_normalizer import normalize_french
from app.models.audit_input import AuditObservation, StructuredAuditInput
from app.domain.itgc_control_catalog import CONTROL_CATALOG, PROCESS_LABELS
from app.models.report_sections import (
    AuditReportOutput,
    ControlMatrixEntry,
    CoveredControl,
    DetailedFinding,
    KeyFigure,
    PrioritySummaryItem,
    ProcessSummary,
)

logger = logging.getLogger(__name__)

FIXED_AUDIT_APPROACH = [
    "Prise de connaissance de l’environnement informatique de l’entité et des évolutions significatives de l’exercice.",
    "Entretiens avec les interlocuteurs clés, analyse documentaire et collecte des éléments probants nécessaires à la revue.",
    "Exécution de tests de contrôles par sondage et observation sur les processus de gestion des accès, des changements et de l’exploitation informatique.",
    "Synthèse des constats, évaluation du niveau de maîtrise et formalisation des recommandations à destination du management.",
]

PRIORITY_LABELS = {
    "Critical": "Critique",
    "High": "Élevée",
    "Medium": "Moyenne",
    "Low": "Faible",
}


def _priority_rank(priority: str) -> int:
    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return order.get(priority, 99)


def _format_priority(priority: str) -> str:
    return PRIORITY_LABELS.get(priority, priority)


def _deduplicate(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _keyword_text(*values: str) -> str:
    text = " ".join(value for value in values if value)
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return normalized.lower()


def _normalize_process_codes(values: list[str]) -> list[str]:
    """
    Mission inputs sometimes carry human labels (e.g., "APD – Gestion des accès") instead of codes ("APD").
    This helper extracts canonical process codes so filtering doesn't accidentally exclude everything.
    """
    codes: list[str] = []
    for raw in values or []:
        value = (raw or "").strip()
        if not value:
            continue
        upper = value.upper()
        for code in ("APD", "PC", "CO"):
            if code in upper:
                if code not in codes:
                    codes.append(code)
                break
    return codes


def _focus_label(label: str) -> str:
    lowered = label.lower()
    if lowered.startswith("gestion "):
        return f"la {lowered}"
    if lowered.startswith("exploitation "):
        return f"l'{lowered}"
    return lowered


def _default_objectives(audit_input: StructuredAuditInput) -> list[str]:
    processes = audit_input.mission.processus_couverts or ["APD", "PC", "CO"]
    labels = [PROCESS_LABELS.get(code, code) for code in _normalize_process_codes(processes) or processes]
    joined_processes = ", ".join(labels)
    return [
        "Apprécier le niveau de maîtrise des contrôles généraux informatiques sur le périmètre audité.",
        "Évaluer la capacité du dispositif de contrôle interne IT à sécuriser la fiabilité, l’intégrité et la disponibilité des traitements.",
        f"Analyser les processus couverts par la mission, en particulier {joined_processes}.",
    ]


def _clean_sentence(text: str) -> str:
    value = " ".join((text or "").split())
    value = value.replace("risque de risque de", "risque de").replace("..", ".").replace(" .", ".").replace(" ,", ",")
    return normalize_french(value).strip()


def _describe_focus_areas(findings: list[DetailedFinding]) -> str:
    labels = _deduplicate([item.domain or PROCESS_LABELS.get(item.reference.split("-")[0], "") for item in findings])
    if not labels:
        return "les processus ITGC couverts"
    if len(labels) == 1:
        return _focus_label(labels[0])
    if len(labels) == 2:
        return f"{_focus_label(labels[0])} et {_focus_label(labels[1])}"
    return ", ".join(_focus_label(label) for label in labels[:-1]) + f" et {_focus_label(labels[-1])}"


def _derive_risk_impact(observation: AuditObservation) -> str:
    explicit_risk = _first_non_empty(observation.risque_associe)
    if explicit_risk:
        return explicit_risk

    explicit_impact = _first_non_empty(observation.impact_potentiel)
    if explicit_impact:
        return explicit_impact

    text = _keyword_text(
        observation.titre_observation,
        observation.categorie_controle,
        observation.constat,
        observation.commentaire_auditeur,
    )

    if "post-depart" in text or "depart" in text or "actif" in text:
        return "Acces non autorise aux systemes et aux donnees sensibles."
    if "validation" in text or "autorisation" in text:
        return "Octroi d'acces ou execution de changements non autorises."
    if "sauvegarde" in text or "restauration" in text or "backup" in text:
        return "Perte de donnees ou indisponibilite prolongee des applications critiques."
    if "changement" in text or "production" in text or "deploi" in text:
        return "Changements non controles et alteration de l'environnement de production."
    if "incident" in text:
        return "Resolution tardive des incidents et degradation de la continuite de service."
    return "Acces non autorise, fraude ou indisponibilite des traitements."


def _derive_business_impact(observation: AuditObservation) -> str:
    explicit_impact = _first_non_empty(observation.impact_potentiel)
    if explicit_impact:
        return explicit_impact

    text = _keyword_text(
        observation.titre_observation,
        observation.categorie_controle,
        observation.constat,
        observation.commentaire_auditeur,
    )

    if "post-depart" in text or "depart" in text or "actif" in text:
        return "Fuite de donnees sensibles et utilisation frauduleuse des comptes."
    if "validation" in text or "autorisation" in text:
        return "Non-conformite aux procedures internes et atteinte a l'integrite des donnees."
    if "sauvegarde" in text or "restauration" in text or "backup" in text:
        return "Interruption des operations et perte definitive de donnees critiques."
    if "changement" in text or "production" in text or "deploi" in text:
        return "Interruption des operations metier et correction couteuse en production."
    if "incident" in text:
        return "Interruption de service, non-respect des engagements et perte financiere."
    return "Perte financiere, non-conformite et atteinte a l'integrite des traitements."


def _expected_control_text(observation: AuditObservation) -> str:
    catalog_control = CONTROL_CATALOG.get(observation.controle_ref.upper())
    if catalog_control and catalog_control.get("description"):
        return catalog_control["description"]
    return observation.controle_attendu or observation.titre_observation


def _impact_level(observation: AuditObservation) -> str:
    text = _keyword_text(
        observation.impact_potentiel,
        observation.constat,
        observation.titre_observation,
        observation.categorie_controle,
    )
    high_markers = (
        "post-depart",
        "depart",
        "non autorise",
        "privilegie",
        "administrateur",
        "restauration",
        "sauvegarde",
        "production",
        "transaction critique",
        "droit sensible",
    )
    medium_markers = ("incident", "sla", "mot de passe", "parametrage", "revue", "recertification")
    if any(marker in text for marker in high_markers):
        return "High"
    if any(marker in text for marker in medium_markers):
        return "Medium"
    return "Low"


def _split_scope_applications(audit_input: StructuredAuditInput) -> list[str]:
    mission_apps = _deduplicate(audit_input.mission.applications or [])
    from_observations = _deduplicate(
        [observation.application for observation in audit_input.observations if observation.application]
    )
    return mission_apps or from_observations


_NUM_RE = re.compile(r"\b\d+\b")


def _truncate_at_word_boundary(text: str, max_len: int) -> str:
    value = " ".join((text or "").split()).strip()
    if len(value) <= max_len:
        return value
    cut = value[: max_len + 1]
    last_space = cut.rfind(" ")
    if last_space <= 0:
        return value[:max_len].rstrip()
    return value[:last_space].rstrip()


def _auto_priority_justification(observation: AuditObservation, *, priority: str) -> str:
    constat = " ".join((observation.constat or "").split()).strip()
    if not constat:
        return ""

    priority_label = _format_priority(priority).lower()

    # Prefer a clean excerpt from the constat (first sentence-like chunk) instead of raw number dumps.
    excerpt = constat
    if "." in constat:
        excerpt = constat.split(".", 1)[0].strip()
    excerpt = _truncate_at_word_boundary(excerpt, 240).rstrip(".")

    lowered = _keyword_text(constat, observation.titre_observation, observation.categorie_controle)
    if "aucun" in lowered or "aucune" in lowered or "absence" in lowered:
        return _clean_sentence(
            f"La priorite {priority_label} est justifiee par l'absence explicite de controle ou de preuve, telle que decrite dans le constat: {excerpt}."
        )

    numbers = sorted(set(_NUM_RE.findall(constat)))
    if numbers:
        return _clean_sentence(
            f"La priorite {priority_label} est justifiee par les elements factuels releves dans le constat, notamment: {excerpt}."
        )

    return _clean_sentence(
        f"La priorite {priority_label} est justifiee par la faiblesse de controle decrite dans le constat: {excerpt}."
    )


def _build_preamble(audit_input: StructuredAuditInput) -> str:
    mission = audit_input.mission
    entity_name = mission.entite_auditee or "l'entite auditee"
    period = mission.periode or "consideree"
    mission_type = mission.type_mission or "ITGC"
    return (
        f"Le présent document restitue les principaux constats issus de notre revue des contrôles généraux informatiques conduite chez "
        f"{entity_name} sur la période {period}. "
        f"Cette intervention s’inscrit dans le cadre d’une mission {mission_type} et a pour objectif d’apprécier "
        f"le niveau de maîtrise du dispositif de contrôle interne informatique sur le périmètre retenu. "
        f"Le présent support est confidentiel et destiné exclusivement aux parties prenantes de la mission."
    )


def _build_scope_summary(audit_input: StructuredAuditInput) -> str:
    mission = audit_input.mission
    applications = ", ".join(_split_scope_applications(audit_input)) or mission.perimetre_intervention
    process_codes = _normalize_process_codes(mission.processus_couverts or [])
    processes = ", ".join(PROCESS_LABELS.get(code, code) for code in process_codes) or "les processus ITGC couverts"
    return (
        f"Nos travaux ont porté sur les applications suivantes: {applications}. "
        f"Le périmètre couvre principalement {processes}. Les diligences ont été réalisées au travers d’entretiens, "
        f"d’analyses documentaires et de tests de contrôles ciblés."
    )


_GENERIC_RECO_MARKERS = (
    "definir un plan d'action",
    "plan d'action cible",
    "traiter durablement le constat",
    "en assurer le suivi",
)


def _is_generic_recommendation(text: str) -> bool:
    lowered = _keyword_text(text or "")
    return any(marker in lowered for marker in _GENERIC_RECO_MARKERS)


def _catalog_item(reference: str) -> dict[str, str]:
    return CONTROL_CATALOG.get((reference or "").upper().strip(), {}) or {}


def _catalog_recommendation(reference: str) -> str:
    item = _catalog_item(reference)
    return str(item.get("recommendation_guidance") or "").strip()


def _build_recommendation(observation: AuditObservation) -> str:
    explicit_recommendation = _first_non_empty(observation.recommandation_proposee)
    if explicit_recommendation:
        return explicit_recommendation

    ref = observation.controle_ref.upper()

    # Authoritative fallback per control (control-aware).
    catalog_reco = _catalog_recommendation(ref)
    if catalog_reco:
        return catalog_reco

    if observation.controle_attendu:
        return f"Renforcer le dispositif afin d’assurer le respect effectif du contrôle attendu suivant: {observation.controle_attendu}."

    # Minimal generic fallback (only when the control is unknown / uncatalogued).
    prefix = (ref or "").split("-", 1)[0].strip().upper()
    if prefix == "APD":
        return "Renforcer les contrôles d’accès (validation, recertification et révocation) et formaliser les preuves associées."
    if prefix == "PC":
        return "Renforcer la gestion des changements (tests, validations et traçabilité) et formaliser les preuves associées."
    if prefix == "CO":
        return "Renforcer les contrôles d’exploitation (sauvegardes, supervision et continuité) et formaliser les preuves associées."
    return "Définir un plan d’action priorisé afin de traiter durablement le constat et d’en assurer le suivi."


def _build_management_summary(
    observation: AuditObservation,
    *,
    priority: str,
    risk: str,
    impact: str,
    root_cause: str = "",
    priority_justification: str = "",
) -> str:
    application = observation.application or "l'application concernee"
    constat = observation.constat.rstrip(".")
    impact_value = (impact or _derive_business_impact(observation)).rstrip(".")
    risk_value = (risk or _derive_risk_impact(observation)).rstrip(".")
    cause_clause = f" La cause racine probable identifiee est: {root_cause.rstrip('.') }." if root_cause else ""
    justification_clause = f" Justification: {priority_justification.rstrip('.') }." if priority_justification else ""
    return _clean_sentence(
        f"Nous avons releve sur {application.lower()} le point suivant: {constat}. "
        f"Cette situation traduit une faiblesse du controle {observation.controle_ref} et expose l'organisation a un risque de {risk_value.lower()} "
        f"pouvant entrainer {impact_value.lower()}."
        f"{cause_clause}{justification_clause}"
        f"Au regard de son effet potentiel sur le dispositif de controle interne, la priorite retenue est {_format_priority(priority).lower()}."
    )


def _sharpen_title(title: str, *, reference: str = "", constat: str = "", category: str = "") -> str:
    value = " ".join((title or "").split()).strip()
    if not value:
        return ""

    lowered = _keyword_text(value, constat, category, reference)

    # Theme-driven sharpening (prevents ref-only mismatches).
    if any(k in lowered for k in ("post-depart", "post depart", "apres depart", "après départ", "depart", "départ", "ancien collaborateur", "anciens collaborateurs", "ancien prestataire", "n'intervenant plus", "n intervenant plus")) and any(k in lowered for k in ("dba", "root", "privileg", "privilégié", "administrateur")):
        return "Comptes privilégiés non révoqués après départ"
    if any(k in lowered for k in ("post-depart", "post depart", "apres depart", "après départ", "depart", "départ", "ancien collaborateur", "anciens collaborateurs", "ancien prestataire", "n'intervenant plus", "n intervenant plus")) and "compte" in lowered:
        return "Comptes actifs post-départ"
    if any(k in lowered for k in ("recertification", "re certification")):
        return "Recertification des droits d'accès non réalisée"
    if any(k in lowered for k in ("mfa", "multi facteur", "authentification forte", "2fa")):
        return "Authentification multifacteur non déployée"
    if any(k in lowered for k in ("incident", "ticketing", "ticket", "delai de resolution", "délai de résolution")):
        return "Processus de gestion des incidents non formalisé"
    if any(k in lowered for k in ("sod", "separation des fonctions", "séparation des fonctions", "incompatib", "auto-valid", "paiement")):
        return "Séparation des fonctions non respectée"
    if any(k in lowered for k in ("root", "compte root")) and any(k in lowered for k in ("partag", "shared", "sans tracabilite", "sans traçabilité", "journalisation")):
        return "Compte root partagé sans traçabilité individuelle"
    if any(k in lowered for k in ("dba", "sap hana")) and any(k in lowered for k in ("supervision", "revue", "surveillance")):
        return "Supervision des comptes DBA insuffisante"
    if any(k in lowered for k in ("dba", "base de donnees", "base de données")) and any(k in lowered for k in ("partag", "shared")):
        return "Comptes DBA partagés en production"
    if any(k in lowered for k in ("mot de passe", "mots de passe", "complexit", "verrouillage")):
        return "Politique de mots de passe non conforme"
    if any(k in lowered for k in ("pra", "pca", "plan de reprise", "reprise d activite", "reprise d'activité")) and any(k in lowered for k in ("non teste", "pas teste", "aucun test")):
        return "PRA non testé et documentation à actualiser"
    if any(k in lowered for k in ("patch", "correctif", "vulnerabil")):
        return "Correctifs de sécurité appliqués avec retard"
    if any(k in lowered for k in ("capacite", "capacity", "stockage")):
        return "Pilotage de la capacité non formalisé"
    if any(k in lowered for k in ("transport", "dev", "prod")) and any(k in lowered for k in ("tracabil", "traçabil", "sans demande")):
        return "Traçabilité des déploiements insuffisante"

    # Generic sharpening for common patterns.
    if lowered.startswith("absence de "):
        trimmed = value[len("Absence de ") :].strip()
        return trimmed[:1].upper() + trimmed[1:] if trimmed else value
    return value


def _resolve_effective_reference(observation: AuditObservation) -> str:
    original = (observation.controle_ref or "").upper().strip()
    text = _keyword_text(
        observation.titre_observation,
        observation.categorie_controle,
        observation.constat,
    )

    if any(
        marker in text
        for marker in (
            "post-depart",
            "post départ",
            "quitte l'organisation",
            "quitte l entreprise",
            "quitté l'entreprise",
            "desactivation des comptes",
            "désactivation des comptes",
            "depart des utilisateurs",
            "ancien collaborateur",
            "anciens collaborateurs",
            "ancien prestataire",
            "anciens prestataires",
            "n'intervenant plus",
            "n intervenant plus",
        )
    ):
        return "APD-02"
    if any(marker in text for marker in ("incident", "ticketing", "ticket", "delai de resolution", "délai de résolution", "escalade", "cause racine")):
        return "CO-02"
    if any(marker in text for marker in ("dba", "sap hana", "root", "superuser", "compte privilegie", "compte privilégié", "compte partage", "compte partagé", "compte generique", "compte générique")):
        return "APD-03"
    if any(marker in text for marker in ("recertification", "re certification", "revue periodique", "revue des acces")):
        return "APD-04"
    if any(marker in text for marker in ("mot de passe", "mots de passe", "complexite", "complexité", "verrouillage", "tentatives infructueuses")):
        return "APD-05"
    if any(marker in text for marker in ("absence d'un environnement de test", "absence de separation des environnements", "absence de séparation des environnements", "environnement de test distinct", "developpement et production")):
        return "PC-02"
    if any(marker in text for marker in ("isae 3402", "sla", "prestataire", "prestations externalisees", "prestations externalisées")):
        return "CO-03"
    return original


def _looks_like_fact_restatement(candidate: str, observation: AuditObservation) -> bool:
    text = " ".join((candidate or "").split()).strip()
    if not text:
        return False

    normalized_candidate = _keyword_text(text)
    normalized_constat = _keyword_text(observation.constat, observation.titre_observation)

    if not normalized_constat:
        return False

    candidate_tokens = {token for token in normalized_candidate.split() if len(token) > 3}
    constat_tokens = {token for token in normalized_constat.split() if len(token) > 3}
    if not candidate_tokens:
        return False

    overlap_ratio = len(candidate_tokens & constat_tokens) / len(candidate_tokens)
    has_raw_numbers = bool(_NUM_RE.search(text))
    starts_like_fact = normalized_candidate.startswith(("presence de", "absence de", "plusieurs", "trois", "quatre", "cinq"))
    return overlap_ratio >= 0.65 or (has_raw_numbers and overlap_ratio >= 0.45) or starts_like_fact


def _risk_guidance_for_control(reference: str) -> str:
    item = CONTROL_CATALOG.get((reference or "").upper().strip())
    if not item:
        return ""
    return str(item.get("risk_guidance") or "").strip()


def _risk_seems_off_topic(risk_text: str, reference: str) -> bool:
    text = _keyword_text(risk_text)
    ref = (reference or "").upper().strip()

    if ref == "CO-02":
        # Incident management: avoid change-management or external-provider wording.
        return any(marker in text for marker in ("changement", "mise en production", "recette", "developpement", "prestataire", "fournisseur", "contractualisation"))
    if ref.startswith("PC-"):
        # Change management: avoid incident-specific wording.
        return any(marker in text for marker in ("incident", "sla", "delai de resolution"))
    if ref == "APD-03":
        return any(marker in text for marker in ("mot de passe", "verrouillage", "complexite"))
    return False


def _moderate_priority(reference: str, observation: AuditObservation, priority: str) -> str:
    if priority != "Critical":
        return priority

    text = _keyword_text(
        reference,
        observation.titre_observation,
        observation.constat,
        observation.application,
        observation.categorie_controle,
        observation.impact_potentiel,
    )
    amount = 0.0
    try:
        amount = max([float(value) for value in _NUM_RE.findall(observation.constat or "")] or [0.0])
    except Exception:
        amount = 0.0

    hard_critical = False
    if any(marker in text for marker in ("post-depart", "post depart", "apres depart", "depart")) and any(marker in text for marker in ("connexion", "connexions", "telecharg", "download", "exfil")):
        hard_critical = True
    if any(marker in text for marker in ("sod", "separation des fonctions", "incompatib", "validation paiement", "paiement")) and amount >= 20:
        hard_critical = True
    if (reference or "").upper().strip() in {"CO-01", "CO-05", "CO-07"} and any(marker in text for marker in ("aucun test", "non teste", "pas teste")) and any(marker in text for marker in ("finance", "sap", "erp", "paiement")):
        hard_critical = True
    if any(marker in text for marker in ("vulnerabilite critique", "vulnérabilité critique", "sql injection", "escalade de privil", "escalade de privilège")):
        hard_critical = True

    return "Critical" if hard_critical else "High"


def _build_detailed_findings(audit_input: StructuredAuditInput) -> list[DetailedFinding]:
    findings: list[DetailedFinding] = []

    reasoning_map = {}
    priority_reasoning_map = {}
    try:
        reasoning_map = infer_observation_reasoning(audit_input.observations)
    except Exception as exc:
        logger.warning("Observation reasoning layer failed; falling back to deterministic rules.", exc_info=exc)

    try:
        priority_reasoning_map = infer_priority_reasoning(audit_input.observations)
    except Exception as exc:
        logger.warning("Priority reasoning layer failed; falling back to deterministic rules.", exc_info=exc)

    for observation in audit_input.observations:
        if not _is_reportable_observation(observation):
            continue

        effective_reference = _resolve_effective_reference(observation)
        reasoning = reasoning_map.get(observation.observation_id)
        priority_reasoning = priority_reasoning_map.get(observation.observation_id)
        inferred_risk = (reasoning.risk if reasoning else "").strip()
        inferred_impact = (reasoning.impact if reasoning else "").strip()
        inferred_root_cause = (reasoning.root_cause if reasoning else "").strip() or _first_non_empty(observation.cause_racine)
        inferred_recommendation = (reasoning.recommendation if reasoning else "").strip()
        inferred_objective = (reasoning.recommendation_objective if reasoning else "").strip()
        inferred_steps = (reasoning.recommendation_steps if reasoning else []) or []
        inferred_justification = (reasoning.priority_justification if reasoning else "").strip()

        reasoning_ok = False
        if reasoning is not None:
            validation = validate_reasoning(observation, reasoning)
            reasoning_ok = validation.ok
            if not reasoning_ok:
                inferred_justification = ""

        priority_reasoning_ok = False
        inferred_priority = ""
        inferred_priority_justification = ""
        if priority_reasoning is not None:
            inferred_priority = (priority_reasoning.priority or "").strip()
            inferred_priority_justification = (priority_reasoning.priority_justification or "").strip()
            validation = validate_priority_reasoning(observation, priority_reasoning)
            priority_reasoning_ok = validation.ok
            if not priority_reasoning_ok:
                inferred_priority = ""
                inferred_priority_justification = ""

        risk_text = inferred_risk or _derive_risk_impact(observation)
        catalog_risk = _risk_guidance_for_control(effective_reference)
        if catalog_risk and (not inferred_risk or _risk_seems_off_topic(risk_text, effective_reference)):
            risk_text = catalog_risk
        if _looks_like_fact_restatement(risk_text, observation):
            risk_text = _derive_risk_impact(observation)

        impact_text = inferred_impact or _derive_business_impact(observation)
        if _looks_like_fact_restatement(impact_text, observation):
            impact_text = _derive_business_impact(observation)
        # Recommendation pipeline:
        # 1) LLM recommendation as the default.
        # 2) Validate recommendation coherence (vs control_ref) and specificity.
        # 3) If invalid/generic/off-topic, enforce CONTROL_CATALOG guidance (or minimal generic fallback).
        recommendation_text = inferred_recommendation.strip() if inferred_recommendation else _first_non_empty(observation.recommandation_proposee)
        reco_objective = inferred_objective
        reco_steps = inferred_steps

        reco_ok = False
        if recommendation_text:
            validation = validate_recommendation(observation.model_copy(update={"controle_ref": effective_reference}), recommendation_text)
            reco_ok = validation.ok

        if not reco_ok:
            recommendation_text = _build_recommendation(observation.model_copy(update={"controle_ref": effective_reference}))
            reco_objective = ""
            reco_steps = []

        priority = classify_priority(
            {
                "controle_ref": effective_reference,
                "reference": effective_reference,
                "title": observation.titre_observation,
                "condition": observation.constat,
                "risk_impact": observation.impact_potentiel,
                "impact": _impact_level(observation),
                "category": observation.categorie_controle,
                "recommendation": recommendation_text,
            }
        )
        if priority_reasoning_ok and inferred_priority in VALID_PRIORITIES:
            priority = inferred_priority

        # Final hard-minimum override layer.
        priority = enforce_min_priority(
            {
                "controle_ref": effective_reference,
                "reference": effective_reference,
                "title": observation.titre_observation,
                "condition": observation.constat,
                "application": observation.application,
                "category": observation.categorie_controle,
                "impact": observation.impact_potentiel,
            },
            priority,
        )
        priority = _moderate_priority(effective_reference, observation, priority)

        # Prefer LLM justification if it passed evidence validation AND the final priority matches it.
        if priority_reasoning_ok and inferred_priority_justification and inferred_priority == priority:
            priority_justification = inferred_priority_justification
        else:
            priority_justification = inferred_justification or _auto_priority_justification(observation, priority=priority)

        # Priority-aware enforcement: High/Critical must not be generic.
        if priority in {"Critical", "High"}:
            validation = validate_recommendation(observation.model_copy(update={"controle_ref": effective_reference}), recommendation_text)
            if (not validation.ok) or "recommendation_generic" in (validation.issues or []):
                recommendation_text = _build_recommendation(observation.model_copy(update={"controle_ref": effective_reference}))
                reco_objective = ""
                reco_steps = []

        findings.append(
            DetailedFinding(
                observation_id=observation.observation_id,
                reference=effective_reference,
                domain=observation.domaine_controle,
                category=observation.categorie_controle,
                application=observation.application,
                layer=observation.couche,
                owners=observation.responsables,
                title=_sharpen_title(
                    observation.titre_observation,
                    reference=effective_reference,
                    constat=observation.constat,
                    category=observation.categorie_controle,
                ),
                expected_control=_expected_control_text(observation.model_copy(update={"controle_ref": effective_reference})),
                finding=observation.constat,
                compensating_procedure=observation.procedure_compensatoire,
                risk_impact=risk_text,
                impact_detail=impact_text,
                root_cause=inferred_root_cause,
                recommendation=recommendation_text,
                recommendation_objective=reco_objective,
                recommendation_steps=[step for step in (reco_steps or []) if step and str(step).strip()],
                priority=priority,
                priority_justification=priority_justification,
                auditor_comment=observation.commentaire_auditeur,
                management_summary=_build_management_summary(
                    observation.model_copy(update={"controle_ref": effective_reference}),
                    priority=priority,
                    risk=risk_text,
                    impact=impact_text,
                    root_cause=inferred_root_cause,
                    priority_justification=priority_justification,
                ),
            )
        )
    return sorted(findings, key=lambda item: (_priority_rank(item.priority), item.reference, item.application, item.layer))


def _build_priority_summary(findings: list[DetailedFinding]) -> list[PrioritySummaryItem]:
    counts = Counter(finding.priority for finding in findings)
    total = sum(counts.values()) or 1
    ordered = ["Critical", "High", "Medium", "Low"]
    return [
        PrioritySummaryItem(
            priority=priority,
            count=counts.get(priority, 0),
            percentage=round((counts.get(priority, 0) / total) * 100, 1),
        )
        for priority in ordered
        if counts.get(priority, 0) > 0
    ]


def _normalize_matrix_status(value: str) -> str:
    lowered = _keyword_text(value)
    if "non applicable" in lowered:
        return "Non applicable"
    if "recommandation mineure" in lowered or "mineure" in lowered:
        return "Recommandation mineure"
    if "satisfais" in lowered and "non" not in lowered:
        return "Satisfaisant"
    if "non teste" in lowered:
        return "Non testé"
    if "non satisfais" in lowered:
        return "Non satisfaisant"
    return ""


def _is_reportable_observation(observation: AuditObservation) -> bool:
    status = _normalize_matrix_status(_first_non_empty(observation.statut_controle, observation.statut_validation))
    return status not in {"Satisfaisant", "Non testé", "Non applicable"}


def _scoped_control_references(audit_input: StructuredAuditInput) -> list[str]:
    process_codes = _normalize_process_codes(audit_input.mission.processus_couverts or [])
    scoped = [
        reference
        for reference, item in CONTROL_CATALOG.items()
        if not process_codes or (item.get("process", "").strip().upper() in process_codes)
    ]

    observed_refs: list[str] = []
    for observation in audit_input.observations:
        reference = _resolve_effective_reference(observation)
        if reference and reference not in scoped and reference not in observed_refs:
            observed_refs.append(reference)

    return sorted(_deduplicate(scoped + observed_refs))


def _build_control_matrix(audit_input: StructuredAuditInput, findings: list[DetailedFinding]) -> list[ControlMatrixEntry]:
    applications = _split_scope_applications(audit_input)
    finding_by_pair: dict[tuple[str, str], DetailedFinding] = {}
    for finding in findings:
        key = (finding.reference, finding.application)
        current = finding_by_pair.get(key)
        if current is None or _priority_rank(finding.priority) < _priority_rank(current.priority):
            finding_by_pair[key] = finding

    observed_refs: dict[str, AuditObservation] = {}
    for observation in audit_input.observations:
        ref = _resolve_effective_reference(observation)
        if ref and ref not in observed_refs:
            observed_refs[ref] = observation.model_copy(update={"controle_ref": ref})

    entries: list[ControlMatrixEntry] = []
    for reference in _scoped_control_references(audit_input):
        obs = observed_refs.get(reference) or AuditObservation(controle_ref=reference)
        process_code = (reference or "").split("-", 1)[0].strip().upper()
        control_description = _expected_control_text(obs)
        application_statuses = {application: "Satisfaisant" for application in applications}
        overall_priority = None

        for application in applications:
            pair = (reference, application)
            if pair in finding_by_pair:
                finding = finding_by_pair[pair]
                if finding.priority == "Low":
                    application_statuses[application] = "Recommandation mineure"
                else:
                    application_statuses[application] = f"Non satisfaisant ({_format_priority(finding.priority)})"
                if overall_priority is None or _priority_rank(finding.priority) < _priority_rank(overall_priority):
                    overall_priority = finding.priority

        for observation in audit_input.observations:
            effective_ref = _resolve_effective_reference(observation)
            if effective_ref != reference:
                continue
            application = (observation.application or "").strip()
            if application not in application_statuses:
                application_statuses[application] = "Satisfaisant"
            explicit_status = _normalize_matrix_status(_first_non_empty(observation.statut_controle, observation.statut_validation))
            if explicit_status:
                application_statuses[application] = explicit_status

        entries.append(
            ControlMatrixEntry(
                reference=reference,
                process=PROCESS_LABELS.get(process_code, process_code),
                control_description=control_description,
                application_statuses=application_statuses,
                overall_priority=overall_priority,
            )
        )

    return sorted(entries, key=lambda item: (item.process, item.reference))


def _build_key_figures(audit_input: StructuredAuditInput, findings: list[DetailedFinding]) -> list[KeyFigure]:
    applications = _split_scope_applications(audit_input)
    priority_summary = _build_priority_summary(findings)
    top_priority = priority_summary[0] if priority_summary else None
    process_codes = _normalize_process_codes(audit_input.mission.processus_couverts or [])
    return [
        KeyFigure(label="Applications auditees", value=str(len(applications)), commentary=", ".join(applications)),
        KeyFigure(label="Observations relevees", value=str(len(findings)), commentary="Constats valides issus de la feuille Observations"),
        KeyFigure(
            label="Processus couverts",
            value=str(len(process_codes)),
            commentary=", ".join(PROCESS_LABELS.get(code, code) for code in process_codes) or ", ".join(audit_input.mission.processus_couverts or []),
        ),
        KeyFigure(
            label="Priorite dominante",
            value=_format_priority(top_priority.priority) if top_priority else "N/A",
            commentary=f"{top_priority.count} observation(s)" if top_priority else "",
        ),
    ]


def _build_executive_highlights(findings: list[DetailedFinding]) -> list[str]:
    highlights = []
    for finding in findings[:3]:
        highlights.append(_clean_sentence(
            f"Sur {finding.application}, nous avons identifie {finding.title.lower()}, avec pour principal enjeu {finding.risk_impact.lower()} et une priorite {_format_priority(finding.priority).lower()}."
        ))
    return highlights


def _build_strengths(findings: list[DetailedFinding], audit_input: StructuredAuditInput) -> list[str]:
    strengths = [
        "Le perimetre de mission et les processus cibles sont clairement identifies dans la feuille Mission.",
    ]
    compensating = [finding for finding in findings if finding.compensating_procedure]
    if compensating:
        strengths.append("Des procedures compensatoires existent sur plusieurs constats, ce qui traduit une prise en compte partielle des risques.")
    if audit_input.mission.intervenants:
        strengths.append("Les interlocuteurs cles de la mission sont identifies, facilitant la gouvernance des plans d'action.")
    return strengths


def _build_watch_points(findings: list[DetailedFinding]) -> list[str]:
    watch_points = []
    for finding in findings[:4]:
        watch_points.append(_clean_sentence(
            f"{finding.reference} - {finding.title}: {finding.finding}. Impact potentiel: {finding.risk_impact}"
        ))
    return watch_points


def _derive_maturity_level(findings: list[DetailedFinding]) -> str:
    critical_count = len([item for item in findings if item.priority == "Critical"])
    high_count = len([item for item in findings if item.priority == "High"])

    if critical_count >= 2:
        return "faible"
    if critical_count == 1 or high_count >= 2:
        return "faible a moderee"
    if high_count == 1:
        return "moderee"
    return "satisfaisante"


def _build_maturity_assessment(findings: list[DetailedFinding]) -> str:
    maturity = _derive_maturity_level(findings)
    focus_areas = _describe_focus_areas(findings)
    return (
        f"Le dispositif de controle interne IT presente un niveau de maturite global {maturity}. "
        f"Les principales faiblesses se concentrent sur {focus_areas}."
    )


def _build_priority_insight(findings: list[DetailedFinding]) -> str:
    counts = Counter(item.priority for item in findings)
    dominant_priority, dominant_count = counts.most_common(1)[0]
    dominant_process, dominant_process_count = Counter(
        PROCESS_LABELS.get(item.reference.split("-")[0], item.domain or item.reference)
        for item in findings
    ).most_common(1)[0]
    return _clean_sentence(
        f"Le risque est principalement concentre sur les observations de priorite {_format_priority(dominant_priority).lower()}, "
        f"qui representent {dominant_count} point(s) sur {len(findings)}. "
        f"Le principal foyer de risque du perimetre audite concerne {dominant_process.lower()} avec {dominant_process_count} observation(s)."
    )


def _build_strategic_priorities(findings: list[DetailedFinding]) -> list[str]:
    priorities = []
    executive_findings = [item for item in findings if item.priority in {"Critical", "High"}][:3]
    if not executive_findings:
        return priorities

    # Distinct management messages (avoid repetition).
    first = executive_findings[0]
    priorities.append(
        _clean_sentence(
            f"Remédier en priorité aux faiblesses critiques/élevées (ex: {first.reference} - {first.application})."
        )
    )

    access_refs = [f.reference for f in executive_findings if (f.reference or "").upper().startswith("APD-")]
    if access_refs:
        priorities.append(_clean_sentence(f"Sécuriser les contrôles d’accès ({', '.join(sorted(set(access_refs))) })."))

    change_refs = [f.reference for f in executive_findings if (f.reference or "").upper().startswith("PC-")]
    if change_refs:
        priorities.append(_clean_sentence(f"Renforcer le cadre de gestion des changements ({', '.join(sorted(set(change_refs))) })."))

    ops_refs = [f.reference for f in executive_findings if (f.reference or "").upper().startswith("CO-")]
    if ops_refs and len(priorities) < 3:
        priorities.append(_clean_sentence(f"Renforcer l'exploitation informatique et le pilotage (ex: {', '.join(sorted(set(ops_refs))) })."))

    # Cap to 3 bullets.
    priorities = priorities[:3]
    return priorities


def _theme_for_finding(finding: DetailedFinding) -> str:
    text = _keyword_text(
        finding.reference,
        finding.domain,
        finding.category,
        finding.title,
        finding.root_cause,
        finding.risk_impact,
        finding.finding,
        finding.recommendation,
    )

    if any(marker in text for marker in ("apd-01", "post-depart", "depart", "revocation", "leaver", "mobilite")):
        return "IAM - Joiner/Mover/Leaver"
    if any(marker in text for marker in ("apd-07", "validation", "autorisation", "approbation", "workflow", "ticketing")):
        return "IAM - Workflow d'approbation"
    if any(marker in text for marker in ("apd-02", "recertification", "revue", "droit sensible", "superuser", "administrateur")):
        return "IAM - Recertification des acces"
    if any(marker in text for marker in ("apd-03", "compte generique", "partage", "shared", "trace", "journal", "log")):
        return "IAM - Comptes privilegies / PAM"
    if any(marker in text for marker in ("apd-04", "mfa", "2fa", "authentification", "verrouillage", "bruteforce")):
        return "Sécurité - Authentification"
    if any(marker in text for marker in ("apd-06", "mot de passe", "password", "complexite", "expiration")):
        return "Sécurité - Politique de mots de passe"
    if any(marker in text for marker in ("apd-05", "sod", "separation des fonctions", "incompatib", "paiement")):
        return "IAM - Séparation des fonctions (SoD)"
    if any(marker in text for marker in ("apd-08", "donnees sensibles", "paie", "rh", "confidential")):
        return "IAM - Accès aux données sensibles"
    if any(marker in text for marker in ("apd-09", "prestataire", "contrat", "tiers", "external")):
        return "Gouvernance - Prestataires"
    if any(marker in text for marker in ("pc-01", "mise en production", "changement", "recette", "test utilisateur")):
        return "Change Management - Validation & tests"
    if any(marker in text for marker in ("pc-02", "separation", "sod", "developpement", "production cumule")):
        return "Change Management - Segregation des environnements"
    if any(marker in text for marker in ("co-01", "co-07", "sauvegarde", "backup", "restauration")):
        return "Exploitation - Sauvegardes & restauration"
    if any(marker in text for marker in ("co-02", "incident", "sla", "ticket", "delai")):
        return "Exploitation - Incidents & SLA"
    if any(marker in text for marker in ("co-05", "pra", "pca", "drp", "reprise")):
        return "Exploitation - Continuité (PCA/PRA)"
    if any(marker in text for marker in ("co-08", "patch", "correctif", "vulnerabil")):
        return "Exploitation - Patches & vulnérabilités"
    if any(marker in text for marker in ("co-09", "capacite", "stockage", "capacity")):
        return "Exploitation - Capacité"
    return "Gouvernance - Controle interne IT"


def _build_transversal_initiatives(findings: list[DetailedFinding]) -> list[str]:
    if not findings:
        return []

    themed: dict[str, list[DetailedFinding]] = defaultdict(list)
    for finding in findings:
        themed[_theme_for_finding(finding)].append(finding)

    def bucket_for_theme(theme: str) -> str:
        if theme.startswith("IAM -"):
            return "IAM"
        if theme.startswith("Change Management -"):
            return "CHANGE"
        if theme.startswith("Exploitation -"):
            return "OPS"
        if theme.startswith("Securite -") or theme.startswith("Sécurité -"):
            return "SEC"
        return "GOV"

    buckets: dict[str, list[DetailedFinding]] = defaultdict(list)
    for theme, items in themed.items():
        buckets[bucket_for_theme(theme)].extend(items)

    scored: list[tuple[int, int, str]] = []
    for bucket, items in buckets.items():
        highest = sorted(items, key=lambda item: _priority_rank(item.priority))[0]
        scored.append((_priority_rank(highest.priority), -len(items), bucket))
    scored.sort()

    def examples(items: list[DetailedFinding], limit: int = 2) -> str:
        chosen = sorted(items, key=lambda item: (_priority_rank(item.priority), item.reference, item.application))[:limit]
        parts = [f"{item.reference} ({item.application})" for item in chosen if item.reference and item.application]
        return ", ".join(parts)

    initiatives: list[str] = []
    for _, _, bucket in scored[:5]:
        items = buckets[bucket]
        ex = examples(items, limit=2)

        if bucket == "IAM":
            initiatives.append(
                _clean_sentence(
                    "Renforcer le processus de gestion des habilitations (IAM), notamment la validation des accès, la recertification périodique, "
                    "ainsi que la gestion des comptes inactifs et privilégiés. " + (f"Exemples: {ex}." if ex else "")
                )
            )
        elif bucket == "CHANGE":
            initiatives.append(
                _clean_sentence(
                    "Améliorer la gestion des changements, en assurant des tests/recettes et validations avant mise en production, "
                    "et en renforçant la séparation des environnements et des rôles. " + (f"Exemples: {ex}." if ex else "")
                )
            )
        elif bucket == "OPS":
            initiatives.append(
                _clean_sentence(
                    "Renforcer l'exploitation informatique, notamment la réalisation de tests de restauration et le pilotage des incidents via des SLA et indicateurs. "
                    + (f"Exemples: {ex}." if ex else "")
                )
            )
        elif bucket == "SEC":
            initiatives.append(
                _clean_sentence(
                    "Renforcer les contrôles de sécurité (authentification et configurations), afin de réduire le risque de compromission des comptes. "
                    + (f"Exemples: {ex}." if ex else "")
                )
            )
        else:
            initiatives.append(
                _clean_sentence(
                    "Renforcer la gouvernance du contrôle interne IT (rôles, procédures, preuves et suivi), afin d'assurer une maîtrise durable des risques. "
                    + (f"Exemples: {ex}." if ex else "")
                )
            )

    return _deduplicate(initiatives)


def _build_specific_weaknesses(findings: list[DetailedFinding]) -> str:
    if not findings:
        return ""

    by_process: dict[str, list[DetailedFinding]] = defaultdict(list)
    for finding in findings:
        code = (finding.reference or "").split("-", 1)[0].strip().upper()
        if code:
            by_process[code].append(finding)

    labels = {
        "APD": "acces",
        "PC": "changements",
        "CO": "exploitation",
    }

    parts: list[str] = []
    for code in ("APD", "PC", "CO"):
        items = sorted(by_process.get(code, []), key=lambda item: (_priority_rank(item.priority), item.reference, item.application))
        if not items:
            continue
        examples = []
        for item in items[:2]:
            title = (item.title or "").strip().rstrip(".")
            if title:
                examples.append(f"{item.reference} ({title.lower()})")
        if examples:
            parts.append(f"{labels.get(code, code)}: " + ", ".join(examples))

    return _clean_sentence("Les principales faiblesses identifiees concernent " + "; ".join(parts) + ".") if parts else ""


def _build_process_summaries(findings: list[DetailedFinding]) -> list[ProcessSummary]:
    grouped: dict[str, list[DetailedFinding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.reference.split("-")[0]].append(finding)

    summaries: list[ProcessSummary] = []
    for process_code, items in grouped.items():
        summaries.append(
            ProcessSummary(
                process_code=process_code,
                process_name=PROCESS_LABELS.get(process_code, process_code),
                observation_count=len(items),
                applications=_deduplicate([item.application for item in items]),
                strengths=["Le processus est formellement present dans le perimetre de mission et couvert par le catalogue de controles."],
                watch_points=[item.title for item in items[:3]],
            )
        )
    return sorted(summaries, key=lambda item: item.process_code)


def _build_general_synthesis(findings: list[DetailedFinding], audit_input: StructuredAuditInput) -> tuple[str, str, str]:
    applications = _split_scope_applications(audit_input)
    top_findings = findings[:3]
    counts = Counter(item.priority for item in findings)
    critical_count = counts.get("Critical", 0)
    high_count = counts.get("High", 0)
    medium_count = counts.get("Medium", 0)
    low_count = counts.get("Low", 0)

    focus_areas = _describe_focus_areas(findings)
    maturity_level = _derive_maturity_level(findings)

    executive_summary = _clean_sentence(
        f"Notre revue ITGC realisee chez {audit_input.mission.entite_auditee} sur la periode {audit_input.mission.periode} "
        f"a mis en evidence {len(findings)} observation(s) sur le perimetre suivant: {', '.join(applications)}."
    )

    initiatives = _build_transversal_initiatives(findings)
    specifics = _build_specific_weaknesses(findings)

    general_synthesis = _clean_sentence(
        " ".join(
            [
                f"Au total, {len(findings)} observation(s) ont ete identifiees, dont {critical_count} critique(s), {high_count} elevee(s), "
                f"{medium_count} moyenne(s) et {low_count} faible(s).",
                f"Le niveau de maturite global du dispositif est estime {maturity_level}.",
                f"Les principaux foyers de risque concernent {focus_areas}.",
                specifics,
                "Des actions correctives sont attendues a court terme sur les points de priorite critique/elevee.",
            ]
        )
    )

    conclusion = _clean_sentence(
        f"Nous recommandons la mise en oeuvre prioritaire d'un plan d'action cible sur {focus_areas}, "
        "ainsi qu'un pilotage formalise (responsables, echeances, preuves) pour assurer la reduction durable des risques."
    )
    return general_synthesis, executive_summary, conclusion


def _build_consolidated_recommendations(findings: list[DetailedFinding]) -> list[DetailedFinding]:
    grouped: dict[tuple[str, str, str], DetailedFinding] = {}
    for finding in findings:
        key = (finding.reference, finding.application, finding.layer)
        current = grouped.get(key)
        if current is None or _priority_rank(finding.priority) < _priority_rank(current.priority):
            grouped[key] = finding
    return sorted(grouped.values(), key=lambda item: (_priority_rank(item.priority), item.reference, item.application, item.layer))


def recalculate_audit_input_priorities(
    audit_input: StructuredAuditInput,
    *,
    preserve_manual_overrides: bool = True,
    findings: list[DetailedFinding] | None = None,
) -> StructuredAuditInput:
    findings = findings if findings is not None else _build_detailed_findings(audit_input)
    findings_by_observation_id = {
        finding.observation_id: finding
        for finding in findings
        if finding.observation_id
    }

    updated_observations: list[AuditObservation] = []
    for observation in audit_input.observations:
        if preserve_manual_overrides and observation.priority_source == "manual_override":
            updated_observations.append(observation)
            continue

        finding = findings_by_observation_id.get(observation.observation_id)
        if finding is None:
            updated_observations.append(
                observation.model_copy(
                    update={
                        "priority": observation.priority or "Low",
                        "priority_justification": observation.priority_justification or "",
                        "priority_reason": observation.priority_reason or "not_reportable_observation",
                        "priority_source": observation.priority_source or "generated_pipeline",
                    }
                )
            )
            continue

        updated_observations.append(
            observation.model_copy(
                update={
                    "priority": finding.priority,
                    "priority_justification": finding.priority_justification,
                    "priority_reason": "generated_pipeline",
                    "priority_source": "generated_pipeline",
                    "recommandation_proposee": finding.recommendation,
                    "cause_racine": finding.root_cause or observation.cause_racine,
                    "impact_potentiel": finding.impact_detail or observation.impact_potentiel,
                    "risque_associe": finding.risk_impact or observation.risque_associe,
                }
            )
        )

    return audit_input.model_copy(update={"observations": updated_observations})


def compose_audit_report(audit_input: StructuredAuditInput) -> AuditReportOutput:
    mission = audit_input.mission
    findings = _build_detailed_findings(audit_input)
    general_synthesis, executive_summary, conclusion = _build_general_synthesis(findings, audit_input)
    maturity_level = _derive_maturity_level(findings)
    transversal_initiatives = _build_transversal_initiatives(findings)

    # Covered controls: include catalog controls for the mission + any observed control refs not in the catalog.
    observed_refs: dict[str, AuditObservation] = {}
    for obs in audit_input.observations:
        ref = _resolve_effective_reference(obs)
        if ref and ref not in observed_refs:
            observed_refs[ref] = obs.model_copy(update={"controle_ref": ref})

    covered_controls: list[CoveredControl] = []
    covered_process_codes = set(_normalize_process_codes(mission.processus_couverts or []))

    def _infer_process(reference: str) -> str:
        prefix = (reference or "").split("-", 1)[0].strip().upper()
        return prefix if prefix in PROCESS_LABELS else ""

    for reference in _scoped_control_references(audit_input):
        obs = observed_refs.get(reference) or AuditObservation(controle_ref=reference)
        item = CONTROL_CATALOG.get(reference, {}) or {}
        process = (item.get("process", "") or "").strip() or _infer_process(reference)
        if covered_process_codes and process and process not in covered_process_codes:
            continue

        description = (item.get("description", "") or "").strip() or (obs.controle_attendu or obs.titre_observation or "Contrôle couvert (référence fournie dans l'input).")
        test_procedure = (item.get("test_procedure", "") or "").strip() or "Procédure de test à définir selon le contrôle et le contexte applicatif."

        covered_controls.append(
            CoveredControl(
                reference=reference,
                process=process or "N/A",
                description=description,
                test_procedure=test_procedure,
            )
        )

    covered_controls = sorted(covered_controls, key=lambda c: (c.process or "", c.reference))

    table_of_contents = [
        "Préambule",
        "Objectifs",
        "Périmètre",
        "Intervenants",
        "Approche d’audit",
        "Liste des contrôles",
        "Synthèse contrôle × application",
        "Synthèse générale",
        "Synthèse des priorités",
        "Points relevés",
        "Recommandations",
    ]

    return AuditReportOutput(
        cover_title=mission.titre_mission or "Rapport d'audit IT",
        cover_subtitle="Version projet",
        client_name=mission.entite_auditee,
        report_period=mission.periode,
        report_date=mission.date_rapport,
        table_of_contents=table_of_contents,
        confidentiality_notice="Strictement privé et confidentiel",
        preamble=_build_preamble(audit_input),
        objectives=mission.objectifs or _default_objectives(audit_input),
        stakeholders=mission.intervenants,
        scope_summary=_build_scope_summary(audit_input),
        applications=_split_scope_applications(audit_input),
        application_details=mission.application_details,
        covered_processes=[PROCESS_LABELS.get(code, code) for code in sorted(covered_process_codes)] or mission.processus_couverts,
        audit_approach=FIXED_AUDIT_APPROACH,
        covered_controls=covered_controls,
        control_matrix=_build_control_matrix(audit_input, findings),
        key_figures=_build_key_figures(audit_input, findings),
        executive_highlights=_build_executive_highlights(findings),
        strengths=_build_strengths(findings, audit_input),
        watch_points=_build_watch_points(findings),
        maturity_level=maturity_level,
        maturity_assessment=_build_maturity_assessment(findings),
        priority_insight=_build_priority_insight(findings),
        strategic_priorities=_build_strategic_priorities(findings),
        transversal_initiatives=transversal_initiatives,
        process_summaries=_build_process_summaries(findings),
        general_synthesis=general_synthesis,
        priority_summary=_build_priority_summary(findings),
        detailed_findings=findings,
        detailed_recommendations=_build_consolidated_recommendations(findings),
        executive_summary=executive_summary,
        conclusion=conclusion,
    )
