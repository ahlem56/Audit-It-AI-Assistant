from __future__ import annotations

from app.agents.base import BaseAgent
from app.models.agent_outputs import RetrievalPlan
from app.services.llm_clients import get_chat_llm
from app.utils.json_parser import extract_json_from_response

llm = get_chat_llm()


class PlannerAgent(BaseAgent):
    def run(self, input_data: dict) -> RetrievalPlan:
        user_input = input_data["user_input"]
        intent = input_data["intent"]
        prompt = f"""
You are a planning agent for an Audit AI assistant.

Your role is to decide the retrieval strategy before the final answer is generated.

User request:
{user_input}

Detected intent:
{intent}

Return VALID JSON only with this schema:
{{
  "needs_multi_hop": true,
  "retrieval_steps": ["general"],
  "comparison_required": false,
  "final_task": "{intent}"
}}

Rules:
- Use "general" if one retrieval is enough.
- Use multiple steps like ["policies", "logs", "procedures"] if the request requires comparing different evidence types.
- comparison_required = true if the task needs comparison across sources.
- Return JSON only.
"""
        response = llm.invoke(prompt)
        parsed = extract_json_from_response(response.content)
        return RetrievalPlan.model_validate(parsed)


def build_plan(user_input: str, intent: str) -> dict:
    return PlannerAgent().run(
        {"user_input": user_input, "intent": intent}
    ).model_dump()
