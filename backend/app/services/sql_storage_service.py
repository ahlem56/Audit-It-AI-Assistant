from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from sqlalchemy import delete, select, text

from app.config.settings import AZURE_SQL_ENABLED
from app.db.models import FeedbackRecord, MissionRecord, ObservationRecord, ReportVersionRecord
from app.db.session import Base, ENGINE, get_db_session
from app.models.audit_input import AuditObservation, MissionInfo, StructuredAuditInput
from app.models.report_sections import AuditReportOutput

logger = logging.getLogger(__name__)
_AZURE_SQL_READY = False
_AZURE_SQL_INITIALIZING = False
_LAST_AZURE_SQL_INIT_ATTEMPT = 0.0
_AZURE_SQL_RETRY_INTERVAL_SECONDS = 20
_AZURE_SQL_INIT_LOCK = Lock()


def _azure_sql_configured() -> bool:
    return AZURE_SQL_ENABLED and ENGINE is not None


def azure_sql_enabled() -> bool:
    if not _azure_sql_configured():
        return False
    if _AZURE_SQL_READY:
        return True
    if _AZURE_SQL_INITIALIZING:
        return False

    now = time.monotonic()
    if now - _LAST_AZURE_SQL_INIT_ATTEMPT >= _AZURE_SQL_RETRY_INTERVAL_SECONDS:
        logger.info("Azure SQL is configured but not ready. Retrying initialization.")
        init_azure_sql_storage()
    return _AZURE_SQL_READY


def init_azure_sql_storage() -> None:
    global _AZURE_SQL_INITIALIZING, _AZURE_SQL_READY, _LAST_AZURE_SQL_INIT_ATTEMPT
    if not _azure_sql_configured():
        logger.info("Azure SQL not configured. Using local mission storage.")
        _AZURE_SQL_READY = False
        return
    if _AZURE_SQL_INITIALIZING:
        return
    with _AZURE_SQL_INIT_LOCK:
        if _AZURE_SQL_INITIALIZING:
            return
        _AZURE_SQL_INITIALIZING = True
        _LAST_AZURE_SQL_INIT_ATTEMPT = time.monotonic()
    try:
        Base.metadata.create_all(bind=ENGINE)
        with ENGINE.connect() as connection:
            mission_columns = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'missions'"
                    )
                )
            }
            if "invited_auditor_emails_json" not in mission_columns:
                connection.execute(
                    text("ALTER TABLE missions ADD invited_auditor_emails_json NVARCHAR(MAX) NULL")
                )
                connection.commit()
            if "audit_input_json" not in mission_columns:
                connection.execute(text("ALTER TABLE missions ADD audit_input_json NVARCHAR(MAX) NULL"))
                connection.commit()
            if "audit_input_cache_key" not in mission_columns:
                connection.execute(text("ALTER TABLE missions ADD audit_input_cache_key NVARCHAR(50) NULL"))
                connection.commit()
            auth_session_columns = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                        "WHERE TABLE_NAME = 'auth_sessions'"
                    )
                )
            }
            auth_session_additions = {
                "graph_access_token": "NVARCHAR(MAX) NULL",
                "graph_refresh_token": "NVARCHAR(MAX) NULL",
                "graph_token_expires_at": "NVARCHAR(50) NULL",
            }
            for column_name, column_type in auth_session_additions.items():
                if column_name not in auth_session_columns:
                    connection.execute(text(f"ALTER TABLE auth_sessions ADD {column_name} {column_type}"))
                    connection.commit()
            connection.execute(text("SELECT 1"))
        _AZURE_SQL_READY = True
        logger.info("Azure SQL schema initialized successfully.")
    except Exception as exc:
        _AZURE_SQL_READY = False
        logger.exception("Azure SQL initialization failed: %s", exc)
    finally:
        _AZURE_SQL_INITIALIZING = False


