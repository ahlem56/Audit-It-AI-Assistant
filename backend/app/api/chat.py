from fastapi import APIRouter
from app.services.rag_pipeline import rag_answer

router = APIRouter()

@router.post("/chat")
async def chat(question: str):
    result = rag_answer(question)
    return result