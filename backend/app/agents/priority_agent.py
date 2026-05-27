from __future__ import annotations

import re
import unicodedata

VALID_PRIORITIES = {"Critical", "High", "Medium", "Low"}
_PRIORITY_RANK = {"Critical": 3, "High": 2, "Medium": 1, "Low": 0}


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()


_NUM_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")
_AMOUNT_RE = re.compile(r"(\d[\d\s.,]{2,})\s*(tnd|dt|dinar|dinars|eur|usd|â‚¬|\\$)?", re.IGNORECASE)


def _extract_numbers(text: str) -> list[float]:
    values: list[float] = []
    for token in _NUM_RE.findall(text or ""):
        token = token.replace(" ", "").replace(",", ".")
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def _extract_amount(text: str) -> float:
    # Best-effort: returns the max amount seen in text.
    best = 0.0
    for raw, _ccy in _AMOUNT_RE.findall(text or ""):
        cleaned = raw.replace(" ", "").replace("\u00a0", "").replace(",", ".")
        cleaned = cleaned.strip(".")
        try:
            val = float(cleaned)
        except ValueError:
            continue
        best = max(best, val)
    return best


def _score_priority(input_data: dict) -> int:
    """
    Deterministic baseline scoring (0-100).

    IMPORTANT:
    This is a SAFETY NET only. The main engine is the LLM-based priority reasoning agent.
    Keep this stable, but sufficiently expressive to distinguish serious "High"
    issues from the few situations that should remain "Critical".
    """
    ref = str(input_data.get("controle_ref", "") or input_data.get("reference", "")).upper().strip()
    title = str(input_data.get("title", "") or "")
    constat = str(input_data.get("condition", "") or input_data.get("constat", "") or "")
    category = str(input_data.get("category", "") or "")
    impact = str(input_data.get("impact", "") or input_data.get("impact_potentiel", "") or "")
    application = str(input_data.get("application", "") or "")

    text = _normalize(" ".join([ref, title, constat, category, impact, application]))

    nums = _extract_numbers(constat)
    max_num = max(nums) if nums else 0.0
    amount = _extract_amount(constat)

    baseline = 10

    if any(
        k in text
        for k in (
            "core banking",
            "t24",
            "swift",
            "openbanking",
            "banque en ligne",
            "payroll",
            "paie",
            "rh",
            "client",
            "production",
        )
    ):
        baseline += 8

    if any(k in text for k in ("absence", "aucun", "aucune", "non formalise", "non supervise", "non documente")):
        baseline += 8

    if any(k in text for k in ("post depart", "post-depart", "apres depart", "depart")) and any(k in text for k in ("compte", "utilisateur")):
        baseline = max(baseline, 68)
        if max_num >= 3:
            baseline += 8
        if any(k in text for k in ("connex", "connexion", "operation", "transaction", "mouvement")):
            baseline = max(baseline, 82)
        if any(k in text for k in ("telecharg", "download", "exfil")):
            baseline = max(baseline, 90)

    if any(k in text for k in ("sod", "separation of duties", "separation des fonctions", "incompatib", "auto-valid", "paiement", "payment")):
        baseline = max(baseline, 70)
        if max_num >= 10:
            baseline += 6
        if amount >= 20000 or any(k in text for k in ("credit", "virement", "swift", "fort encours")):
            baseline = max(baseline, 86)

    if any(k in text for k in ("dba", "administrateur", "privileg", "root", "superuser", "teller_admin")) and any(k in text for k in ("partag", "shared", "compte generique", "comptes generiques", "compte partage", "comptes partages")):
        baseline = max(baseline, 72)
        if any(k in text for k in ("sans supervision", "non supervise", "interactive", "interactif", "validation", "annulation")):
            baseline = max(baseline, 82)

    if any(k in text for k in ("mot de passe", "mots de passe", "password", "mfa", "2fa", "authentification")):
        baseline = max(baseline, 58)
        if any(k in text for k in ("openbanking", "banque en ligne", "client", "virement")):
            baseline = max(baseline, 68)
        if any(k in text for k in ("absence", "non gere", "non geree", "brute force", "tentatives suspectes")):
            baseline += 6

    if any(k in text for k in ("pra", "pca", "drp", "plan de reprise")) and any(k in text for k in ("non teste", "pas teste", "aucun test", "18 mois", "24 mois", "12 mois")):
        baseline = max(baseline, 72)
        if any(k in text for k in ("rto", "rpo", "restauration", "site de secours")):
            baseline += 8
        if any(k in text for k in ("finance", "erp", "paiement", "t24", "core banking")):
            baseline = max(baseline, 86)

    if any(k in text for k in ("correctif", "patch", "vulnerabil", "cve", "openssl", "escalade de privileg")):
        baseline = max(baseline, 68)
        if any(k in text for k in ("critique", "cvss", "retard", "exploitable")):
            baseline = max(baseline, 76)
        if max_num >= 10 or any(k in text for k in ("banque en ligne", "openbanking", "session client", "client")):
            baseline = max(baseline, 86)

    if any(k in text for k in ("developpeur", "developpement", "dev")) and any(k in text for k in ("production", "prod")):
        baseline = max(baseline, 66)
        if any(k in text for k in ("acces cumul", "separation", "segreg", "simultane")):
            baseline = max(baseline, 74)
        if max_num >= 5:
            baseline += 6

    if any(k in text for k in ("isae", "soc 2", "prestataire", "sla", "kpi", "second niveau", "comite de pilotage")):
        baseline = max(baseline, 56)
        if any(k in text for k in ("absence", "aucun", "aucune")):
            baseline = max(baseline, 66)
        if any(k in text for k in ("core banking", "openbanking", "maintenance applicative")):
            baseline = max(baseline, 72)

    return max(0, min(100, int(baseline)))


