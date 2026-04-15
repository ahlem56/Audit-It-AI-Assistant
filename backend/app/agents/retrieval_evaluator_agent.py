from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent_outputs import RetrievalStepEvaluation
from app.services.llm_clients import get_chat_llm
from app.utils.json_parser import extract_json_from_response

llm = get_chat_llm()


class RetrievalEvaluatorAgent(BaseAgent):
    def run(self, input_data: dict) -> RetrievalStepEvaluation:
        user_input = input_data["user_input"]
        step = input_data["step"]
        docs = input_data["docs"]
        context = "\n\n".join(
            f"- {document.get('document_name')} | chunk={document.get('chunk_id')} | {document.get('content', '')[:500]}"
            for document in docs
        )

        prompt = f"""
You are a retrieval evaluation agent for an Audit AI assistant.

User request:
{user_input}

Retrieval step:
{step}

Retrieved context:
{context}

Return VALID JSON only:
{{
  "relevant": true,
  "sufficient": true,
  "reason": "...",
  "retry_step": null
}}

Rules:
- relevant = true only if the retrieved documents actually match the retrieval step.
- sufficient = true only if the retrieved information is enough for this step.
- If insufficient, suggest retry_step such as "logs", "procedures", or "general".
"""
        response = llm.invoke(prompt)

        try:
            parsed = extract_json_from_response(response.content)
            return RetrievalStepEvaluation.model_validate(parsed)
        except Exception:
            return RetrievalStepEvaluation(
                relevant=True,
                sufficient=True,
                reason="Fallback evaluation due to JSON parsing failure.",
                retry_step=None,
            )


def evaluate_retrieval(user_input: str, step: str, docs: list[dict]) -> dict:
    return RetrievalEvaluatorAgent().run(
        {"user_input": user_input, "step": step, "docs": docs}
    ).model_dump()
