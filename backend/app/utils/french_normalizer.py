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
    "scenario": "scénario",
    "metier": "métier",
    "donnees": "données",
    "autorisee": "autorisée",
    "autorise": "autorisé",
    "identifies": "identifiés",
    "identifiees": "identifiées",
    "desactivation": "désactivation",
    "desactiver": "désactiver",
    "desactive": "désactivé",
    "desactives": "désactivés",
    "delai": "délai",
    "delais": "délais",
    "accuse": "accusé",
    "tracabilite": "traçabilité",
    "responsabilites": "responsabilités",
    "periodique": "périodique",
    "periodiques": "périodiques",
    "execution": "exécution",
    "associes": "associés",
    "residuels": "résiduels",
    "systematique": "systématique",
    "exhaustivite": "exhaustivité",
    "formalise": "formalisé",
    "formalisee": "formalisée",
    "formalises": "formalisés",
    "tracable": "traçable",
    "recurrent": "récurrent",
    "legitimes": "légitimes",
    "regularisation": "régularisation",
    "resultats": "résultats",
    "equipes": "équipes",
    "apres": "après",
    "jusqu": "jusqu",
    "taches": "tâches",
    "segregation": "ségrégation",
    "individuellement": "individuellement",
    "independant": "indépendant",
    "indisponibilite": "indisponibilité",
    "incapacite": "incapacité",
    "vulnerabilites": "vulnérabilités",
    "exposes": "exposés",
    "alteration": "altération",
    "legitime": "légitime",
    "operations": "opérations",
    "operation": "opération",
    "perimetre": "périmètre",
    "concerne": "concerné",
    "concernee": "concernée",
    "concernes": "concernés",
    "criticite": "criticité",
    "fenetre": "fenêtre",
    "fenetres": "fenêtres",
    "deploiement": "déploiement",
    "deploiements": "déploiements",
    "deployer": "déployer",
    "deployee": "déployée",
    "deployees": "déployées",
    "remediation": "remédiation",
    "remediations": "remédiations",
    "maitrise": "maîtrise",
    "continuité": "continuité",
    "continuite": "continuité",
    "scenarios": "scénarios",
    "criteres": "critères",
    "ecarts": "écarts",
    "comite": "comité",
    "comites": "comités",
    "depassant": "dépassant",
    "accelere": "accéléré",
    "acceleree": "accélérée",
    "acceleres": "accélérés",
    "accelerees": "accélérées",
    "deploiement": "déploiement",
    "documente": "documenté",
    "documentee": "documentée",
    "documentes": "documentés",
    "ciblee": "ciblée",
    "ciblees": "ciblées",
    "cumules": "cumulés",
    "developpement": "développement",
    "separation": "séparation",
    "necessaires": "nécessaires",
    "cloturees": "clôturées",
    "recurrents": "récurrents",
    "residuels": "résiduels",
    "exposees": "exposées",
    "externalisees": "externalisées",
    "externalises": "externalisés",
    "derogation": "dérogation",
    "derogations": "dérogations",
    "concernees": "concernées",
    "systeme": "système",
    "systemes": "systèmes",
    "equipe": "équipe",
    "etat": "état",
    "etats": "états",
    "presente": "présente",
    "presenter": "présenter",
    "audite": "audité",
    "auditee": "auditée",
    "justifie": "justifié",
    "justifies": "justifiés",
    "justifiee": "justifiée",
    "justifiees": "justifiées",
    "echeance": "échéance",
    "echeances": "échéances",
    "element": "élément",
    "elements": "éléments",
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
    (re.compile(r"\bpost[- ]depart\b", re.IGNORECASE), "post-départ"),
    (re.compile(r"\bpost[- ]départ\b", re.IGNORECASE), "post-départ"),
    (re.compile(r"\bjusqu['’]?a\b", re.IGNORECASE), "jusqu'à"),
    (re.compile(r"\ba\s+l'utilisation\b", re.IGNORECASE), "à l'utilisation"),
    (re.compile(r"\ba\s+des\b", re.IGNORECASE), "à des"),
    (re.compile(r"\ba\s+fort\b", re.IGNORECASE), "à fort"),
    (re.compile(r"\ba\s+d'anciens\b", re.IGNORECASE), "à d'anciens"),
    (re.compile(r"\bappartenant\s+a\b", re.IGNORECASE), "appartenant à"),
    (re.compile(r"\bincapacite\s+a\b", re.IGNORECASE), "incapacité à"),
    (re.compile(r"\betre\s+exploite", re.IGNORECASE), "être exploité"),
    (re.compile(r"\bpresence\s+d['’]elements\b", re.IGNORECASE), "présence d'éléments"),
    (re.compile(r"\bpresence\s+d\s+elements\b", re.IGNORECASE), "présence d'éléments"),
    (re.compile(r"\bbase\s+sur\b", re.IGNORECASE), "basé sur"),
    (re.compile(r"\bpreuve attendue\s*:\s*preuve attendue\s*:\s*", re.IGNORECASE), "Preuve attendue : "),
    (re.compile(r"\bpreuves?\s+attendues?\s*:\s*produire et archiver les preuves suivantes\s*:\s*", re.IGNORECASE), "Produire et archiver les preuves suivantes : "),
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