def _score_to_priority(score: int) -> str:
    if score >= 80:
        return "Critical"
    if score >= 60:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def _max_priority(a: str, b: str) -> str:
    if _PRIORITY_RANK.get(a, -1) >= _PRIORITY_RANK.get(b, -1):
        return a
    return b


def enforce_min_priority(observation: dict, priority: str) -> str:
    """
    Final safety layer: enforce minimum audit-grade priority based on hard red flags,
    so critical risks cannot be downgraded by wording or model variability.

    This function should remain small and stable (hard rules only).
    """
    ref = str(observation.get("controle_ref", "") or observation.get("reference", "")).upper().strip()
    title = str(observation.get("title", "") or "")
    constat = str(observation.get("condition", "") or observation.get("constat", "") or "")
    application = str(observation.get("application", "") or "")
    category = str(observation.get("category", "") or "")
    impact = str(observation.get("impact", "") or observation.get("impact_potentiel", "") or "")

    text = _normalize(" ".join([ref, title, constat, application, category, impact]))
    amount = _extract_amount(constat)
    nums = _extract_numbers(constat)
    max_num = max(nums) if nums else 0.0

    minimum = "Low"

    app_text = _normalize(application)
    is_critical_app = any(
        k in (app_text + " " + text)
        for k in (
            "finance",
            "finance360",
            "rh",
            "paie",
            "payroll",
            "banque",
            "core banking",
            "t24",
            "swift",
            "openbanking",
        )
    )
    if is_critical_app:
        minimum = _max_priority(minimum, "Medium")

    if any(
        k in text
        for k in (
            "donnees personnelles",
            "donnees rh",
            "dossiers rh",
            "salaire",
            "paie",
            "identite",
            "cin",
            "rib",
            "iban",
            "pii",
        )
    ):
        minimum = _max_priority(minimum, "High")

    if any(k in text for k in ("compte generique", "comptes generiques", "compte partage", "comptes partages", "compte partagee", "compte commun", "shared account", "generic account")):
        minimum = _max_priority(minimum, "High")

    if any(k in text for k in ("post depart", "post-depart", "apres depart", "depart")) and any(k in text for k in ("compte", "accounts", "utilisateur")):
        if any(k in text for k in ("connex", "connexion", "operation", "transaction", "mouvement")):
            minimum = _max_priority(minimum, "High")
        if any(k in text for k in ("telecharg", "download", "exfil")):
            minimum = _max_priority(minimum, "Critical")
        if max_num >= 3 and any(k in text for k in ("client", "fort encours", "t24", "core banking")):
            minimum = _max_priority(minimum, "Critical")

    if any(k in text for k in ("dba", "administrateur", "privileg", "root", "superuser", "teller_admin")) and any(k in text for k in ("partag", "shared", "compte generique", "comptes generiques", "compte partage", "comptes partages")):
        minimum = _max_priority(minimum, "High")
        if any(k in text for k in ("validation", "annulation", "virement", "swift", "interactive", "interactif")):
            minimum = _max_priority(minimum, "Critical")

    if any(k in text for k in ("mot de passe", "mots de passe", "password", "mfa", "2fa", "authentification")):
        minimum = _max_priority(minimum, "Medium")
        if any(k in text for k in ("openbanking", "banque en ligne", "client", "virement", "donnees personnelles")):
            minimum = _max_priority(minimum, "High")

    if any(k in text for k in ("sod", "separation des fonctions", "separation of duties", "incompatib", "auto-valid")):
        minimum = _max_priority(minimum, "High")
        if amount >= 20000 or any(k in text for k in ("credit", "virement", "swift", "fort encours")):
            minimum = _max_priority(minimum, "Critical")

    if any(k in text for k in ("vulnerabil", "patch", "correctif", "cve")) and any(k in text for k in ("critique", "eleve", "retard", "cvss", "injection sql", "escalade")):
        minimum = _max_priority(minimum, "High")
        if max_num >= 10 and any(k in text for k in ("openbanking", "banque en ligne", "client")):
            minimum = _max_priority(minimum, "Critical")

    if any(k in text for k in ("pra", "pca", "drp", "plan de reprise")) and any(k in text for k in ("non teste", "pas teste", "aucun test", "18 mois", "24 mois", "12 mois")):
        minimum = _max_priority(minimum, "High")
        if any(k in text for k in ("finance", "erp", "paiement", "t24", "core banking")):
            minimum = _max_priority(minimum, "Critical")

    if any(k in text for k in ("sauvegarde", "backup", "restauration")) and any(k in text for k in ("aucun test", "non teste", "pas teste")):
        minimum = _max_priority(minimum, "High")

    if any(k in text for k in ("sauvegarde", "backup")) and any(k in text for k in ("echec", "echecs", "erreur", "failed")):
        if "%" in (constat or ""):
            minimum = _max_priority(minimum, "High")

    if any(k in text for k in ("developpeur", "developpement", "dev")) and any(k in text for k in ("production", "prod")):
        if any(k in text for k in ("r/w", "rw", "lecture/ecriture", "lecture", "ecriture", "read", "write", "modification", "simultane")):
            minimum = _max_priority(minimum, "High")

    if any(k in text for k in ("recertification", "re certification", "revue")) and any(k in text for k in ("superuser", "administrateur", "privileg")):
        if any(k in text for k in ("aucune", "absence", "jamais", "non realise", "non effectue")) and any(k in text for k in ("12 mois", "16 mois", "18 mois", "24 mois", "mois")):
            minimum = _max_priority(minimum, "High")

    if any(k in text for k in ("cab", "change advisory board", "mise en production", "changement")) and any(k in text for k in ("sans validation", "absence de validation", "ne comporte pas de validation", "non valide")):
        minimum = _max_priority(minimum, "Medium")
        if max_num >= 10:
            minimum = _max_priority(minimum, "High")

    return _max_priority(priority, minimum)


