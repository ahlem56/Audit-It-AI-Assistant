from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.audit_input import AuditObservation
from app.models.priority_reasoning import PriorityReasoning


@dataclass(frozen=True)
class PriorityValidation:
    ok: bool
    issues: list[str]


_NUM_RE = re.compile(r"\b\d+\b")
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\-]{2,}")

_STOPWORDS = {
    # Very small FR stopword set (we only need to detect overlap of meaningful terms).
    "les",
    "des",
    "une",
    "un",
    "de",
    "du",
    "la",
    "le",
    "et",
    "ou",
    "dans",
    "sur",
    "au",
    "aux",
    "par",
    "pour",
    "avec",
    "sans",
    "est",
    "sont",
    "etre",
    "être",
    "a",
    "à",
    "ont",
    "afin",
    "que",
    "qui",
    "dont",
    "plus",
    "moins",
    "aucun",
    "aucune",
    "absence",
    "niveau",
    "controle",
    "contrôle",
    "constat",
    "revue",
}


def _extract_numbers(text: str) -> set[str]:
    return set(_NUM_RE.findall(text or ""))


def _has_evidence_language(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        marker in lowered
        for marker in (
            "échantillon",
            "echantillon",
            "sur l'échantillon",
            "sur l'echantillon",
            "aucun",
            "aucune",
            "absence",
            "parmi",
            "dont",
            "taux",
            "%",
        )
    )


def _extract_keywords(text: str) -> set[str]:
    """
    Extract a small set of meaningful words for "fact reference" detection.
    Not linguistic-perfect; just enough for soft validation.
    """
    lowered = (text or "").lower()
    words = set()
    for token in _WORD_RE.findall(lowered):
        token = token.strip("'-")
        if len(token) < 5:
            continue
        if token in _STOPWORDS:
            continue
        words.add(token)
    return words


def validate_priority_reasoning(observation: AuditObservation, reasoning: PriorityReasoning) -> PriorityValidation:
    """
    Accept the LLM priority only if it is justified by evidence (numbers or explicit evidence language),
    to avoid empty/hand-wavy justifications.
    """
    issues: list[str] = []

    justification = (reasoning.priority_justification or "").strip()
    if not justification:
        issues.append("priority_justification_empty")
        return PriorityValidation(ok=False, issues=issues)

    constat_numbers = _extract_numbers(observation.constat)
    justification_numbers = _extract_numbers(justification)

    # Soft validation:
    # - If numbers exist in the finding, we prefer reuse but do NOT require exact matching.
    # - Evidence language or clear references to finding facts is acceptable.
    has_number_overlap = bool(constat_numbers & justification_numbers)
    has_evidence_language = _has_evidence_language(justification)

    if constat_numbers and not has_number_overlap and not has_evidence_language:
        # If no numbers and no evidence language, allow keyword overlap as "fact referencing".
        finding_kw = _extract_keywords(observation.constat)
        just_kw = _extract_keywords(justification)
        overlap = len(finding_kw & just_kw)
        if overlap < 2:
            issues.append("priority_justification_weak_fact_reference")

    if not constat_numbers and not has_evidence_language:
        finding_kw = _extract_keywords(observation.constat)
        just_kw = _extract_keywords(justification)
        overlap = len(finding_kw & just_kw)
        if overlap < 2:
            issues.append("priority_justification_missing_evidence_language")

    ok = not any(
        issue in issues
        for issue in (
            "priority_justification_weak_fact_reference",
            "priority_justification_missing_evidence_language",
        )
    )
    return PriorityValidation(ok=ok, issues=issues)
