from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config.settings import (
    AZURE_SQL_CONNECTION_TIMEOUT,
    AZURE_SQL_DATABASE,
    AZURE_SQL_DRIVER,
    AZURE_SQL_ENABLED,
    AZURE_SQL_ENCRYPT,
    AZURE_SQL_PASSWORD,
    AZURE_SQL_SERVER,
    AZURE_SQL_TRUST_SERVER_CERTIFICATE,
    AZURE_SQL_USERNAME,
)

Base = declarative_base()


def _resolve_sql_driver() -> str:
    preferred_driver = AZURE_SQL_DRIVER
    try:
        import pyodbc

        available_drivers = set(pyodbc.drivers())
    except Exception:
        return preferred_driver

    if preferred_driver in available_drivers:
        return preferred_driver

    for fallback_driver in (
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ):
        if fallback_driver in available_drivers:
            return fallback_driver

    return preferred_driver


def _build_database_url() -> str:
    return "mssql+pyodbc://"


def _build_odbc_connection_string() -> str:
    resolved_driver = _resolve_sql_driver()
    return (
        f"DRIVER={{{resolved_driver}}};"
        f"SERVER={AZURE_SQL_SERVER};"
        f"DATABASE={AZURE_SQL_DATABASE};"
        f"UID={AZURE_SQL_USERNAME};"
        f"PWD={AZURE_SQL_PASSWORD};"
        f"Encrypt={AZURE_SQL_ENCRYPT};"
        f"TrustServerCertificate={AZURE_SQL_TRUST_SERVER_CERTIFICATE};"
        f"Connection Timeout={AZURE_SQL_CONNECTION_TIMEOUT};"
    )


def _connect_pyodbc():
    import pyodbc

    return pyodbc.connect(_build_odbc_connection_string())


ENGINE = (
    create_engine(
        _build_database_url(),
        creator=_connect_pyodbc,
        pool_pre_ping=True,
        future=True,
    )
    if AZURE_SQL_ENABLED
    else None
)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, future=True) if ENGINE else None


@contextmanager
def get_db_session():
    if SessionLocal is None:
        raise RuntimeError("Azure SQL is not configured.")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
