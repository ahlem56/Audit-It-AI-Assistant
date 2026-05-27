from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config.settings import (
    AUTH_FRONTEND_BASE_URL,
    REPORT_EMAIL_DEFAULT_TO,
    REPORT_EMAIL_ENABLED,
    REPORT_EMAIL_SENDER,
    REPORT_EMAIL_SENDER_NAME,
    REPORT_EMAIL_SMTP_HOST,
    REPORT_EMAIL_SMTP_PASSWORD,
    REPORT_EMAIL_SMTP_PORT,
    REPORT_EMAIL_SMTP_USERNAME,
    REPORT_EMAIL_USE_TLS,
)

logger = logging.getLogger(__name__)


def build_default_report_email_subject(*, mission_name: str, client_name: str, fiscal_year: str) -> str:
    mission_label = mission_name.strip() or "Rapport d'audit ITGC"
    client_label = client_name.strip() or "client"
    year_label = fiscal_year.strip() or "FY"
    return f"Transmission du rapport d'audit ITGC - {client_label} - {year_label} - {mission_label}"


def build_default_report_email_body(*, client_name: str, mission_name: str, fiscal_year: str) -> str:
    client_label = client_name.strip() or "Client"
    mission_label = mission_name.strip() or "la mission d'audit ITGC"
    year_label = fiscal_year.strip() or "la periode concernee"

    return (
        f"Bonjour,\n\n"
        f"Veuillez trouver ci-joint le rapport d'audit ITGC relatif a {mission_label}, "
        f"concernant {client_label} au titre de {year_label}.\n\n"
        f"Ce document est transmis pour revue et suivi des actions a engager, le cas echeant.\n\n"
        f"N'hesitez pas a me faire part de vos commentaires ou demandes d'ajustement.\n\n"
        f"Cordialement,\n"
        f"{REPORT_EMAIL_SENDER_NAME}"
    )


def default_report_recipient() -> str:
    return REPORT_EMAIL_DEFAULT_TO


def _ensure_email_enabled() -> None:
    if not REPORT_EMAIL_ENABLED:
        raise RuntimeError(
            "Email sending is disabled. Set REPORT_EMAIL_ENABLED=true and configure SMTP credentials in the backend environment."
        )

    if not REPORT_EMAIL_SMTP_USERNAME or not REPORT_EMAIL_SMTP_PASSWORD:
        raise RuntimeError("SMTP credentials are missing. Configure REPORT_EMAIL_SMTP_USERNAME and REPORT_EMAIL_SMTP_PASSWORD.")


def _send_plain_email(*, to_email: str, subject: str, body: str) -> None:
    _ensure_email_enabled()

    message = EmailMessage()
    message["Subject"] = subject.strip()
    message["From"] = f"{REPORT_EMAIL_SENDER_NAME} <{REPORT_EMAIL_SENDER}>"
    message["To"] = to_email.strip()
    message.set_content(body.strip())

    logger.info("Sending email to %s", to_email)
    with smtplib.SMTP(REPORT_EMAIL_SMTP_HOST, REPORT_EMAIL_SMTP_PORT, timeout=30) as server:
        if REPORT_EMAIL_USE_TLS:
            server.starttls()
        server.login(REPORT_EMAIL_SMTP_USERNAME, REPORT_EMAIL_SMTP_PASSWORD)
        server.send_message(message)


def send_report_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    attachment_bytes: bytes,
    attachment_filename: str,
) -> None:
    _ensure_email_enabled()

    message = EmailMessage()
    message["Subject"] = subject.strip()
    message["From"] = f"{REPORT_EMAIL_SENDER_NAME} <{REPORT_EMAIL_SENDER}>"
    message["To"] = to_email.strip()
    message.set_content(body.strip())
    message.add_attachment(
        attachment_bytes,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=attachment_filename,
    )

    logger.info("Sending report email to %s", to_email)
    with smtplib.SMTP(REPORT_EMAIL_SMTP_HOST, REPORT_EMAIL_SMTP_PORT, timeout=30) as server:
        if REPORT_EMAIL_USE_TLS:
            server.starttls()
        server.login(REPORT_EMAIL_SMTP_USERNAME, REPORT_EMAIL_SMTP_PASSWORD)
        server.send_message(message)


def send_mission_invitation_email(
    *,
    to_email: str,
    mission_name: str,
    client_name: str,
    fiscal_year: str,
    invited_by: str,
) -> None:
    mission_label = mission_name.strip() or "an Audit IT mission"
    client_label = client_name.strip() or "the client"
    year_label = fiscal_year.strip() or "the current audit period"
    inviter_label = invited_by.strip() or REPORT_EMAIL_SENDER_NAME
    login_url = f"{AUTH_FRONTEND_BASE_URL}/login?next=/"

    subject = f"Invitation to Audit IT mission - {mission_label}"
    body = (
        f"Hello,\n\n"
        f"{inviter_label} invited you to collaborate on the following Audit IT mission:\n\n"
        f"Mission: {mission_label}\n"
        f"Client: {client_label}\n"
        f"Period: {year_label}\n\n"
        f"You can access the mission by signing in here:\n"
        f"{login_url}\n\n"
        f"Please use this email address to sign in: {to_email.strip()}\n\n"
        f"Best regards,\n"
        f"{REPORT_EMAIL_SENDER_NAME}"
    )
    _send_plain_email(to_email=to_email, subject=subject, body=body)
