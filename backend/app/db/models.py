from __future__ import annotations

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.session import Base


class MissionRecord(Base):
    __tablename__ = "missions"

    mission_id = Column(String(120), primary_key=True)
    name = Column(String(255), nullable=False)
    client_name = Column(String(255), default="")
    fiscal_year = Column(String(50), default="")
    status = Column(String(50), default="Draft")
    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)
    uploaded_file_name = Column(String(255), nullable=True)
    parsing_status = Column(String(50), default="not_uploaded")
    observations_count = Column(Integer, default=0)
    applications_count = Column(Integer, default=0)
    control_ids_count = Column(Integer, default=0)
    report_generated_at = Column(String(50), nullable=True)
    exported_at = Column(String(50), nullable=True)
    owner_user_id = Column(String(120), default="")
    owner_email = Column(String(255), default="")
    invited_auditor_emails_json = Column(Text, default="[]")
    audit_input_json = Column(Text, nullable=True)
    audit_input_cache_key = Column(String(50), nullable=True)

    observations = relationship("ObservationRecord", back_populates="mission", cascade="all, delete-orphan")
    feedbacks = relationship("FeedbackRecord", back_populates="mission", cascade="all, delete-orphan")
    report_versions = relationship("ReportVersionRecord", back_populates="mission", cascade="all, delete-orphan")


class ObservationRecord(Base):
    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mission_id = Column(String(120), ForeignKey("missions.mission_id", ondelete="CASCADE"), index=True, nullable=False)
    observation_id = Column(String(120), nullable=False, index=True)
    domaine_controle = Column(String(120), default="")
    categorie_controle = Column(String(120), default="")
    controle_ref = Column(String(120), default="")
    application = Column(String(255), default="")
    couche = Column(String(120), default="")
    controle_attendu = Column(Text, default="")
    constat = Column(Text, default="")
    risque_associe = Column(Text, default="")
    procedure_compensatoire = Column(Text, default="")
    impact_potentiel = Column(Text, default="")
    cause_racine = Column(Text, default="")
    commentaire_auditeur = Column(Text, default="")
    population = Column(Text, default="")
    taille_echantillon = Column(Text, default="")
    nombre_exceptions = Column(Text, default="")
    responsables = Column(Text, default="")
    references_probantes = Column(Text, default="")
    statut_controle = Column(String(120), default="")
    priority = Column(String(50), nullable=True)
    priority_justification = Column(Text, default="")
    priority_reason = Column(Text, default="")
    priority_source = Column(String(120), default="")
    statut_validation = Column(String(50), default="")
    recommandation_proposee = Column(Text, default="")
    titre_observation = Column(String(500), default="")
    included_in_report = Column(Boolean, default=True)
    updated_at = Column(String(50), nullable=False)

    mission = relationship("MissionRecord", back_populates="observations")


