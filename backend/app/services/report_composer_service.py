from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import unicodedata
import logging
import re

from app.agents.priority_agent import classify_priority, enforce_min_priority
from app.agents.priority_agent import VALID_PRIORITIES
from app.agents.reasoning_agent import infer_observation_reasoning, infer_priority_reasoning
from app.services.reasoning_validator_service import validate_priority_reasoning, validate_reasoning
from app.services.recommendation_validator import validate_recommendation
from app.utils.french_normalizer import normalize_french
from app.models.audit_input import AuditObservation, StructuredAuditInput
from app.domain.itgc_control_catalog import CONTROL_CATALOG, PROCESS_LABELS
from app.models.report_sections import (
    AuditReportOutput,
    ControlMatrixEntry,
    CoveredControl,
    DetailedFinding,
    FindingTraceability,
    KeyFigure,
    PrioritySummaryItem,
    ProcessSummary,
    TraceabilitySource,
)
from app.services.quality_gate_service import evaluate_report_quality_gate

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


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _traceability_confidence(
    *,
    reasoning_ok: bool,
    priority_reasoning_ok: bool,
    recommendation_valid: bool,
    priority: str,
    priority_justification: str,
) -> float:
    score = 0.55
    if reasoning_ok:
        score += 0.1
    if priority_reasoning_ok:
        score += 0.12
    if recommendation_valid:
        score += 0.08
    if priority in {"Critical", "High"} and priority_justification.strip():
        score += 0.08
    if len(priority_justification.strip()) >= 80:
        score += 0.04
    return round(min(score, 0.98), 2)


def _traceability_sources(observation: AuditObservation) -> list[TraceabilitySource]:
    evidence_excerpt = " | ".join(
        part
        for part in [
            (observation.constat or "").strip(),
            (observation.references_probantes or "").strip(),
            (observation.commentaire_auditeur or "").strip(),
        ]
        if part
    )[:280]

    sources = [
        TraceabilitySource(
            source_id=observation.observation_id or "observation",
            document_name="mission audit input",
            source_type="structured_audit_input",
            excerpt=evidence_excerpt or "Structured mission observation used to generate the finding.",
        )
    ]

    if (observation.references_probantes or "").strip():
        sources.append(
            TraceabilitySource(
                source_id=f"{observation.observation_id}-evidence",
                document_name="references_probantes",
                source_type="auditor_evidence_reference",
                excerpt=(observation.references_probantes or "").strip()[:280],
            )
        )

    return sources


def _traceability_rule_markers(
    observation: AuditObservation,
    *,
    original_reference: str,
    resolved_reference: str,
    priority_mode: str,
    recommendation_mode: str,
    reasoning_ok: bool,
    priority_reasoning_ok: bool,
    final_priority: str,
) -> list[str]:
    markers = [f"reference_resolution:{original_reference or 'missing'}->{resolved_reference or 'missing'}"]
    if original_reference != resolved_reference:
        markers.append("control_reference_remapped")
    if reasoning_ok:
        markers.append("observation_reasoning_validated")
    if priority_reasoning_ok:
        markers.append("priority_reasoning_validated")
    if "enforced" in priority_mode:
        markers.append("minimum_priority_enforced")
    if "deterministic" in priority_mode:
        markers.append("deterministic_priority_rules")
    if recommendation_mode != "validated_llm":
        markers.append("recommendation_fallback_rules")
    if final_priority in {"Critical", "High"}:
        markers.append("heightened_review_priority")
    if (observation.priority_source or "").strip() == "manual_override":
        markers.append("manual_priority_override_preserved")
    return markers


def _reference_process(reference: str) -> str:
    return ((reference or "").upper().strip().split("-", 1) or [""])[0]


def _reference_signal_strength(text: str, markers: tuple[str, ...]) -> int:
    score = 0
    for marker in markers:
        if marker in text:
            score += 1
    return score


def _reference_scores(observation: AuditObservation) -> dict[str, int]:
    title_text = _keyword_text(observation.titre_observation)
    category_text = _keyword_text(observation.categorie_controle)
    constat_text = _keyword_text(observation.constat, observation.impact_potentiel, observation.application)

    weighted_signals = {
        "APD-02": (
            ("post-depart", "post depart", "apres depart", "ancien collaborateur", "anciens collaborateurs", "depart des utilisateurs", "desactivation des comptes"),
            ("mouvement rh", "depart", "quitte l organisation", "quitte l entreprise", "contrat a pris fin"),
            (),
        ),
        "APD-03": (
            ("superuser", "teller_admin", "compte generique", "compte partage", "compte commun", "shared account", "generic account", "absence de tracabilite", "tracabilite individuelle"),
            ("privilegie", "privilege", "journalisation", "tracabilite", "interactive", "interactif", "validation", "annulation", "swift_opr", "operateur swift", "operateurs swift", "droits etendus"),
            (),
        ),
        "APD-04": (
            ("recertification", "re certification"),
            ("revue periodique", "revue des acces", "droits incompatibles", "fonctions incompatibles", "4 yeux", "quatre yeux"),
            (),
        ),
        "APD-09": (
            ("prestataire", "prestataires", "consultant", "consultants"),
            ("fin de mission", "contrat expire", "contrats ont expire", "echeance des contrats", "revocation des acces prestataires", "compte prestataire"),
            (),
        ),
        "APD-05": (
            ("mot de passe", "mots de passe", "password", "mfa", "2fa"),
            ("complexite", "historique", "verrouillage", "tentatives infructueuses", "brute force", "authentification"),
            (),
        ),
        "PC-01": (
            ("cab", "change advisory board", "deploiement", "mise en production", "rfc"),
            ("approbation formelle", "sans validation", "rollback", "preuve de test", "validation cab"),
            (),
        ),
        "PC-02": (
            ("developpement", "dev", "production", "prod"),
            ("separation des environnements", "acces cumules", "connexions simultanees", "simultane"),
            (),
        ),
        "CO-01": (
            ("sauvegarde", "backup", "backups"),
            ("copie de sauvegarde", "offshore", "retention"),
            (),
        ),
        "CO-02": (
            ("incident", "incidents", "itsm", "helpdesk", "ticketing"),
            ("sla", "cause racine", "rca", "escalade", "delai de resolution"),
            (),
        ),
        "CO-03": (
            ("prestataire", "prestations externalisees", "fournisseur", "third party"),
            ("isae 3402", "soc 2", "sla", "kpi", "comite de pilotage", "comite de gouvernance", "second niveau"),
            (),
        ),
        "CO-05": (
            ("plan de reprise", "plan de continuite", "reprise apres sinistre", "continuite informatique"),
            ("rpo", "rto", "basculement", "site de secours", "sinistre"),
            (),
        ),
        "CO-07": (
            ("restauration", "restore"),
            ("procedure de restauration", "test de restauration", "restauration complete"),
            (),
        ),
        "CO-08": (
            ("patch", "correctif", "correctifs", "cve"),
            ("vulnerabil", "cvss", "openssl", "patch management", "security patch"),
            (),
        ),
    }

    scores: dict[str, int] = {}
    for reference, (title_markers, constat_markers, category_markers) in weighted_signals.items():
        score = 0
        score += _reference_signal_strength(title_text, title_markers) * 3
        score += _reference_signal_strength(constat_text, constat_markers) * 2
        score += _reference_signal_strength(category_text, category_markers)
        if score:
            scores[reference] = score
    return scores


