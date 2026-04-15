from __future__ import annotations

import json
from typing import Iterable

from app.services.llm_clients import get_chat_llm
from app.utils.json_parser import extract_json_from_response


_PROMPT = """
Tu es un correcteur professionnel FR (audit), chargé UNIQUEMENT de corriger la langue.

Objectif:
- Corriger les accents, la grammaire, les accords (genre/nombre), les apostrophes/contractions (de -> d', le -> l', etc.)
- Améliorer légèrement la fluidité pour un ton audit, SANS changer le sens.

Contraintes strictes (non négociables):
1) Ne change jamais les faits: nombres, dates, pourcentages, montants, noms propres, acronymes (ITGC, IAM, SAP), références (APD-01, PC-02), et applications.
2) Ne change pas la structure: garde les retours à la ligne, les puces, et le style global.
3) Ne reformule pas: pas de nouvelles idées, pas de suppression de contenu, pas d'ajout.
4) Phrases verrouillées (doivent rester exactement ainsi):
   - "mis en évidence"
   - "niveau de maturité"
   - "contrôle interne"
   - "contrôles généraux informatiques"
   - "risque d'accès"

Entrée: une liste d'objets {{"path": "...", "text": "..."}}.
Sortie: JSON valide uniquement, même structure, avec le champ "text" corrigé.

INPUT:
{items_json}
""".strip()


def polish_french_texts(items: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    payload = list(items)
    if not payload:
        return []

    llm = get_chat_llm()
    prompt = _PROMPT.format(items_json=json.dumps(payload, ensure_ascii=False, indent=2))
    response = llm.invoke(prompt)
    parsed = extract_json_from_response(response.content)
    if not isinstance(parsed, list):
        raise ValueError("French polisher did not return a JSON list.")
    return [{"path": str(row.get("path", "")), "text": str(row.get("text", ""))} for row in parsed]

