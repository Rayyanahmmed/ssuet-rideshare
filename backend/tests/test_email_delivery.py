"""SMTP delivery for verification and reset emails.

The real SMTP server is replaced by a mock, so these tests never send mail.
They check the protocol steps (STARTTLS, login, headers, link) and that a mail
outage never breaks the request that triggered the email.
"""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.services import email_service

TOKEN = "t" * 40


def _smtp_mock() -> MagicMock:
    """`with smtplib.SMTP(...) as server` yields __enter__'s return value, so wire it to the same mock."""
    server = MagicMock()
    server.__enter__.return_value = server
    server.__exit__.return_value = False
    return server


@pytest.fixture
def smtp_settings(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp-relay.example.test")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", "login-id@example.test")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "fake-smtp-key")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", True)
    monkeypatch.setattr(settings, "EMAIL_FROM", "SSUET RideShare <noreply@example.test>")


def test_smtp_send_uses_starttls_login_and_proper_headers(smtp_settings):
    server = _smtp_mock()
    with patch("app.services.email_service.smtplib.SMTP", return_value=server) as smtp_cls:
        sent = email_service.send_verification_email("student@ssuet.edu.pk", "Ali Raza", TOKEN)

    assert sent is True
    smtp_cls.assert_called_once_with("smtp-relay.example.test", 587, timeout=15)
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("login-id@example.test", "fake-smtp-key")

    message = server.send_message.call_args.args[0]
    assert message["To"] == "student@ssuet.edu.pk"
    assert message["From"] == "SSUET RideShare <noreply@example.test>"
    assert message["Subject"] == "Confirm your SSUET RideShare email"
    assert f"ssuetrideshare://verify-email?token={TOKEN}" in message.get_content()


def test_reset_email_contains_reset_link_and_expiry(smtp_settings):
    server = _smtp_mock()
    with patch("app.services.email_service.smtplib.SMTP", return_value=server):
        assert email_service.send_password_reset_email("student@ssuet.edu.pk", "Ali Raza", TOKEN) is True

    message = server.send_message.call_args.args[0]
    body = message.get_content()
    assert f"ssuetrideshare://reset-password?token={TOKEN}" in body
    assert f"expires in {settings.PASSWORD_RESET_TOKEN_MINUTES} minutes" in body


def test_smtp_without_user_skips_login(smtp_settings, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_USER", "")
    server = _smtp_mock()
    with patch("app.services.email_service.smtplib.SMTP", return_value=server):
        assert email_service.send_email("a@ssuet.edu.pk", "Hi", "Body") is True
    server.login.assert_not_called()


def test_mail_outage_returns_false_and_never_raises(smtp_settings):
    with patch(
        "app.services.email_service.smtplib.SMTP",
        side_effect=smtplib.SMTPAuthenticationError(535, b"bad credentials"),
    ):
        assert email_service.send_verification_email("a@ssuet.edu.pk", "Ali", TOKEN) is False


def test_network_error_returns_false_and_never_raises(smtp_settings):
    with patch("app.services.email_service.smtplib.SMTP", side_effect=OSError("unreachable")):
        assert email_service.send_password_reset_email("a@ssuet.edu.pk", "Ali", TOKEN) is False


def test_unconfigured_smtp_logs_instead_of_sending(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    with patch("app.services.email_service.smtplib.SMTP") as smtp_cls:
        assert email_service.send_email("a@ssuet.edu.pk", "Hi", "Body") is False
    smtp_cls.assert_not_called()