def _resolve_effective_reference_with_reason(observation: AuditObservation) -> tuple[str, str]:
    original = (observation.controle_ref or "").upper().strip()
    original_valid = original in CONTROL_CATALOG
    scores = _reference_scores(observation)

    if original_valid:
        scores[original] = scores.get(original, 0) + 3

    if not scores:
        if original_valid:
            return original, "Original reference kept: no stronger keyword evidence was detected."
        return original, "Original reference kept: no keyword evidence was available for remapping."

    best_reference, best_score = max(scores.items(), key=lambda item: item[1])
    original_score = scores.get(original, 0)
    same_process = _reference_process(best_reference) == _reference_process(original)

    if best_reference == original:
        return original, "Original reference confirmed by keyword evidence in the observation."

    if original_valid and not same_process and best_score < original_score + 3:
        return original, f"Original reference kept to avoid cross-process over-remapping; strongest alternate signal was {best_reference}."

    if original_valid and same_process and best_score < original_score + 2:
        return original, f"Original reference kept because alternate evidence toward {best_reference} was not materially stronger."

    if original_valid and best_score < 4:
        return original, f"Original reference kept because the remapping evidence toward {best_reference} was too weak."

    if original_valid:
        return best_reference, f"Reference remapped from {original} to {best_reference} based on stronger keyword evidence in the title and observation details."
    return best_reference, f"Reference inferred as {best_reference} because the original reference was missing or unsupported."


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
    value = value.replace("risque de risque de", "risque de").replace(" .", ".").replace(" ,", ",")
    while ".." in value:
        value = value.replace("..", ".")
    value = re.sub(r"\s+([.;:,])", r"\1", value)
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


def _derive_business_impact(observation: AuditObservation, reference: str = "") -> str:
    explicit_impact = _first_non_empty(observation.impact_potentiel)
    if explicit_impact:
        return explicit_impact

    text = _keyword_text(
        observation.titre_observation,
        observation.categorie_controle,
        observation.constat,
        observation.commentaire_auditeur,
    )
    ref = (reference or observation.controle_ref or "").upper().strip()

    if ref in {"APD-01", "APD-02", "APD-09"} or "post-depart" in text or "depart" in text or "actif" in text:
        if any(k in text for k in ("fort encours", "operation", "mouvement", "virement", "client")):
            return "Operations non legitimes ou consultation de donnees clients sensibles, avec perte de tracabilite sur des comptes a fort enjeu metier."
        if any(k in text for k in ("paie", "remuneration", "donnees personnelles")):
            return "Consultation ou modification non autorisee de donnees RH et de paie, avec exposition de donnees personnelles sensibles."
        return "Utilisation non autorisee de comptes residuels, fuite de donnees sensibles et perte de responsabilisation des actions realisees."
    if ref == "APD-03" or any(k in text for k in ("compte generique", "compte partage", "superuser", "teller_admin", "privilegie")):
        return "Actions sensibles non attribuables individuellement, contournement possible de la segregation des taches et risque de manipulation non autorisee des operations ou parametres critiques."
    if ref == "APD-04" or any(k in text for k in ("recertification", "fonctions incompatibles", "4 yeux", "quatre yeux")):
        return "Maintien de droits excessifs ou incompatibles pouvant permettre la saisie et validation d'operations sans controle independant, notamment sur les processus metier sensibles."
    if ref == "CO-05" or any(k in text for k in ("pra", "pca", "rpo", "rto", "basculement")):
        return "Indisponibilite prolongee des services critiques et incapacite a confirmer le respect des objectifs RTO/RPO en cas de sinistre."
    if ref == "CO-08" or any(k in text for k in ("patch", "correctif", "vulnerabil", "cve", "cvss")):
        return "Exploitation potentielle de vulnerabilites connues, compromission de services exposes et interruption ou alteration de traitements clients."
    if "validation" in text or "autorisation" in text:
        return "Non-conformite aux procedures internes et atteinte a l'integrite des donnees."
    if "sauvegarde" in text or "restauration" in text or "backup" in text:
        return "Interruption des operations et perte definitive de donnees critiques."
    if "changement" in text or "production" in text or "deploi" in text:
        return "Interruption des operations metier et correction couteuse en production."
    if "incident" in text:
        return "Interruption de service, non-respect des engagements et perte financiere."
    return "Perte financiere, non-conformite et atteinte a l'integrite des traitements."


def _business_impact_is_generic(value: str) -> bool:
    text = _keyword_text(value)
    generic_markers = (
        "fuite de donnees sensibles et utilisation frauduleuse des comptes",
        "perte financiere non conformite",
        "non conformite aux procedures internes",
    )
    return any(marker in text for marker in generic_markers)