def _mission_to_dict(record: MissionRecord) -> dict[str, Any]:
    try:
        invited_auditor_emails = json.loads(record.invited_auditor_emails_json or "[]")
    except json.JSONDecodeError:
        invited_auditor_emails = []

    return {
        "mission_id": record.mission_id,
        "name": record.name,
        "client_name": record.client_name or "",
        "fiscal_year": record.fiscal_year or "",
        "status": record.status or "Draft",
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "uploaded_file_name": record.uploaded_file_name,
        "parsing_status": record.parsing_status or "not_uploaded",
        "observations_count": record.observations_count or 0,
        "applications_count": record.applications_count or 0,
        "control_ids_count": record.control_ids_count or 0,
        "report_generated_at": record.report_generated_at,
        "exported_at": record.exported_at,
        "owner_user_id": record.owner_user_id or "",
        "owner_email": record.owner_email or "",
        "audit_input_cache_key": record.audit_input_cache_key or "",
        "invited_auditor_emails": [
            str(email).strip().lower()
            for email in invited_auditor_emails
            if str(email).strip()
        ],
    }


def _normalize_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def _mission_accessible(record: MissionRecord, *, user_id: str | None, user_email: str | None, user_role: str | None) -> bool:
    if user_id and (record.owner_user_id or "") == user_id:
        return True
    try:
        invited = json.loads(record.invited_auditor_emails_json or "[]")
    except json.JSONDecodeError:
        invited = []
    return _normalize_email(user_email) in {
        _normalize_email(str(email))
        for email in invited
        if str(email).strip()
    }


def list_missions(*, user_id: str | None = None, user_email: str | None = None, user_role: str | None = None) -> list[dict[str, Any]]:
    if not azure_sql_enabled():
        return []
    with get_db_session() as session:
        records = session.execute(select(MissionRecord).order_by(MissionRecord.updated_at.desc())).scalars().all()
        return [
            _mission_to_dict(record)
            for record in records
            if _mission_accessible(record, user_id=user_id, user_email=user_email, user_role=user_role)
        ]


def get_mission(
    mission_id: str,
    *,
    user_id: str | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
) -> dict[str, Any] | None:
    if not azure_sql_enabled():
        return None
    with get_db_session() as session:
        record = session.execute(select(MissionRecord).where(MissionRecord.mission_id == mission_id)).scalar_one_or_none()
        if record and not _mission_accessible(record, user_id=user_id, user_email=user_email, user_role=user_role):
            return None
        return _mission_to_dict(record) if record else None


def load_audit_input(
    mission_id: str,
    *,
    user_id: str | None = None,
    user_email: str | None = None,
    user_role: str | None = None,
) -> StructuredAuditInput | None:
    if not azure_sql_enabled():
        return None
    with get_db_session() as session:
        mission_record = session.execute(
            select(MissionRecord).where(MissionRecord.mission_id == mission_id)
        ).scalar_one_or_none()
        if mission_record is None:
            return None
        if not _mission_accessible(
            mission_record,
            user_id=user_id,
            user_email=user_email,
            user_role=user_role,
        ):
            return None

        if mission_record.audit_input_json:
            try:
                return StructuredAuditInput.model_validate(json.loads(mission_record.audit_input_json))
            except (json.JSONDecodeError, ValueError):
                logger.warning("Stored audit_input_json for mission %s is invalid; rebuilding from observations.", mission_id)

        observation_records = (
            session.execute(
                select(ObservationRecord)
                .where(ObservationRecord.mission_id == mission_id)
                .order_by(ObservationRecord.id.asc())
            )
            .scalars()
            .all()
        )
        if not observation_records:
            return None

        applications = sorted(
            {
                (record.application or "").strip()
                for record in observation_records
                if (record.application or "").strip()
            }
        )
        covered_processes = sorted(
            {
                (record.domaine_controle or "").strip()
                for record in observation_records
                if (record.domaine_controle or "").strip()
            }
        )

        return StructuredAuditInput(
            mission=MissionInfo(
                mission_id=mission_record.mission_id,
                titre_mission=mission_record.name or "",
                entite_auditee=mission_record.client_name or "",
                periode=mission_record.fiscal_year or "",
                processus_couverts=covered_processes,
                applications=applications,
            ),
            observations=[
                AuditObservation(
                    observation_id=record.observation_id or "",
                    domaine_controle=record.domaine_controle or "",
                    categorie_controle=record.categorie_controle or "",
                    controle_ref=record.controle_ref or "",
                    application=record.application or "",
                    couche=record.couche or "",
                    controle_attendu=record.controle_attendu or "",
                    constat=record.constat or "",
                    risque_associe=record.risque_associe or "",
                    procedure_compensatoire=record.procedure_compensatoire or "",
                    impact_potentiel=record.impact_potentiel or "",
                    cause_racine=record.cause_racine or "",
                    commentaire_auditeur=record.commentaire_auditeur or "",
                    population=record.population or "",
                    taille_echantillon=record.taille_echantillon or "",
                    nombre_exceptions=record.nombre_exceptions or "",
                    responsables=record.responsables or "",
                    references_probantes=record.references_probantes or "",
                    statut_controle=record.statut_controle or "",
                    priority=record.priority,
                    priority_justification=record.priority_justification or "",
                    priority_reason=record.priority_reason or "",
                    priority_source=record.priority_source or "",
                    statut_validation=record.statut_validation or "",
                    recommandation_proposee=record.recommandation_proposee or "",
                    titre_observation=record.titre_observation or "",
                    included_in_report=bool(record.included_in_report),
                )
                for record in observation_records
            ],
        )


