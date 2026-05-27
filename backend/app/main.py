import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, feedbacks, m365, missions, notifications, observations, security, upload
from app.config.settings import APP_NAME
from app.services.auth_service import init_auth_storage, require_authenticated_user
from app.services.search_service import ensure_search_index_schema
from app.services.sql_storage_service import init_azure_sql_storage

logging.basicConfig(level=logging.INFO)

app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:4173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup() -> None:
    init_azure_sql_storage()
    init_auth_storage()
    ensure_search_index_schema()


app.include_router(auth.router, tags=["auth"])
secured = [Depends(require_authenticated_user)]

app.include_router(upload.router, tags=["upload"], dependencies=secured)
app.include_router(m365.router, tags=["m365"], dependencies=secured)
app.include_router(chat.router, tags=["chat"], dependencies=secured)
app.include_router(missions.router, tags=["missions"], dependencies=secured)
app.include_router(feedbacks.router, tags=["feedbacks"], dependencies=secured)
app.include_router(observations.router, tags=["observations"], dependencies=secured)
app.include_router(notifications.router, tags=["notifications"], dependencies=secured)
app.include_router(security.router, tags=["security"], dependencies=secured)


@app.get("/")
def root():
    return {"message": "Audit AI Assistant API running"}
