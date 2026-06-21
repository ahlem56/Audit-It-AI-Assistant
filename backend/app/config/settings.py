import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "Audit IT Assistant API")
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CORS_ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://localhost:4173,"
        "http://127.0.0.1:3000,http://127.0.0.1:5173,http://127.0.0.1:4173",
    ).split(",")
    if origin.strip()
]

AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
AZURE_STORAGE_CONTAINER_RAW = os.getenv("AZURE_STORAGE_CONTAINER_RAW")
AZURE_STORAGE_CONTAINER_PROCESSED = os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED")
AZURE_STORAGE_CONTAINER_PROFILE_IMAGES = os.getenv(
    "AZURE_STORAGE_CONTAINER_PROFILE_IMAGES",
    "profile-images",
)

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
GPT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

REPORT_EMAIL_ENABLED = os.getenv("REPORT_EMAIL_ENABLED", "false").lower() == "true"
REPORT_EMAIL_SMTP_HOST = os.getenv("REPORT_EMAIL_SMTP_HOST", "smtp.gmail.com")
REPORT_EMAIL_SMTP_PORT = int(os.getenv("REPORT_EMAIL_SMTP_PORT", "587"))
REPORT_EMAIL_SMTP_USERNAME = os.getenv("REPORT_EMAIL_SMTP_USERNAME", "")
REPORT_EMAIL_SMTP_PASSWORD = os.getenv("REPORT_EMAIL_SMTP_PASSWORD", "")
REPORT_EMAIL_USE_TLS = os.getenv("REPORT_EMAIL_USE_TLS", "true").lower() == "true"
REPORT_EMAIL_SENDER = os.getenv("REPORT_EMAIL_SENDER", REPORT_EMAIL_SMTP_USERNAME or "bouchahouaahlem@gmail.com")
REPORT_EMAIL_SENDER_NAME = os.getenv("REPORT_EMAIL_SENDER_NAME", "Ahlem Bouchahoua")
REPORT_EMAIL_DEFAULT_TO = os.getenv("REPORT_EMAIL_DEFAULT_TO", "ahlem.bouchahoua@esprit.tn")
WINDOWS_EXPORT_SERVICE_URL = os.getenv("WINDOWS_EXPORT_SERVICE_URL", "").strip().rstrip("/")
WINDOWS_EXPORT_SERVICE_TIMEOUT_SECONDS = int(os.getenv("WINDOWS_EXPORT_SERVICE_TIMEOUT_SECONDS", "900"))

AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
AUTH_FRONTEND_BASE_URL = os.getenv("AUTH_FRONTEND_BASE_URL", "http://localhost:4173").rstrip("/")
AUTH_SESSION_COOKIE_NAME = os.getenv("AUTH_SESSION_COOKIE_NAME", "audit_it_session")
AUTH_SESSION_TTL_HOURS = int(os.getenv("AUTH_SESSION_TTL_HOURS", "12"))
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
AUTH_SQLITE_PATH = Path(os.getenv("AUTH_SQLITE_PATH", str(DATA_DIR / "auth.sqlite3")))
AUTH_PROFILE_IMAGES_DIR = Path(os.getenv("AUTH_PROFILE_IMAGES_DIR", str(DATA_DIR / "profile_images")))
AUTH_ENTRA_CLIENT_ID = os.getenv("AUTH_ENTRA_CLIENT_ID", "")
AUTH_ENTRA_CLIENT_SECRET = os.getenv("AUTH_ENTRA_CLIENT_SECRET", "")
AUTH_ENTRA_REDIRECT_URI = os.getenv("AUTH_ENTRA_REDIRECT_URI", "http://127.0.0.1:8000/auth/entra/callback")
AUTH_ENTRA_POST_LOGOUT_REDIRECT_URI = os.getenv(
    "AUTH_ENTRA_POST_LOGOUT_REDIRECT_URI",
    f"{AUTH_FRONTEND_BASE_URL}/login",
)
AUTH_ENTRA_METADATA_URL = os.getenv("AUTH_ENTRA_METADATA_URL", "")
AUTH_DEMO_USER_EMAIL = os.getenv("AUTH_DEMO_USER_EMAIL", "demo.auditor@audit-it.local")
AUTH_DEMO_USER_NAME = os.getenv("AUTH_DEMO_USER_NAME", "Demo Auditor")
AUTH_DEMO_USER_ORGANIZATION = os.getenv("AUTH_DEMO_USER_ORGANIZATION", "Audit IT Local Workspace")
AUTH_DEMO_USER_ROLE = os.getenv("AUTH_DEMO_USER_ROLE", "manager").strip().lower()
AUTH_MANAGER_EMAILS = {
    email.strip().lower()
    for email in os.getenv("AUTH_MANAGER_EMAILS", "").split(",")
    if email.strip()
}

GRAPH_TENANT_ID = os.getenv("GRAPH_TENANT_ID", "").strip()
GRAPH_CLIENT_ID = os.getenv("GRAPH_CLIENT_ID", "").strip()
GRAPH_CLIENT_SECRET = os.getenv("GRAPH_CLIENT_SECRET", "").strip()
GRAPH_BASE_URL = os.getenv("GRAPH_BASE_URL", "https://graph.microsoft.com/v1.0").rstrip("/")
GRAPH_DELEGATED_SCOPES = os.getenv(
    "GRAPH_DELEGATED_SCOPES",
    "User.Read Files.Read",
).strip()

AZURE_SQL_SERVER = os.getenv("AZURE_SQL_SERVER", "").strip()
AZURE_SQL_DATABASE = os.getenv("AZURE_SQL_DATABASE", "").strip()
AZURE_SQL_USERNAME = os.getenv("AZURE_SQL_USERNAME", "").strip()
AZURE_SQL_PASSWORD = os.getenv("AZURE_SQL_PASSWORD", "").strip()
AZURE_SQL_DRIVER = os.getenv("AZURE_SQL_DRIVER", "ODBC Driver 18 for SQL Server").strip()
AZURE_SQL_ENCRYPT = os.getenv("AZURE_SQL_ENCRYPT", "yes").strip()
AZURE_SQL_TRUST_SERVER_CERTIFICATE = os.getenv("AZURE_SQL_TRUST_SERVER_CERTIFICATE", "no").strip()
AZURE_SQL_CONNECTION_TIMEOUT = int(os.getenv("AZURE_SQL_CONNECTION_TIMEOUT", "30"))
_AZURE_SQL_ENABLED_RAW = os.getenv("AZURE_SQL_ENABLED", "").strip().lower()
AZURE_SQL_ENABLED = (
    _AZURE_SQL_ENABLED_RAW not in {"0", "false", "no", "off"}
    and all(
        [
            AZURE_SQL_SERVER,
            AZURE_SQL_DATABASE,
            AZURE_SQL_USERNAME,
            AZURE_SQL_PASSWORD,
        ]
    )
)