def _derive_risk_scenario(observation: AuditObservation, reference: str, fallback_risk: str = "") -> str:
    application = observation.application or "l'application concernee"
    text = _keyword_text(
        reference,
        observation.titre_observation,
        observation.constat,
        observation.categorie_controle,
    )

    if any(k in text for k in ("post-depart", "post depart", "apres depart", "depart")):
        return _clean_sentence(
            f"Le maintien de comptes actifs apres depart sur {application} expose l'entite a l'utilisation non autorisee "
            "d'identifiants appartenant a d'anciens collaborateurs ou tiers n'intervenant plus sur le perimetre."
        )
    if any(k in text for k in ("compte generique", "compte partage", "superuser", "teller_admin", "privilegie")):
        return _clean_sentence(
            f"L'utilisation de comptes generiques ou privilegies sur {application} peut permettre l'execution d'actions sensibles "
            "sans attribution individuelle fiable des responsabilites."
        )
    if any(k in text for k in ("recertification", "fonctions incompatibles", "4 yeux", "quatre yeux")):
        return _clean_sentence(
            f"L'absence de revue formelle des droits sur {application} peut maintenir des acces excessifs ou incompatibles avec les fonctions exercees."
        )
    if any(k in text for k in ("mot de passe", "mfa", "authentification", "verrouillage")):
        return _clean_sentence(
            f"Des parametres d'authentification insuffisants sur {application} augmentent la probabilite de compromission de comptes utilisateurs."
        )
    if any(k in text for k in ("cab", "changement", "mise en production", "rfc", "deploi")):
        return _clean_sentence(
            f"Des changements de production deployes sans validation formelle sur {application} peuvent introduire des modifications non maitrisees dans les traitements."
        )
    if any(k in text for k in ("pra", "pca", "restauration", "sauvegarde", "rpo", "rto")):
        return _clean_sentence(
            f"L'absence de tests complets de reprise ou de restauration sur {application} peut empecher le retablissement maitrise des services en cas d'incident majeur."
        )
    if any(k in text for k in ("incident", "itsm", "ticketing", "sla")):
        return _clean_sentence(
            f"Un processus incident insuffisamment outille ou formalise peut retarder l'escalade, la resolution et l'analyse des incidents affectant {application}."
        )
    if any(k in text for k in ("patch", "correctif", "vulnerabil", "cve", "cvss")):
        return _clean_sentence(
            f"Le retard de correction sur {application} maintient une exposition a des vulnerabilites connues pouvant etre exploitees."
        )
    return _clean_sentence(fallback_risk or _derive_risk_impact(observation))


def _derive_control_impact(observation: AuditObservation, reference: str) -> str:
    ref = (reference or "").upper().strip()
    text = _keyword_text(reference, observation.titre_observation, observation.constat, observation.categorie_controle)
    if ref.startswith("APD") or any(k in text for k in ("acces", "compte", "habilitation")):
        return "Le dispositif de controle interne ne permet pas de garantir l'exhaustivite, la pertinence et la tracabilite du cycle de vie des habilitations."
    if ref.startswith("PC") or any(k in text for k in ("changement", "production", "deploi")):
        return "Le dispositif de gestion des changements ne garantit pas que les mises en production sont autorisees, testees et tracables avant de modifier l'environnement."
    if ref.startswith("CO") or any(k in text for k in ("incident", "sauvegarde", "restauration", "pra", "patch")):
        return "Le dispositif d'exploitation ne fournit pas une assurance suffisante sur la continuite, la supervision et la preuve d'execution des controles."
    return "Le dispositif ITGC ne fournit pas une assurance suffisante sur la conception, l'execution et la tracabilite du controle attendu."


def _derive_compliance_impact(observation: AuditObservation) -> str:
    text = _keyword_text(observation.constat, observation.titre_observation, observation.commentaire_auditeur)
    if any(k in text for k in ("bct", "circulaire", "nist", "iso", "isae", "soc 2", "reglement")):
        return "La faiblesse peut exposer l'entite a un ecart vis-a-vis des exigences internes, reglementaires ou des bonnes pratiques explicitement citees dans le constat."
    if any(k in text for k in ("donnees personnelles", "paie", "client", "confidentialite")):
        return "La faiblesse peut accroitre l'exposition en matiere de confidentialite et de protection des donnees sensibles."
    return ""


def _derive_aggravating_factors(observation: AuditObservation) -> list[str]:
    text = " ".join(
        part.strip()
        for part in [
            observation.constat,
            observation.commentaire_auditeur,
            observation.procedure_compensatoire,
            observation.application,
        ]
        if part and part.strip()
    )
    lowered = _keyword_text(text)
    factors: list[str] = []

    if _NUM_RE.search(text):
        factors.append("Presence d'elements quantifies dans le constat, indiquant une exposition mesurable.")
    if any(k in lowered for k in ("t24", "core banking", "swift", "openbanking", "paie")):
        factors.append("Application ou processus sensible dans le perimetre audite.")
    if any(k in lowered for k in ("fort encours", "client", "virement", "swift", "credit", "paie")):
        factors.append("Exposition a des donnees ou operations metier sensibles.")
    if any(k in lowered for k in ("connexion", "operation", "mouvement", "interactif", "simultanee")):
        factors.append("Activite ou usage confirme au-dela d'une simple anomalie de parametrage.")
    if any(k in lowered for k in ("aucun", "aucune", "absence", "non formalise", "sans workflow", "sans procedure")):
        factors.append("Absence de procedure, de workflow ou de preuve formelle de controle.")
    if any(k in lowered for k in ("pas d'accuse", "accuse de reception", "sans suivi", "exceptions")):
        factors.append("Suivi des exceptions ou accuse de traitement insuffisamment formalise.")
    return _deduplicate(factors)[:5]


