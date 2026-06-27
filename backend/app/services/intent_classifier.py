import re

from app.services.llm_clients import get_chat_llm
from app.utils.chat_utils import extract_current_question

VALID_INTENTS = {"qa", "report"}

_REPORT_REQUEST_RE = re.compile(
    r"\b(?:g[eé]n[eè]re(?:r)?|cr[eé]e(?:r)?|r[eé]dige(?:r)?|pr[eé]pare(?:r)?|produi(?:re|s)|generate|create|draft|write)\b"
    r".{0,45}\b(?:rapport|report)\b|\b(?:rapport|report)\b.{0,45}"
    r"\b(?:complet|final|d['’]audit|audit|generate|create|draft)\b",
    re.IGNORECASE,
)

_QA_REQUEST_RE = re.compile(
    r"^\s*(?:combien|quel(?:le)?s?|qui|pourquoi|comment|liste|compare|identifie|propose|pr[eé]pare|"
    r"r[eé]sume|explique|donne|what|which|who|why|how|list|compare|identify|suggest|propose|prepare|summarize)\b",
    re.IGNORECASE,
)


def classify_intent(user_input: str) -> str:
    value = extract_current_question(user_input)
    if not value:
        return "qa"

    # Most chatbot turns are questions or analytical requests. Only an explicit
    # request to produce an audit report should enter the report-generation path.
    if _REPORT_REQUEST_RE.search(value):
        return "report"
    if "?" in value or _QA_REQUEST_RE.search(value):
        return "qa"

    prompt = f"""
You are an AI system that classifies a user's request for an Audit Assistant.

Choose ONLY one intent:

qa -> when the user asks a question

report -> ONLY when the user explicitly asks to generate, create, draft, or write an audit report

Questions about observations, comparisons, recommendations, action plans, summaries,
and analyses are always qa, even when they mention audit findings.

User request:
{user_input}

Return ONLY:
qa
report
"""
    llm = get_chat_llm()
    response = llm.invoke(prompt)
    intent = response.content.strip().lower()
    return intent if intent in VALID_INTENTS else "qa"
