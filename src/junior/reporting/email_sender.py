"""Optional SMTP delivery for a user-previewed Junior report."""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EmailSendResult:
    sent: bool
    message: str


def send_email_report(
    settings: dict[str, object],
    subject: str,
    body: str,
    html_body: str | None = None,
    attachment_path: str | Path | None = None,
) -> EmailSendResult:
    if not settings.get("enabled", False):
        return EmailSendResult(False, "Email sending is disabled in Settings.")
    password_env = str(settings.get("smtp_password_env") or "")
    password = os.environ.get(password_env)
    if not password:
        return EmailSendResult(
            False, f"Email password environment variable is not set: {password_env}"
        )
    try:
        message = _build_message(
            str(settings["sender"]),
            str(settings.get("sender_name") or ""),
            tuple(str(item) for item in settings["recipients"]),
            subject,
            body,
            html_body,
            attachment_path,
        )
        _send(settings, message, password)
    except (KeyError, OSError, smtplib.SMTPException, ValueError) as error:
        return EmailSendResult(False, f"Email send failed: {error}")
    return EmailSendResult(True, "Email sent.")


def _build_message(
    sender: str,
    sender_name: str,
    recipients: tuple[str, ...],
    subject: str,
    body: str,
    html_body: str | None,
    attachment_path: str | Path | None,
) -> EmailMessage:
    if not sender or not recipients:
        raise ValueError("A sender and at least one recipient are required.")
    message = EmailMessage()
    message["From"] = formataddr((sender_name, sender)) if sender_name else sender
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    if attachment_path:
        path = Path(attachment_path)
        subtype = "html" if path.suffix.casefold() in {".html", ".htm"} else "markdown"
        message.add_attachment(
            path.read_text(encoding="utf-8"), subtype=subtype, filename=path.name
        )
    return message


def _send(settings: dict[str, object], message: EmailMessage, password: str) -> None:
    host = str(settings["smtp_host"])
    port = int(settings["smtp_port"])
    mode = str(settings.get("smtp_tls_mode") or "starttls")
    if mode not in {"starttls", "ssl", "none"}:
        raise ValueError("SMTP TLS mode must be starttls, ssl, or none.")
    smtp_type = smtplib.SMTP_SSL if mode == "ssl" else smtplib.SMTP
    with smtp_type(host, port) as smtp:
        if mode == "starttls":
            smtp.starttls()
        smtp.login(str(settings["smtp_username"]), password)
        smtp.send_message(message)
