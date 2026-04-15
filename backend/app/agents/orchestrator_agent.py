from __future__ import annotations

import logging

from app.agents.planner_agent import build_plan
from app.agents.qa_agent import answer_mission_question, answer_question
from app.agents.report_agent import generate_audit_report
from app.services.agentic_retrieval_service import run_agentic_retrieval
from app.services.intent_classifier import classify_intent
from app.services.mission_service import get_mission, load_mission_audit_input, load_mission_report_cache

logger = logging.getLogger(__name__)


def flatten_results(results: dict) -> list[dict]:
    merged = []
    seen = set()

    for docs in results.values():
        for document in docs:
            key = (
                document.get("document_name"),
                document.get("chunk_id"),
                document.get("content"),
            )
            if key not in seen:
                seen.add(key)
                merged.append(document)

    return merged


def route_request(user_input: str, mission_id: str | None = None):
    if mission_id and get_mission(mission_id) is None:
        raise ValueError(f"Mission '{mission_id}' was not found.")

    audit_input = load_mission_audit_input(mission_id) if mission_id else None
    report_result = load_mission_report_cache(mission_id) if mission_id else None
    mission_result = answer_mission_question(user_input, audit_input)
    if mission_result is not None:
        mission_result.update(
            {
                "plan": {
                    "needs_multi_hop": False,
                    "retrieval_steps": ["mission_audit_input"],
                    "comparison_required": False,
                    "final_task": "qa",
                },
                "retrieval_evaluations": {
                    "mission_audit_input": {
                        "relevant": True,
                        "sufficient": True,
                        "reason": "Answered directly from the selected mission audit input.",
                        "retry_step": None,
                    }
                },
            }
        )
        logger.info(
            "Request routed via mission audit input",
            extra={
                "intent": "qa",
                "mission_id": mission_id,
                "retrieval_steps": ["mission_audit_input"],
            },
        )
        return mission_result

    intent = classify_intent(user_input)
    if intent != "report" and audit_input is not None:
        result = answer_question(
            user_input,
            docs=None,
            audit_input=audit_input,
            report_result=report_result,
        )
        result.update(
            {
                "plan": {
                    "needs_multi_hop": False,
                    "retrieval_steps": ["mission_audit_input", "mission_report_cache"],
                    "comparison_required": False,
                    "final_task": "qa",
                },
                "retrieval_evaluations": {
                    "mission_audit_input": {
                        "relevant": True,
                        "sufficient": True,
                        "reason": "Answered from the selected mission context and cached report.",
                        "retry_step": None,
                    }
                },
            }
        )
        logger.info(
            "Request routed via mission context",
            extra={
                "intent": intent,
                "mission_id": mission_id,
                "retrieval_steps": ["mission_audit_input", "mission_report_cache"],
            },
        )
        return result

    plan = build_plan(user_input, intent)
    retrieval_output = run_agentic_retrieval(user_input, plan, mission_id=mission_id)
    merged_docs = flatten_results(retrieval_output["results"])

    if intent == "report":
        result = generate_audit_report(user_input, docs=merged_docs, audit_input=audit_input)
    else:
        result = answer_question(
            user_input,
            docs=merged_docs,
            audit_input=audit_input,
            report_result=report_result,
            mission_scoped=bool(mission_id),
        )

    result.update(
        {
            "plan": plan,
            "retrieval_evaluations": retrieval_output["evaluations"],
        }
    )
    logger.info(
        "Request routed",
        extra={
            "intent": intent,
            "retrieval_steps": plan.get("retrieval_steps", []),
            "evaluations": retrieval_output["evaluations"],
        },
    )
    return result
