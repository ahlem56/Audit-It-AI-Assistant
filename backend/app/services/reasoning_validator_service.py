from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.audit_input import AuditObservation
from app.models.observation_reasoning import ObservationReasoning
from app.models.priority_reasoning import PriorityReasoning


@dataclass(frozen=True)
class ReasoningValidation:
    ok: bool
    issues: list[str]


@dataclass(frozen=True)
class PriorityValidation:
    ok: bool
    issues: list[str]


_NUM_RE = re.compile(r"\b\d+\b")
_WORD_RE = re.compile(r"[^\W\d_][^\W\d_'\-]{2,}", re.UNICODE)

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
    "Ãªtre",
    "a",
    "Ã ",
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
    "contrÃ´le",
    "constat",
    "revue",
}


def _extract_numbers(text: str) -> set[str]:
    return set(_NUM_RE.findall(text or ""))


def _has_observation_evidence_keywords(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        marker in lowered
        for marker in (
            "echantillon",
            "sur l'echantillon",
            "sur lâ€™echantillon",
            "aucun",
            "aucune",
            "absence",
            "0 ",
            "zero",
            "plusieurs",
            "total",
            "parmi",
        )
    )


def _has_priority_evidence_language(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        marker in lowered
        for marker in (
            "Ã©chantillon",
            "echantillon",
            "sur l'Ã©chantillon",
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


def validate_reasoning(observation: AuditObservation, reasoning: ObservationReasoning) -> ReasoningValidation:
    issues: list[str] = []

    constat_numbers = _extract_numbers(observation.constat)
    justification_numbers = _extract_numbers(reasoning.priority_justification)

    # If the finding includes digits, we expect justification to reuse at least one of them.
    if constat_numbers and not (constat_numbers & justification_numbers):
        issues.append("priority_justification_missing_factual_numbers")

    # If there are no digits, still require explicit evidence language.
    if not constat_numbers and reasoning.priority_justification and not _has_observation_evidence_keywords(reasoning.priority_justification):
        issues.append("priority_justification_missing_evidence_language")

    # If justification is empty, it is always weak (will be auto-generated downstream).
    if not (reasoning.priority_justification or "").strip():
        issues.append("priority_justification_empty")

    ok = not any(
        issue in issues
        for issue in (
            "priority_justification_missing_factual_numbers",
            "priority_justification_missing_evidence_language",
        )
    )
    return ReasoningValidation(ok=ok, issues=issues)


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
    has_evidence_language = _has_priority_evidence_language(justification)

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