class FeedbackRecord(Base):
    __tablename__ = "feedbacks"

    feedback_id = Column(String(120), primary_key=True)
    mission_id = Column(String(120), ForeignKey("missions.mission_id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(String(50), nullable=False)
    author = Column(String(255), nullable=True)
    scope = Column(String(50), nullable=True)
    target_id = Column(String(120), nullable=True)
    rating = Column(Integer, nullable=True)
    sentiment = Column(String(50), nullable=True)
    categories_json = Column(Text, default="[]")
    comment = Column(Text, nullable=True)
    requires_action = Column(Boolean, default=False)
    status = Column(String(50), default="pending")

    mission = relationship("MissionRecord", back_populates="feedbacks")


class ReportVersionRecord(Base):
    __tablename__ = "report_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mission_id = Column(String(120), ForeignKey("missions.mission_id", ondelete="CASCADE"), index=True, nullable=False)
    cached_at = Column(String(50), nullable=False)
    audit_input_mtime_ns = Column(String(50), nullable=False)
    readiness_score = Column(Integer, nullable=True)
    export_allowed = Column(Boolean, nullable=True)
    blocking_issues_count = Column(Integer, nullable=True)
    warning_issues_count = Column(Integer, nullable=True)
    structured_output_json = Column(Text, nullable=False)

    mission = relationship("MissionRecord", back_populates="report_versions")


class SecurityAuditEventRecord(Base):
    __tablename__ = "security_audit_events"

    event_id = Column(String(120), primary_key=True)
    timestamp = Column(String(50), nullable=False, index=True)
    user_id = Column(String(120), nullable=True, index=True)
    user_email = Column(String(255), nullable=True, index=True)
    organization_id = Column(String(255), nullable=True)
    mission_id = Column(String(120), nullable=True, index=True)
    action = Column(String(80), nullable=False, index=True)
    resource_type = Column(String(80), nullable=True)
    resource_id = Column(String(255), nullable=True)
    ip_address = Column(String(80), nullable=True)
    user_agent = Column(String(500), nullable=True)
    status = Column(String(50), nullable=False, default="success")
    metadata_json = Column(Text, nullable=False, default="{}")
    hash = Column(String(64), nullable=False)
    previous_hash = Column(String(64), nullable=False, default="")


class AppUserRecord(Base):
    __tablename__ = "app_users"

    user_id = Column(String(120), primary_key=True)
    email = Column(String(255), nullable=False)
    email_normalized = Column(String(255), nullable=False, unique=True, index=True)
    first_name = Column(String(255), nullable=False, default="")
    last_name = Column(String(255), nullable=False, default="")
    display_name = Column(String(255), nullable=False, default="")
    organization = Column(String(255), nullable=False, default="")
    job_title = Column(String(255), nullable=False, default="")
    role = Column(String(50), nullable=False, default="auditor")
    auth_provider = Column(String(120), nullable=False, default="entra_external_id")
    entra_subject = Column(String(255), nullable=False, unique=True, index=True)
    entra_oid = Column(String(255), nullable=True)
    entra_tid = Column(String(255), nullable=True)
    profile_image_path = Column(String(500), nullable=True)
    created_at = Column(String(50), nullable=False)
    updated_at = Column(String(50), nullable=False)
    last_login_at = Column(String(50), nullable=True)
    raw_claims = Column(Text, nullable=False, default="{}")


class NotificationRecord(Base):
    __tablename__ = "notifications"

    notification_id = Column(String(120), primary_key=True)
    recipient_user_id = Column(String(120), nullable=True, index=True)
    recipient_email = Column(String(255), nullable=False, index=True, default="")
    actor_user_id = Column(String(120), nullable=True)
    actor_email = Column(String(255), nullable=True)
    type = Column(String(80), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    mission_id = Column(String(120), nullable=True, index=True)
    related_entity_type = Column(String(80), nullable=True)
    related_entity_id = Column(String(120), nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(String(50), nullable=False)
    read_at = Column(String(50), nullable=True)


class AuthStateRecord(Base):
    __tablename__ = "auth_states"

    state_token = Column(String(255), primary_key=True)
    nonce = Column(String(255), nullable=False)
    next_path = Column(String(1000), nullable=False)
    created_at = Column(String(50), nullable=False)
    expires_at = Column(String(50), nullable=False)


class AuthSessionRecord(Base):
    __tablename__ = "auth_sessions"

    session_token = Column(String(255), primary_key=True)
    user_id = Column(String(120), ForeignKey("app_users.user_id", ondelete="CASCADE"), index=True, nullable=False)
    created_at = Column(String(50), nullable=False)
    expires_at = Column(String(50), nullable=False)
    last_seen_at = Column(String(50), nullable=False)
    user_agent = Column(String(500), nullable=False, default="")
    graph_access_token = Column(Text, nullable=True)
    graph_refresh_token = Column(Text, nullable=True)
    graph_token_expires_at = Column(String(50), nullable=True)
