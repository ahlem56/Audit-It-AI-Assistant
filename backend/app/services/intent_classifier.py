from langchain_openai import AzureChatOpenAI
from app.config.settings import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_API_VERSION,
    GPT_DEPLOYMENT
)

llm = AzureChatOpenAI(
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY,
    api_version=AZURE_OPENAI_API_VERSION,
    azure_deployment=GPT_DEPLOYMENT
)


def classify_intent(user_input: str):

    prompt = f"""
You are an AI system that classifies a user's request for an IT Audit Assistant.

Choose ONLY one intent from this list:

qa → when the user asks a question or requests an explanation about documents or policies.

rcm → when the user asks to generate a Risk Control Matrix.

observation → when the user asks for an audit observation, audit finding, or audit issue.

report → when the user asks for a complete audit report.

User request:
{user_input}

Return ONLY one word:
qa
rcm
observation
report
"""
    response = llm.invoke(prompt)

    intent = response.content.strip().lower()

    return intent