from fastapi import APIRouter
from app.agents.orchestrator_agent import route_request

router = APIRouter()

@router.post("/assistant")
async def assistant(user_input: str):
    result = route_request(user_input)
    return result