def _derive_impact_level(input_data: dict) -> str:
    signal = " ".join(
        [
            str(input_data.get("impact", "")),
            str(input_data.get("risk_impact", "")),
            str(input_data.get("condition", "")),
            str(input_data.get("title", "")),
        ]
    )
    text = _normalize(signal)

    high_markers = (
        "connexion post-depart",
        "post depart",
        "compte actif apres depart",
        "privileg",
        "administrateur",
        "transaction critique",
        "droit sensible",
        "production",
        "perte de donnees",
        "indisponibilite",
        "aucun test de restauration",
        "non autoris",
        "sans validation",
    )
    medium_markers = (
        "absence de revue",
        "revue non formalisee",
        "sla",
        "incident",
        "procedure compensatoire",
        "controle informel",
        "non consolide",
        "parametrage",
        "mot de passe",
    )

    if any(marker in text for marker in high_markers):
        return "High"
    if any(marker in text for marker in medium_markers):
        return "Medium"
    return "Low"


def _derive_risk_level(input_data: dict) -> str:
    signal = " ".join(
        [
            str(input_data.get("risk_impact", "")),
            str(input_data.get("condition", "")),
            str(input_data.get("title", "")),
            str(input_data.get("category", "")),
        ]
    )
    text = _normalize(signal)

    critical_markers = (
        "fraud",
        "fraude",
        "post depart",
        "non autoris",
        "privileg",
        "administrateur",
        "production et developpement",
        "production cumule",
    )
    high_markers = (
        "perte de donnees",
        "indisponibilite",
        "sauvegarde",
        "restauration",
        "changement",
        "mise en production",
        "mot de passe",
        "transaction critique",
        "droit sensible",
    )

    if any(marker in text for marker in critical_markers):
        return "High"
    if any(marker in text for marker in high_markers):
        return "Medium"
    return "Low"


def _deterministic_priority(input_data: dict) -> str:
    score = _score_priority(input_data)
    prio = _score_to_priority(score)
    if prio in VALID_PRIORITIES:
        return prio

    impact = _derive_impact_level(input_data)
    risk = _derive_risk_level(input_data)

    if impact == "High" and risk == "High":
        return "Critical"
    if impact == "High":
        return "High"
    if impact == "Medium" or risk == "Medium":
        return "Medium"
    return "Low"


class PriorityAgent:
    def run(self, input_data: dict) -> str:
        return _deterministic_priority(input_data)


def classify_priority(observation: dict) -> str:
    priority = PriorityAgent().run(observation)
    return priority if priority in VALID_PRIORITIES else "Low"
