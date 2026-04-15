from __future__ import annotations

from app.agents.retrieval_evaluator_agent import evaluate_retrieval
from app.services.retrieval_strategy_service import execute_retrieval_plan, retrieve_by_step


def run_agentic_retrieval(user_input: str, plan: dict, mission_id: str | None = None):
    retrieval_steps = plan.get("retrieval_steps") or ["general"]
    all_results = execute_retrieval_plan(user_input, retrieval_steps, mission_id=mission_id)
    evaluations = {}

    for step, docs in list(all_results.items()):
        evaluation = evaluate_retrieval(user_input, step, docs)
        evaluations[step] = evaluation

        retry_step = evaluation.get("retry_step")
        if not evaluation.get("sufficient", True) and retry_step and retry_step not in all_results:
            retry_docs = retrieve_by_step(user_input, retry_step, mission_id=mission_id)
            all_results[retry_step] = retry_docs
            evaluations[retry_step] = evaluate_retrieval(user_input, retry_step, retry_docs)

    return {"results": all_results, "evaluations": evaluations}
