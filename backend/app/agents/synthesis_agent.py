from __future__ import annotations

from app.agents.base import BaseAgent
from app.services.llm_clients import get_chat_llm

llm = get_chat_llm()


class SynthesisAgent(BaseAgent):
    def run(self, input_data: dict) -> str:
        user_input = input_data["user_input"]
        retrieval_results = input_data["retrieval_results"]
        parts = []

        for step, docs in retrieval_results.items():
            parts.append(f"=== STEP: {step} ===")
            for document in docs:
                parts.append(
                    f"document_name: {document.get('document_name')}\n"
                    f"chunk_id: {document.get('chunk_id')}\n"
                    f"content: {document.get('content')}\n"
                )

        merged_context = "\n\n".join(parts)
        prompt = f"""
You are a synthesis agent for an Audit AI system.

User request:
{user_input}

Retrieved evidence:
{merged_context}

Your task:
- group the retrieved information by evidence type
- identify alignments and inconsistencies
- distinguish requirement statements from execution evidence
- produce a concise synthesized context for a downstream audit agent

Return plain text only.
"""
        response = llm.invoke(prompt)
        return response.content


def synthesize_retrievals(user_input: str, retrieval_results: dict) -> str:
    return SynthesisAgent().run(
        {"user_input": user_input, "retrieval_results": retrieval_results}
    )
