from app.services.llm_clients import get_chat_llm

llm = get_chat_llm()

VALID_INTENTS = {"qa", "report"}


def classify_intent(user_input: str) -> str:
    prompt = f"""
You are an AI system that classifies a user's request for an Audit Assistant.

Choose ONLY one intent:

qa -> when the user asks a question

report -> when the user:
- provides audit observations
- asks to generate an audit report
- asks to analyze audit findings

User request:
{user_input}

Return ONLY:
qa
report
"""
    response = llm.invoke(prompt)
    intent = response.content.strip().lower()
    return intent if intent in VALID_INTENTS else "qa"
