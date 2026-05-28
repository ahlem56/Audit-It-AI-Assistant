import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, feedbacks, m365, missions, notifications, observations, security, upload
from app.config.settings import APP_NAME, AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX, AZURE_SEARCH_KEY, CORS_ALLOWED_ORIGINS
from app.services.auth_service import init_auth_storage, require_authenticated_user
from app.services.search_service import ensure_search_index_schema
from app.services.sql_storage_service import init_azure_sql_storage

logging.basicConfig(level=logging.INFO)

app = FastAPI(title=APP_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup() -> None:
    init_azure_sql_storage()
    init_auth_storage()
    if AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY and AZURE_SEARCH_INDEX:
        ensure_search_index_schema()
    else:
        logging.info("Azure AI Search not configured. Skipping search index startup check.")


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
