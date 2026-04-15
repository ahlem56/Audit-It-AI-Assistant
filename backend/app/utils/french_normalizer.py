from __future__ import annotations

import re


_WORD_MAP = {
    # Common audit vocabulary (ASCII -> accented)
    "acces": "accès",
    "entite": "entité",
    "controle": "contrôle",
    "controles": "contrôles",
    "controle interne": "contrôle interne",
    "controles generaux informatiques": "contrôles généraux informatiques",
    "generaux": "généraux",
    "informatiques": "informatiques",
    "elevee": "élevée",
    "elevees": "élevées",
    "eleve": "élevé",
    "eleves": "élevés",
    "parametrage": "paramétrage",
    "periode": "période",
    "realisees": "réalisées",
    "realisee": "réalisée",
    "realiser": "réaliser",
    "realisation": "réalisation",
    "recuperabilite": "récupérabilité",
    "maturite": "maturité",
    "appreciation": "appréciation",
    # Don't rewrite "evidence" blindly: it breaks locked phrases like "mis en evidence".
    "hierarchique": "hiérarchique",
    "privilegies": "privilégiés",
    "privilegie": "privilégié",
    "generiques": "génériques",
    "generique": "générique",
    "securite": "sécurité",
    "parametres": "paramètres",
    # Prefer sentence-level templates/LLM for rephrasing; keep this normalizer conservative.
}


_PHRASE_PATTERNS = [
    # Contractions and apostrophes
    (re.compile(r"\bde\s+acc[eè]s\b", re.IGNORECASE), "d'accès"),
    (re.compile(r"\bde\s+entite\b", re.IGNORECASE), "d'entité"),
    (re.compile(r"\bde\s+exiger\b", re.IGNORECASE), "d'exiger"),
    (re.compile(r"\ble\s+acc[eè]s\b", re.IGNORECASE), "l'accès"),
    (re.compile(r"\ble\s+entite\b", re.IGNORECASE), "l'entité"),
    (re.compile(r"\bl\s+entite\b", re.IGNORECASE), "l'entité"),
    # Agreements (common audit patterns)
    (re.compile(r"\bfaiblesses\s+critique\b", re.IGNORECASE), "faiblesses critiques"),
    (re.compile(r"\bfaiblesses\s+elevee\b", re.IGNORECASE), "faiblesses élevées"),
    (re.compile(r"\bpriorite\s+elevee\b", re.IGNORECASE), "priorité élevée"),
    (re.compile(r"\bpriorite\s+critique\b", re.IGNORECASE), "priorité critique"),
]


_LOCKED_PHRASES = [
    "mis en évidence",
    "niveau de maturité",
    "contrôle interne",
    "contrôles généraux informatiques",
    "risque d'accès",
]


def _preserve_simple_case(original: str, replacement: str) -> str:
    # Preserve simple TitleCase / UPPER based on the matched token.
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def normalize_french(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return value

    # Protect critical phrases from any rewrite.
    locked_tokens: dict[str, str] = {}
    protected = value
    for idx, phrase in enumerate(_LOCKED_PHRASES, start=1):
        token = f"__LOCKED_{idx}__"
        # Match both accented and ASCII variants for a few phrases.
        if phrase == "mis en évidence":
            protected = re.sub(r"\bmis en eviden[ct]e\b", token, protected, flags=re.IGNORECASE)
            locked_tokens[token] = "mis en évidence"
        elif phrase == "niveau de maturité":
            protected = re.sub(r"\bniveau de maturit[eé]\b", token, protected, flags=re.IGNORECASE)
            locked_tokens[token] = "niveau de maturité"
        elif phrase == "contrôle interne":
            protected = re.sub(r"\bcontrole interne\b", token, protected, flags=re.IGNORECASE)
            locked_tokens[token] = "contrôle interne"
        elif phrase == "contrôles généraux informatiques":
            protected = re.sub(r"\bcontroles generaux informatiques\b", token, protected, flags=re.IGNORECASE)
            locked_tokens[token] = "contrôles généraux informatiques"
        elif phrase == "risque d'accès":
            protected = re.sub(r"\brisque de\s+acc[eè]s\b", token, protected, flags=re.IGNORECASE)
            locked_tokens[token] = "risque d'accès"

    # First: phrase-level fixes (apostrophes etc.)
    for pattern, repl in _PHRASE_PATTERNS:
        protected = pattern.sub(repl, protected)

    # Then: word/phrase map using word boundaries, longest-first to avoid partial overlaps.
    for source in sorted(_WORD_MAP.keys(), key=len, reverse=True):
        target = _WORD_MAP[source]
        pattern = re.compile(rf"\b{re.escape(source)}\b", re.IGNORECASE)

        def _sub(match: re.Match) -> str:
            return _preserve_simple_case(match.group(0), target)

        protected = pattern.sub(_sub, protected)

    # Normalize common spacing issues
    protected = re.sub(r"\s+([.,;:])", r"\1", protected)
    protected = re.sub(r"\s{2,}", " ", protected)

    for token, phrase in locked_tokens.items():
        protected = protected.replace(token, phrase)

    return protected
