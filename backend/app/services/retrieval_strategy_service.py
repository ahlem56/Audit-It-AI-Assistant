from __future__ import annotations

from app.services.retrieval_service import retrieve_documents

STEP_QUERY_EXPANSIONS = {
    "policies": "policy standard requirement control",
    "procedures": "procedure process workflow",
    "logs": "log evidence monitoring alert event",
    "general": "",
}


def retrieve_by_step(user_input: str, step: str, top_k: int = 5, mission_id: str | None = None):
    suffix = STEP_QUERY_EXPANSIONS.get(step, "")
    query = f"{user_input} {suffix}".strip()
    return retrieve_documents(query, top_k=top_k, mission_id=mission_id)


def execute_retrieval_plan(user_input: str, retrieval_steps: list[str], mission_id: str | None = None):
    results = {}
    for step in retrieval_steps or ["general"]:
        results[step] = retrieve_by_step(user_input, step, mission_id=mission_id)
    return results