def _derive_root_cause(observation: AuditObservation, reference: str) -> str:
    explicit = _first_non_empty(observation.cause_racine)
    if explicit:
        return explicit

    text = _keyword_text(
        reference,
        observation.titre_observation,
        observation.constat,
        observation.procedure_compensatoire,
        observation.commentaire_auditeur,
    )
    if any(k in text for k in ("post-depart", "post depart", "apres depart", "depart", "revocation")):
        return "Absence de processus formalise, tracable et systematique de rapprochement entre mouvements RH et desactivation effective des comptes."
    if any(k in text for k in ("compte generique", "compte partage", "privilegie", "superuser")):
        return "Absence de gouvernance formelle des comptes generiques et privilegies, incluant justification, journalisation et revue periodique des usages."
    if any(k in text for k in ("recertification", "revue des acces", "fonctions incompatibles")):
        return "Absence de campagne formelle de recertification des droits et de suivi documente des corrections d'habilitations."
    if any(k in text for k in ("mot de passe", "mfa", "authentification")):
        return "Parametrage de securite insuffisamment aligne avec les exigences internes et les bonnes pratiques applicables."
    if any(k in text for k in ("cab", "changement", "rfc", "mise en production")):
        return "Processus de gestion des changements insuffisamment contraignant sur les validations, preuves de test et controles avant mise en production."
    if any(k in text for k in ("pra", "pca", "restauration", "sauvegarde", "rpo", "rto")):
        return "Absence de planification et de documentation suffisantes des tests de reprise ou de restauration sur les scenarios critiques."
    if any(k in text for k in ("incident", "itsm", "ticketing", "sla")):
        return "Absence d'un processus outille et formalise de gestion des incidents, incluant classification, escalade et analyse de cause racine."
    return "Insuffisance de formalisation du controle attendu, des responsabilites, des preuves d'execution et du suivi des exceptions."


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
    application = (observation.application or "le perimetre concerne").strip()
    reference = (observation.controle_ref or "").strip()

    excerpt = constat
    if "." in constat:
        excerpt = constat.split(".", 1)[0].strip()
    excerpt = _truncate_at_word_boundary(excerpt, 240).rstrip(".")

    lowered = _keyword_text(constat, observation.titre_observation, observation.categorie_controle)
    numbers = sorted(set(_NUM_RE.findall(constat)))
    evidence_parts: list[str] = []

    if numbers:
        evidence_parts.append(f"des elements factuels ont ete releves ({', '.join(numbers[:3])})")
    if any(k in lowered for k in ("absence", "aucun", "aucune", "non formalise", "non documente", "non supervise")):
        evidence_parts.append("le dispositif de controle ou la preuve d'execution est absent ou insuffisamment formalise")
    if any(k in lowered for k in ("compte generique", "compte partage", "shared", "superuser", "administrateur", "privileg")):
        evidence_parts.append("des acces etendus ou non nominatifs sont maintenus")
    if any(k in lowered for k in ("post depart", "apres depart", "depart")):
        evidence_parts.append("des comptes restent actifs apres depart")
    if any(k in lowered for k in ("operation", "transaction", "virement", "swift", "fort encours")):
        evidence_parts.append("l'exposition porte sur des traitements sensibles")
    if any(k in lowered for k in ("patch", "correctif", "cve", "vulnerabil")):
        evidence_parts.append("des vulnerabilites connues demeurent exposees")
    if any(k in lowered for k in ("pra", "pca", "drp", "restauration", "rto", "rpo")):
        evidence_parts.append("la capacite de reprise ou de restauration n'est pas suffisamment demontree")
    if any(k in lowered for k in ("incompatib", "sod", "separation des fonctions", "auto-valid")):
        evidence_parts.append("des droits incompatibles ou des contournements de segregation des taches sont identifies")

    evidence_clause = "; ".join(evidence_parts[:3]) if evidence_parts else f"le constat met en evidence l'ecart suivant: {excerpt}"
    return _clean_sentence(
        f"La priorite {priority_label} retenue pour {application} au titre du controle {reference or 'considere'} est justifiee des lors que {evidence_clause}. "
        f"Les faits releves montrent une exposition suffisamment significative pour qualifier ce point en priorite {priority_label}."
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


def _recommendation_owner(observation: AuditObservation) -> str:
    text = _keyword_text(observation.application, observation.titre_observation, observation.constat, observation.categorie_controle)
    if any(k in text for k in ("rh", "paie", "hr access")):
        return "les equipes RH et IT"
    if any(k in text for k in ("swift", "banque en ligne", "openbanking", "t24", "core banking")):
        return "les equipes IT et les responsables applicatifs"
    if any(k in text for k in ("prestataire", "sopra", "ibs")):
        return "la DSI et les responsables de la relation fournisseur"
    return "la DSI et les responsables de processus concernes"


def _recommendation_evidence(reference: str) -> str:
    prefix = (reference or "").split("-", 1)[0].strip().upper()
    if prefix == "APD":
        return "conserver les validations, revues et journaux d'execution associes"
    if prefix == "PC":
        return "conserver les preuves de recette, d'approbation et de mise en production"
    if prefix == "CO":
        return "conserver les journaux, indicateurs, comptes rendus et preuves de tests associes"
    return "conserver une piste d'audit complete des actions de remediation"


def _build_contextual_recommendation(observation: AuditObservation, reference: str) -> str:
    base = _catalog_recommendation(reference)
    text = _keyword_text(
        observation.application,
        observation.titre_observation,
        observation.constat,
        observation.categorie_controle,
        observation.impact_potentiel,
    )
    owner = _recommendation_owner(observation)
    evidence = _recommendation_evidence(reference)

    if reference == "APD-01":
        return _clean_sentence(
            f"Formaliser un processus de revocation des acces post-depart, pilote par {owner}, couvrant les applications critiques et les couches techniques associees. "
            "Ce processus doit prevoir une notification RH systematique des departs, un delai cible de desactivation, un accuse de traitement par les equipes IT, "
            f"un rapprochement periodique entre mouvements RH et comptes actifs, ainsi qu'un suivi documente des exceptions; {evidence}."
        )
    if reference == "APD-02":
        return _clean_sentence(
            "Formaliser et automatiser le processus de revocation des acces sur l'ensemble des couches applicatives et techniques a la suite des departs ou mobilites, "
            f"avec suivi des comptes residuels, revue periodique et validation par {owner}; {evidence}."
        )
    if reference == "APD-03":
        return _clean_sentence(
            "Reduire strictement l'usage des comptes generiques ou privilegies, mettre en place des comptes nominatifs lorsque cela est possible, "
            f"renforcer la journalisation et instaurer une revue periodique formelle des usages par {owner}; {evidence}."
        )
    if reference == "APD-04":
        return _clean_sentence(
            "Mettre en oeuvre une campagne formelle et periodique de recertification des acces couvrant l'exhaustivite des comptes, profils et droits sensibles, "
            f"avec validation par les managers, correction des incompatibilites et suivi documente des plans d'action par {owner}; {evidence}."
        )
    if reference == "APD-05":
        return _clean_sentence(
            "Aligner la politique d'authentification sur les exigences internes et reglementaires en renforcant les parametres de mots de passe, "
            f"en deployant des mecanismes de verrouillage et, lorsque pertinent, une authentification forte sur les operations sensibles; {evidence}."
        )
    if reference == "PC-01":
        return _clean_sentence(
            "Imposer qu'aucun changement ne soit deploye en production sans validation CAB ou approbation equivalente, preuve de test ou recette, "
            f"analyse d'impact et plan de retour arriere, y compris pour les changements urgents; {evidence}."
        )
    if reference == "PC-02":
        return _clean_sentence(
            "Restreindre les acces cumules entre developpement, recette et production, formaliser les derogations strictement necessaires, "
            f"et mettre en place une revue periodique des habilitations techniques par {owner}; {evidence}."
        )
    if reference in {"CO-01", "CO-05", "CO-07"}:
        return _clean_sentence(
            "Planifier et executer regulierement des tests de sauvegarde, restauration et reprise, documenter les resultats obtenus, "
            f"traiter les ecarts constates au regard des objectifs RTO/RPO et maintenir a jour la documentation operative; {evidence}."
        )
    if reference == "CO-02":
        return _clean_sentence(
            "Structurer le pilotage des incidents via un outil de ticketing, des SLA par criticite, des escalades formelles et des analyses de cause racine, "
            f"avec tableau de bord periodique de suivi a destination du management; {evidence}."
        )
    if reference == "CO-03":
        return _clean_sentence(
            "Formaliser la supervision des prestations externalisees au travers de SLA, KPI, comites de pilotage et controles de second niveau, "
            f"et contractualiser les exigences de controle attendues vis-a-vis du prestataire; {evidence}."
        )
    if reference in {"CO-04", "CO-08"}:
        return _clean_sentence(
            "Mettre en place un pilotage renforce des configurations de securite et des correctifs, avec suivi par criticite, validation des exceptions, "
            f"fenetres de maintenance definies et reporting periodique au management; {evidence}."
        )

    if base:
        if any(k in text for k in ("absence", "aucun", "aucune", "non formalise", "non documente")):
            return _clean_sentence(f"{base.rstrip('.')} et formaliser la frequence, les responsables et les preuves attendues d'execution.")
        if any(k in text for k in ("plusieurs", "23", "11", "14", "%")):
            return _clean_sentence(f"{base.rstrip('.')} avec un plan de remediation priorise sur les populations ou cas identifies, ainsi qu'un suivi formel des exceptions.")
        return _clean_sentence(f"{base.rstrip('.')} sous pilotage de {owner}; {evidence}.")

    if observation.controle_attendu:
        return _clean_sentence(
            f"Formaliser un dispositif permettant d'assurer le respect effectif du controle attendu, avec responsabilites definies, calendrier d'execution et preuves de realisation; {evidence}."
        )

    prefix = (reference or "").split("-", 1)[0].strip().upper()
    if prefix == "APD":
        return _clean_sentence(
            f"Renforcer les controles d'acces via validation, revocation, revue periodique et supervision des exceptions, sous pilotage de {owner}; {evidence}."
        )
    if prefix == "PC":
        return _clean_sentence(
            f"Renforcer la gestion des changements en imposant validation, recette, traceabilite et segregation des roles avant mise en production; {evidence}."
        )
    if prefix == "CO":
        return _clean_sentence(
            f"Renforcer les controles d'exploitation en structurant la supervision, la continuite et la production des preuves de controle; {evidence}."
        )
    return _clean_sentence(
        "Formaliser un plan de remediation cible avec responsabilites, echeances, controles de suivi et preuves d'execution."
    )


def _build_recommendation_objective(observation: AuditObservation, reference: str) -> str:
    ref = (reference or "").upper().strip()
    if ref.startswith("APD"):
        return "Reduire durablement le risque d'acces non autorise en assurant une gestion exhaustive, rapide et tracable des habilitations."
    if ref.startswith("PC"):
        return "Garantir que les changements de production sont autorises, testes, tracables et conformes au niveau de risque metier."
    if ref.startswith("CO"):
        return "Renforcer la maitrise de l'exploitation informatique et la disponibilite des services critiques au moyen de controles documentes."
    return "Renforcer la maitrise du controle interne IT et la tracabilite des actions correctives."


def _build_recommendation_components(observation: AuditObservation, reference: str) -> dict[str, str | list[str]]:
    owner = _recommendation_owner(observation)
    evidence = _recommendation_evidence(reference)
    ref = (reference or "").upper().strip()

    if ref in {"APD-01", "APD-02", "APD-09"}:
        immediate = "Desactiver les comptes residuels identifies et documenter la justification des exceptions maintenues temporairement."
        structural = (
            "Mettre en place un rapprochement RH/IT recurrent entre les mouvements de personnel et les comptes actifs, avec delai cible de traitement "
            "et accuse de prise en charge par les equipes IT."
        )
        follow_up = "Suivre mensuellement les comptes post-depart, les delais de desactivation et les exceptions ouvertes jusqu'a regularisation."
    elif ref == "APD-03":
        immediate = "Revoir les comptes generiques ou privilegies identifies, supprimer les droits non justifies et documenter les usages maintenus."
        structural = "Basculer vers des comptes nominatifs ou un dispositif PAM lorsque possible, avec journalisation et revue periodique des activites sensibles."
        follow_up = "Produire une revue periodique des usages privilegies et des connexions atypiques, validee par le responsable applicatif."
    elif ref == "APD-04":
        immediate = "Lancer une revue ciblee des droits sensibles et corriger les cas de droits excessifs ou incompatibles identifies."
        structural = "Instituer une campagne de recertification periodique couvrant comptes, profils et droits sensibles, avec validation manager/metier."
        follow_up = "Suivre les validations, refus, corrections et exceptions dans un tableau de bord de remediations."
    elif ref.startswith("PC"):
        immediate = "Revoir les changements non conformes identifies et documenter a posteriori les validations, tests et risques residuels."
        structural = "Bloquer les mises en production sans demande approuvee, preuve de recette, analyse d'impact et plan de retour arriere."
        follow_up = "Suivre mensuellement le taux de changements deployes avec dossier complet et les exceptions validees."
    elif ref in {"CO-01", "CO-05", "CO-07"}:
        immediate = "Planifier un test cible de restauration ou de reprise sur le perimetre concerne et documenter les resultats."
        structural = "Formaliser un calendrier de tests, des scenarios couvrant les applications critiques et les criteres d'acceptation RTO/RPO."
        follow_up = "Presenter les resultats de tests, ecarts et plans d'action dans un comite de suivi IT/risques."
    elif ref == "CO-02":
        immediate = "Centraliser les incidents ouverts, qualifier leur criticite et documenter les analyses de cause racine des incidents majeurs."
        structural = "Deployer ou formaliser un outil ITSM avec workflow, SLA par criticite, escalades et tableau de bord de pilotage."
        follow_up = "Revoir periodiquement les delais de resolution, incidents recurrents et RCA non cloturees."
    elif ref == "CO-08":
        immediate = "Prioriser les correctifs critiques en retard et formaliser les exceptions de patching avec acceptation du risque."
        structural = "Mettre en place un processus de patch management base sur la criticite, avec fenetres de maintenance et reporting."
        follow_up = "Suivre les delais de correction par criticite et les vulnerabilites depassant les seuils internes."
    else:
        immediate = "Traiter les exceptions identifiees et documenter les actions correctives realisees."
        structural = "Formaliser le controle attendu avec roles, frequence, criteres d'execution et preuves obligatoires."
        follow_up = "Mettre en place un suivi periodique des exceptions, responsables et echeances de remediation."

    evidence_expected = f"{evidence}; conserver les validations, dates de traitement, exceptions et resultats des revues."
    steps = [
        f"Action corrective immediate: {immediate}",
        f"Action structurelle: {structural}",
        f"Responsable: {owner}.",
        f"Preuves attendues: {evidence_expected}",
        f"Mecanisme de suivi: {follow_up}",
    ]
    return {
        "immediate_action": _clean_sentence(immediate),
        "structural_action": _clean_sentence(structural),
        "owner": owner,
        "evidence_expected": _clean_sentence(evidence_expected),
        "follow_up_mechanism": _clean_sentence(follow_up),
        "steps": [_clean_sentence(step) for step in steps],
    }


def _build_recommendation_v2(observation: AuditObservation) -> str:
    ref = (observation.controle_ref or "").upper()
    return _build_contextual_recommendation(observation, ref)


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
    impact_value = (impact or _derive_business_impact(observation, observation.controle_ref)).rstrip(".")
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


def _resolve_effective_reference_v2(observation: AuditObservation) -> str:
    resolved_reference, _reason = _resolve_effective_reference_with_reason(observation)
    return resolved_reference


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


def _moderate_priority_v2(reference: str, observation: AuditObservation, priority: str) -> str:
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

    sensitivity_markers = (
        "t24",
        "core banking",
        "swift",
        "openbanking",
        "banque en ligne",
        "paie",
        "payroll",
        "client",
    )
    hard_critical = False
    if any(marker in text for marker in ("post-depart", "post depart", "apres depart", "depart")) and any(marker in text for marker in ("connexion", "connexions", "telecharg", "download", "exfil", "operation", "transaction", "mouvement")):
        hard_critical = True
    if any(marker in text for marker in ("sod", "separation des fonctions", "incompatib", "validation paiement", "paiement", "credit", "virement", "swift")) and amount >= 20:
        hard_critical = True
    if (reference or "").upper().strip() in {"CO-01", "CO-05", "CO-07"} and any(marker in text for marker in ("aucun test", "non teste", "pas teste")) and any(marker in text for marker in ("finance", "sap", "erp", "paiement", "t24", "core banking")):
        hard_critical = True
    if any(marker in text for marker in ("vulnerabilite critique", "sql injection", "escalade de privil", "cve", "cvss")) and any(marker in text for marker in ("openbanking", "banque en ligne", "client")):
        hard_critical = True
    if any(marker in text for marker in ("superuser", "compte generique", "shared", "partage")) and any(marker in text for marker in ("validation", "annulation", "virement", "swift")):
        hard_critical = True
    if any(marker in text for marker in sensitivity_markers) and amount >= 50:
        hard_critical = True

    return "Critical" if hard_critical else "High"


def _priority_trigger_reasons(reference: str, observation: AuditObservation) -> list[str]:
    ref = (reference or "").upper().strip()
    text = _keyword_text(
        reference,
        observation.titre_observation,
        observation.constat,
        observation.application,
        observation.categorie_controle,
        observation.impact_potentiel,
    )
    reasons: list[str] = []

    if any(marker in text for marker in ("post-depart", "post depart", "apres depart", "ancien collaborateur", "ancien prestataire")):
        reasons.append("post-departure or expired-contractor accounts remained active")
    if any(marker in text for marker in ("prestataire", "consultant", "fin de mission", "contrat expire")) and any(marker in text for marker in ("compte", "acces", "droits")):
        reasons.append("third-party access lifecycle controls did not enforce timely revocation")
    if any(marker in text for marker in ("operation", "transaction", "mouvement", "virement", "swift")) and any(marker in text for marker in ("post-depart", "post depart", "superuser", "compte generique", "compte partage")):
        reasons.append("sensitive banking operations were possible through uncontrolled access")
    if any(marker in text for marker in ("superuser", "compte generique", "compte partage", "privilegie")):
        reasons.append("privileged or shared accounts were not sufficiently controlled")
    if any(marker in text for marker in ("recertification", "revue periodique", "fonctions incompatibles", "4 yeux", "quatre yeux")):
        reasons.append("access recertification or segregation-of-duties controls were ineffective")
    if ref.startswith("PC-") or any(marker in text for marker in ("cab", "change advisory board", "mise en production")):
        reasons.append("production changes lacked formal approval or release governance")
    if any(marker in text for marker in ("developpement", "dev")) and any(marker in text for marker in ("production", "prod", "acces cumules")):
        reasons.append("segregation between development and production was weakened")
    if ref in {"CO-01", "CO-05", "CO-07"} or any(marker in text for marker in ("plan de reprise", "plan de continuite", "site de secours", "test de restauration", "procedure de restauration", "rpo", "rto")):
        reasons.append("resilience and recovery controls were not tested or not fully documented")
    if ref == "CO-08" or any(marker in text for marker in ("cve", "cvss", "vulnerabil", "security patch", "patch management")):
        reasons.append("known security vulnerabilities remained exposed beyond policy timelines")
    if ref == "CO-02" or any(marker in text for marker in ("ticketing", "helpdesk", "itsm", "cause racine", "rca")):
        reasons.append("incident response governance and traceability were insufficient")
    if any(marker in text for marker in ("mot de passe", "mots de passe", "password", "mfa", "2fa", "brute force", "tentatives suspectes")):
        reasons.append("authentication controls were insufficient for the sensitivity of the exposed service")
    if ref == "CO-03" or any(marker in text for marker in ("isae 3402", "soc 2", "sla", "kpi", "second niveau", "comite de pilotage", "comite de gouvernance")):
        reasons.append("third-party oversight and service control evidence were insufficient")

    return _deduplicate(reasons)


def _priority_decision_mode(
    *,
    base_priority: str,
    llm_priority_used: bool,
    enforced_priority: str,
    final_priority: str,
) -> str:
    parts = ["llm_validated" if llm_priority_used else "deterministic_fallback"]
    if enforced_priority != base_priority:
        parts.append("hard_floor_override")
    if final_priority != enforced_priority:
        parts.append("priority_moderation")
    return "+".join(parts)


def _recommendation_decision_mode(*, reasoning_ok: bool, recommendation_valid: bool) -> str:
    if reasoning_ok and recommendation_valid:
        return "llm_validated"
    return "contextual_fallback"


def _build_escalation_reason(
    *,
    observation: AuditObservation,
    reference: str,
    base_priority: str,
    final_priority: str,
    llm_priority_used: bool,
) -> str:
    reasons = _priority_trigger_reasons(reference, observation)
    if not reasons:
        reasons = ["overall exposure remains aligned with the detected control failure and impacted scope"]

    source_label = "validated LLM reasoning" if llm_priority_used else "deterministic fallback rules"
    joined_reasons = "; ".join(reasons[:3])

    if final_priority != base_priority:
        return f"Priority escalated from {base_priority} to {final_priority} by {source_label} because {joined_reasons}."
    return f"Priority set to {final_priority} by {source_label} because {joined_reasons}."


def _build_detailed_findings(
    audit_input: StructuredAuditInput,
    *,
    generated_at: str = "",
    report_version: str = "",
) -> list[DetailedFinding]:
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

        original_reference = (observation.controle_ref or "").upper().strip()
        effective_reference, resolved_reference_reason = _resolve_effective_reference_with_reason(observation)
        reasoning = reasoning_map.get(observation.observation_id)
        priority_reasoning = priority_reasoning_map.get(observation.observation_id)
        inferred_risk = (reasoning.risk if reasoning else "").strip()
        inferred_risk_scenario = (reasoning.risk_scenario if reasoning else "").strip()
        inferred_impact = (reasoning.impact if reasoning else "").strip()
        inferred_business_impact = (reasoning.business_impact if reasoning else "").strip()
        inferred_control_impact = (reasoning.control_impact if reasoning else "").strip()
        inferred_compliance_impact = (reasoning.compliance_impact if reasoning else "").strip()
        inferred_root_cause = (reasoning.root_cause if reasoning else "").strip() or _derive_root_cause(observation, effective_reference)
        inferred_aggravating_factors = (reasoning.aggravating_factors if reasoning else []) or []
        inferred_recommendation = (reasoning.recommendation if reasoning else "").strip()
        inferred_objective = (reasoning.recommendation_objective if reasoning else "").strip()
        inferred_immediate_action = (reasoning.immediate_action if reasoning else "").strip()
        inferred_structural_action = (reasoning.structural_action if reasoning else "").strip()
        inferred_owner = (reasoning.owner if reasoning else "").strip()
        inferred_evidence_expected = (reasoning.evidence_expected if reasoning else "").strip()
        inferred_follow_up_mechanism = (reasoning.follow_up_mechanism if reasoning else "").strip()
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

        impact_text = inferred_impact or _derive_business_impact(observation, effective_reference)
        if _looks_like_fact_restatement(impact_text, observation):
            impact_text = _derive_business_impact(observation, effective_reference)

        risk_scenario = inferred_risk_scenario or _derive_risk_scenario(observation, effective_reference, risk_text)
        deterministic_business_impact = _derive_business_impact(observation, effective_reference)
        business_impact = inferred_business_impact or impact_text
        if _business_impact_is_generic(business_impact) or (effective_reference in {"APD-01", "APD-03", "APD-04", "CO-05", "CO-08"} and inferred_business_impact):
            business_impact = deterministic_business_impact
        control_impact = inferred_control_impact or _derive_control_impact(observation, effective_reference)
        compliance_impact = inferred_compliance_impact or _derive_compliance_impact(observation)
        aggravating_factors = [
            str(item).strip() for item in (inferred_aggravating_factors or _derive_aggravating_factors(observation)) if str(item).strip()
        ]
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
            recommendation_text = _build_recommendation_v2(observation.model_copy(update={"controle_ref": effective_reference}))
            reco_objective = ""
            reco_steps = []

        reco_components = _build_recommendation_components(observation, effective_reference)
        immediate_action = inferred_immediate_action or str(reco_components["immediate_action"])
        structural_action = inferred_structural_action or str(reco_components["structural_action"])
        owner = inferred_owner or str(reco_components["owner"])
        evidence_expected = inferred_evidence_expected or str(reco_components["evidence_expected"])
        follow_up_mechanism = inferred_follow_up_mechanism or str(reco_components["follow_up_mechanism"])
        if not reco_objective:
            reco_objective = _build_recommendation_objective(observation, effective_reference)
        if not reco_steps:
            reco_steps = list(reco_components["steps"])  # type: ignore[arg-type]

        recommendation_mode = _recommendation_decision_mode(
            reasoning_ok=reasoning_ok and bool(inferred_recommendation.strip()),
            recommendation_valid=reco_ok,
        )

        base_priority = classify_priority(
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
        priority = base_priority
        if priority_reasoning_ok and inferred_priority in VALID_PRIORITIES:
            priority = inferred_priority
        priority_before_enforcement = priority

        # Final hard-minimum override layer.
        enforced_priority = enforce_min_priority(
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
        priority = _moderate_priority_v2(effective_reference, observation, enforced_priority)
        priority_mode = _priority_decision_mode(
            base_priority=priority_before_enforcement,
            llm_priority_used=priority_reasoning_ok and inferred_priority in VALID_PRIORITIES,
            enforced_priority=enforced_priority,
            final_priority=priority,
        )
        escalation_reason = _build_escalation_reason(
            observation=observation,
            reference=effective_reference,
            base_priority=priority_before_enforcement,
            final_priority=priority,
            llm_priority_used=priority_reasoning_ok and inferred_priority in VALID_PRIORITIES,
        )

        # Prefer LLM justification if it passed evidence validation AND the final priority matches it.
        if priority_reasoning_ok and inferred_priority_justification and inferred_priority == priority:
            priority_justification = inferred_priority_justification
        else:
            priority_justification = inferred_justification or _auto_priority_justification(observation, priority=priority)

        # Priority-aware enforcement: High/Critical must not be generic.
        if priority in {"Critical", "High"}:
            validation = validate_recommendation(observation.model_copy(update={"controle_ref": effective_reference}), recommendation_text)
            if (not validation.ok) or "recommendation_generic" in (validation.issues or []):
                recommendation_text = _build_recommendation_v2(observation.model_copy(update={"controle_ref": effective_reference}))
                reco_objective = _build_recommendation_objective(observation, effective_reference)
                reco_steps = list(reco_components["steps"])  # type: ignore[arg-type]
                reco_ok = False

        traceability = FindingTraceability(
            observation_source_id=observation.observation_id,
            original_reference=original_reference,
            resolved_reference=effective_reference,
            fields_used=[
                "observation_id",
                "controle_ref",
                "titre_observation",
                "constat",
                "application",
                "categorie_controle",
                "impact_potentiel",
                "cause_racine",
                "recommandation_proposee",
                "commentaire_auditeur",
                "references_probantes",
                "statut_validation",
            ],
            source_documents=_traceability_sources(observation),
            heuristic_rules_triggered=_traceability_rule_markers(
                observation,
                original_reference=original_reference,
                resolved_reference=effective_reference,
                priority_mode=priority_mode,
                recommendation_mode=recommendation_mode,
                reasoning_ok=reasoning_ok,
                priority_reasoning_ok=priority_reasoning_ok,
                final_priority=priority,
            ),
            confidence_score=_traceability_confidence(
                reasoning_ok=reasoning_ok,
                priority_reasoning_ok=priority_reasoning_ok,
                recommendation_valid=reco_ok,
                priority=priority,
                priority_justification=priority_justification,
            ),
            priority_justification=priority_justification,
            priority_decision_mode=priority_mode,
            recommendation_decision_mode=recommendation_mode,
            agent="report_agent",
            generated_at=generated_at,
            report_version=report_version,
        )

        findings.append(
            DetailedFinding(
                observation_id=observation.observation_id,
                original_reference=original_reference,
                reference=effective_reference,
                resolved_reference_reason=resolved_reference_reason,
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
                risk_scenario=risk_scenario,
                impact_detail=impact_text,
                business_impact=business_impact,
                control_impact=control_impact,
                compliance_impact=compliance_impact,
                root_cause=inferred_root_cause,
                aggravating_factors=aggravating_factors,
                recommendation=recommendation_text,
                recommendation_objective=reco_objective,
                immediate_action=immediate_action,
                structural_action=structural_action,
                owner=owner,
                evidence_expected=evidence_expected,
                follow_up_mechanism=follow_up_mechanism,
                recommendation_steps=[step for step in (reco_steps or []) if step and str(step).strip()],
                recommendation_decision_mode=recommendation_mode,
                priority=priority,
                priority_justification=priority_justification,
                priority_decision_mode=priority_mode,
                escalation_reason=escalation_reason,
                auditor_comment=observation.commentaire_auditeur,
                management_summary=_build_management_summary(
                    observation.model_copy(update={"controle_ref": effective_reference}),
                    priority=priority,
                    risk=risk_text,
                    impact=impact_text,
                    root_cause=inferred_root_cause,
                    priority_justification=priority_justification,
                ),
                traceability=traceability,
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
        reference = _resolve_effective_reference_v2(observation)
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
        ref = _resolve_effective_reference_v2(observation)
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
            effective_ref = _resolve_effective_reference_v2(observation)
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
                    "priority_reason": finding.escalation_reason or finding.priority_justification or "generated_pipeline",
                    "priority_source": finding.priority_decision_mode or "generated_pipeline",
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
    generated_at = _utc_timestamp()
    report_version = f"{mission.mission_id or 'mission'}:{generated_at}"
    findings = _build_detailed_findings(audit_input, generated_at=generated_at, report_version=report_version)
    general_synthesis, executive_summary, conclusion = _build_general_synthesis(findings, audit_input)
    maturity_level = _derive_maturity_level(findings)
    transversal_initiatives = _build_transversal_initiatives(findings)

    # Covered controls: include catalog controls for the mission + any observed control refs not in the catalog.
    observed_refs: dict[str, AuditObservation] = {}
    for obs in audit_input.observations:
        ref = _resolve_effective_reference_v2(obs)
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
        "Cadre de notre intervention et démarche",
        "Synthèse générale",
        "Recommandations détaillées",
        "Annexes",
    ]

    report_output = AuditReportOutput(
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
    report_output.quality_gate = evaluate_report_quality_gate(audit_input, report_output)
    return report_output
