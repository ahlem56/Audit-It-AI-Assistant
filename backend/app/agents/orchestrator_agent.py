from app.agents.qa_agent import answer_question
from app.agents.rcm_agent import generate_rcm
from app.agents.observation_agent import generate_observation
from app.agents.report_agent import generate_audit_report
from app.services.intent_classifier import classify_intent

def detect_intent(user_input: str) -> str:
    return classify_intent(user_input)

def route_request(user_input: str):
    intent = detect_intent(user_input)

    if intent == "rcm":
        return generate_rcm(user_input)

    if intent == "observation":
        return generate_observation(user_input)

    if intent == "report":
        return generate_audit_report(user_input)

    return answer_question(user_input)