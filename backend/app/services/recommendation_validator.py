from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.audit_input import AuditObservation


@dataclass(frozen=True)
class RecommendationValidation:
    ok: bool
    issues: list[str]


_GENERIC_MARKERS = (
    "definir un plan d'action",
    "définir un plan d'action",
    "plan d'action cible",
    "traiter durablement le constat",
    "en assurer le suivi",
    "mettre en oeuvre la recommandation suivante",
)


_ACTION_VERBS = (
    "mettre en place",
    "deployer",
    "déployer",
    "formaliser",
    "renforcer",
    "restreindre",
    "corriger",
    "mettre a jour",
    "mettre à jour",
    "planifier",
    "documenter",
    "superviser",
    "configurer",
    "instituer",
    "instaurer",
    "exiger",
    "interdire",
    "automatiser",
    "centraliser",
)


def _keyword_text(*values: str) -> str:
    # Keep this local: validator should not depend on other services.
    import unicodedata

    text = " ".join(value for value in values if value)
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return normalized.lower()


def _is_generic(recommendation: str) -> bool:
    lowered = _keyword_text(recommendation or "")
    if not lowered.strip():
        return True
    return any(marker in lowered for marker in _GENERIC_MARKERS)


def _has_action_verb(recommendation: str) -> bool:
    lowered = _keyword_text(recommendation or "").strip()
    if not lowered:
        return False
    # Check the beginning first (most audit recommendations start with an infinitive).
    head = lowered[:80]
    if any(head.startswith(v) for v in _ACTION_VERBS):
        return True
    # Also accept bullet lists ("- Mettre en place ...")
    if head.startswith("- ") and any(v in head for v in _ACTION_VERBS):
        return True
    return any(v in lowered for v in _ACTION_VERBS)


def _seems_off_topic(observation: AuditObservation, recommendation: str) -> bool:
    """
    Very conservative mismatch detection.
    We only flag *strong* cross-domain mismatches to avoid false positives.
    """
    ref = (observation.controle_ref or "").upper().strip()
    text = _keyword_text(recommendation or "")

    # Backup/restore controls should not get PAM/DBA-specific recommendations.
    if ref in {"CO-01", "CO-07"}:
        return any(k in text for k in ("dba", "pam", "coffre-fort", "coffre fort", "privileg", "administrateur"))

    # Patching should not receive backup/PRA-only recommendations.
    if ref == "CO-08":
        return any(k in text for k in ("sauvegarde", "backup", "restauration", "pra", "pca", "drp"))

    # Incident management should not be expressed as change management.
    if ref == "CO-02":
        return any(
            k in text
            for k in (
                "cab",
                "mise en production",
                "recette",
                "transport",
                "deploiement",
                "prestataire",
                "contractualiser",
                "comite de pilotage",
                "comites",
            )
        )

    # Privileged-account supervision should not receive password-policy-only actions.
    if ref == "APD-03":
        return any(
            k in text
            for k in (
                "complexite des mots de passe",
                "historique",
                "expiration",
                "verrouillage",
                "pam_faillock",
            )
        )

    # Password policy should not receive PAM / privileged-account supervision actions only.
    if ref == "APD-05":
        return any(
            k in text
            for k in (
                "compte nominatif",
                "compte partage",
                "journalisation",
                "supervision periodique des usages",
            )
        )

    # Change management should not be expressed as incident SLA management.
    if ref.startswith("PC-"):
        return any(k in text for k in ("sla", "delai de resolution", "ticketing incident"))

    return False


def validate_recommendation(observation: AuditObservation, recommendation: str) -> RecommendationValidation:
    issues: list[str] = []
    value = (recommendation or "").strip()

    if not value:
        issues.append("recommendation_empty")
        return RecommendationValidation(ok=False, issues=issues)

    if _is_generic(value):
        issues.append("recommendation_generic")

    if not _has_action_verb(value):
        issues.append("recommendation_missing_action_verb")

    if _seems_off_topic(observation, value):
        issues.append("recommendation_off_topic_vs_control")

    ok = not any(
        issue in issues
        for issue in (
            "recommendation_empty",
            "recommendation_generic",
            "recommendation_off_topic_vs_control",
        )
    )
    return RecommendationValidation(ok=ok, issues=issues)