def create_mission(payload: dict[str, Any]) -> dict[str, Any]:
    with get_db_session() as session:
        record_payload = dict(payload)
        if "invited_auditor_emails" in record_payload:
            record_payload["invited_auditor_emails_json"] = json.dumps(
                record_payload.pop("invited_auditor_emails") or [],
                ensure_ascii=False,
            )
        record = MissionRecord(**record_payload)
        session.add(record)
        session.flush()
        session.refresh(record)
        return _mission_to_dict(record)


def update_mission(mission_id: str, payload: dict[str, Any], *, user_id: str | None = None) -> dict[str, Any] | None:
    if not azure_sql_enabled():
        return None
    with get_db_session() as session:
        record = session.execute(select(MissionRecord).where(MissionRecord.mission_id == mission_id)).scalar_one_or_none()
        if record is None:
            return None
        for key, value in payload.items():
            if key == "invited_auditor_emails":
                record.invited_auditor_emails_json = json.dumps(value or [], ensure_ascii=False)
            elif hasattr(record, key):
                setattr(record, key, value)
        session.flush()
        session.refresh(record)
        return _mission_to_dict(record)


def delete_mission(mission_id: str, *, user_id: str | None = None) -> bool:
    if not azure_sql_enabled():
        return False
    with get_db_session() as session:
        record = session.execute(select(MissionRecord).where(MissionRecord.mission_id == mission_id)).scalar_one_or_none()
        if record is None:
            return False
        session.delete(record)
        return True


def sync_observations(mission_id: str, audit_input: StructuredAuditInput) -> None:
    if not azure_sql_enabled():
        return
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with get_db_session() as session:
        session.execute(delete(ObservationRecord).where(ObservationRecord.mission_id == mission_id))
        for observation in audit_input.observations or []:
            session.add(
                ObservationRecord(
                    mission_id=mission_id,
                    observation_id=observation.observation_id or "",
                    domaine_controle=observation.domaine_controle or "",
                    categorie_controle=observation.categorie_controle or "",
                    controle_ref=observation.controle_ref or "",
                    application=observation.application or "",
                    couche=observation.couche or "",
                    controle_attendu=observation.controle_attendu or "",
                    constat=observation.constat or "",
                    risque_associe=observation.risque_associe or "",
                    procedure_compensatoire=observation.procedure_compensatoire or "",
                    impact_potentiel=observation.impact_potentiel or "",
                    cause_racine=observation.cause_racine or "",
                    commentaire_auditeur=observation.commentaire_auditeur or "",
                    population=observation.population or "",
                    taille_echantillon=observation.taille_echantillon or "",
                    nombre_exceptions=observation.nombre_exceptions or "",
                    responsables=observation.responsables or "",
                    references_probantes=observation.references_probantes or "",
                    statut_controle=observation.statut_controle or "",
                    priority=observation.priority,
                    priority_justification=observation.priority_justification or "",
                    priority_reason=observation.priority_reason or "",
                    priority_source=observation.priority_source or "",
                    statut_validation=observation.statut_validation or "",
                    recommandation_proposee=observation.recommandation_proposee or "",
                    titre_observation=observation.titre_observation or "",
                    included_in_report=bool(observation.included_in_report),
                    updated_at=now,
                )
            )


