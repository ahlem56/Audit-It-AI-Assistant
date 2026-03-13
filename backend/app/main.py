from fastapi import FastAPI
from app.api import upload, chat, assistant
from app.config.settings import APP_NAME

app = FastAPI(title=APP_NAME)

app.include_router(upload.router, tags=["upload"])
app.include_router(chat.router, tags=["chat"])
app.include_router(assistant.router, tags=["assistant"])

@app.get("/")
def root():
    return {"message": "Audit AI Assistant API running"}