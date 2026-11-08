"""Transactional email delivery (§4, §20).

Two backends:

* **SMTP** — used when `SMTP_HOST` is configured.
* **Console** — development fallback: the message is written to the log so the
  verification / reset link is still usable without any mail provider.

`send_email` never raises: a mail outage must not turn a successful signup into a
500. The failure is logged and the token stays valid until it expires.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("ssuet.rideshare.email")


def _send_via_smtp(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(message)


def send_email(to: str, subject: str, body: str) -> bool:
    if not settings.smtp_configured:
        logger.warning(
            "DEV EMAIL (no SMTP configured) → to=%s | subject=%s\n%s", to, subject, body
        )
        return False
    try:
        _send_via_smtp(to, subject, body)
        logger.info("Email sent to %s (%s)", to, subject)
        return True
    except (smtplib.SMTPException, OSError):
        logger.exception("Email delivery failed for %s — token kept valid", to)
        return False


def send_verification_email(to: str, full_name: str, raw_token: str) -> bool:
    link = f"{settings.APP_DEEP_LINK_BASE}verify-email?token={raw_token}"
    body = (
        f"Assalam-o-Alaikum {full_name},\n\n"
        "Welcome to SSUET RideShare. Please confirm your email address to finish "
        f"setting up your account:\n\n{link}\n\n"
        "If you did not create this account you can ignore this message.\n\n"
        "— SSUET RideShare"
    )
    return send_email(to, "Confirm your SSUET RideShare email", body)


def send_password_reset_email(to: str, full_name: str, raw_token: str) -> bool:
    link = f"{settings.APP_DEEP_LINK_BASE}reset-password?token={raw_token}"
    body = (
        f"Assalam-o-Alaikum {full_name},\n\n"
        "We received a request to reset your SSUET RideShare password. This link "
        f"expires in {settings.PASSWORD_RESET_TOKEN_MINUTES} minutes:\n\n{link}\n\n"
        "If you did not request this, no action is needed — your password is unchanged.\n\n"
        "— SSUET RideShare"
    )
    return send_email(to, "Reset your SSUET RideShare password", body)
