import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import assistant, chat, feedbacks, missions, observations, upload
from app.config.settings import APP_NAME

logging.basicConfig(level=logging.INFO)

app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, tags=["upload"])
app.include_router(chat.router, tags=["chat"])
app.include_router(assistant.router, tags=["assistant"])
app.include_router(missions.router, tags=["missions"])
app.include_router(feedbacks.router, tags=["feedbacks"])
app.include_router(observations.router, tags=["observations"])


@app.get("/")
def root():
    return {"message": "Audit AI Assistant API running"}