def list_feedbacks(mission_id: str) -> list[dict[str, Any]]:
    if not azure_sql_enabled():
        return []
    with get_db_session() as session:
        records = session.execute(
            select(FeedbackRecord).where(FeedbackRecord.mission_id == mission_id).order_by(FeedbackRecord.created_at.desc())
        ).scalars().all()
        return [
            {
                "feedback_id": record.feedback_id,
                "mission_id": record.mission_id,
                "created_at": record.created_at,
                "author": record.author,
                "scope": record.scope,
                "target_id": record.target_id,
                "rating": record.rating,
                "sentiment": record.sentiment,
                "categories": json.loads(record.categories_json or "[]"),
                "comment": record.comment,
                "requires_action": bool(record.requires_action),
                "status": record.status,
            }
            for record in records
        ]


def create_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    with get_db_session() as session:
        record = FeedbackRecord(
            feedback_id=payload["feedback_id"],
            mission_id=payload["mission_id"],
            created_at=payload["created_at"],
            author=payload.get("author"),
            scope=payload.get("scope"),
            target_id=payload.get("target_id"),
            rating=payload.get("rating"),
            sentiment=payload.get("sentiment"),
            categories_json=json.dumps(payload.get("categories") or [], ensure_ascii=False),
            comment=payload.get("comment"),
            requires_action=bool(payload.get("requires_action")),
            status=payload.get("status") or "pending",
        )
        session.add(record)
        return payload


def update_feedback_status(mission_id: str, feedback_id: str, status: str) -> dict[str, Any] | None:
    if not azure_sql_enabled():
        return None
    with get_db_session() as session:
        record = session.execute(
            select(FeedbackRecord).where(
                FeedbackRecord.mission_id == mission_id,
                FeedbackRecord.feedback_id == feedback_id,
            )
        ).scalar_one_or_none()
        if record is None:
            return None
        record.status = status
        session.flush()
        return {
            "feedback_id": record.feedback_id,
            "mission_id": record.mission_id,
            "created_at": record.created_at,
            "author": record.author,
            "scope": record.scope,
            "target_id": record.target_id,
            "rating": record.rating,
            "sentiment": record.sentiment,
            "categories": json.loads(record.categories_json or "[]"),
            "comment": record.comment,
            "requires_action": bool(record.requires_action),
            "status": record.status,
        }


def delete_feedback(mission_id: str, feedback_id: str) -> bool:
    if not azure_sql_enabled():
        return False
    with get_db_session() as session:
        record = session.execute(
            select(FeedbackRecord).where(
                FeedbackRecord.mission_id == mission_id,
                FeedbackRecord.feedback_id == feedback_id,
            )
        ).scalar_one_or_none()
        if record is None:
            return False
        session.delete(record)
        return True


def save_report_version(
    mission_id: str,
    *,
    cached_at: str,
    audit_input_mtime_ns: str,
    structured_output: dict[str, Any],
    quality_gate: dict[str, Any] | None = None,
) -> None:
    if not azure_sql_enabled():
        return
    with get_db_session() as session:
        session.add(
            ReportVersionRecord(
                mission_id=mission_id,
                cached_at=cached_at,
                audit_input_mtime_ns=str(audit_input_mtime_ns),
                readiness_score=(quality_gate or {}).get("readiness_score"),
                export_allowed=(quality_gate or {}).get("export_allowed"),
                blocking_issues_count=(quality_gate or {}).get("blocking_issues_count"),
                warning_issues_count=(quality_gate or {}).get("warning_issues_count"),
                structured_output_json=json.dumps(structured_output, ensure_ascii=False),
            )
        )


def load_latest_report_version(mission_id: str) -> dict[str, Any] | None:
    if not azure_sql_enabled():
        return None
    with get_db_session() as session:
        record = (
            session.execute(
                select(ReportVersionRecord)
                .where(ReportVersionRecord.mission_id == mission_id)
                .order_by(ReportVersionRecord.cached_at.desc(), ReportVersionRecord.id.desc())
            )
            .scalars()
            .first()
        )
        if record is None:
            return None
        try:
            structured_output = json.loads(record.structured_output_json or "{}")
        except json.JSONDecodeError:
            return None
        return {
            "agent": "report_agent",
            "request": f"Generate report for mission {mission_id}",
            "audit_input_mtime_ns": record.audit_input_mtime_ns,
            "structured_output": structured_output,
        }
