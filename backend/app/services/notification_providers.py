"""Notification delivery providers.

`NotificationProvider` is the seam the spec asks for: WhatsApp/Teams/Slack/SMS become
another class implementing `send()`, registered in `PROVIDERS` in notification_service.py
-- nothing in the event/template/logging machinery changes.

Two providers today, both "email" channel:
- `GmailProvider` -- real Gmail API send via OAuth2 (refresh-token grant), used when
  Google OAuth env vars are configured.
- `SmtpProvider` -- the app's original transactional-email path (Mailpit in dev, any
  real SMTP server in prod, including smtp.gmail.com with an app password). Used
  whenever Gmail OAuth isn't configured, so Gmail is never mandatory for delivery.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.exceptions import QEMSError

logger = logging.getLogger("qems.notification")
settings = get_settings()

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.modify"  # modify needed to mark inbound replies read


class NotificationSendError(QEMSError):
    status_code = 502
    code = "notification_send_failed"


class NotificationProvider(ABC):
    name: str

    @abstractmethod
    async def send(self, to_address: str, subject: str, body: str) -> str:
        """Send and return a provider-side message id. Raises NotificationSendError."""


def _send_smtp_sync(to_address: str, subject: str, body: str) -> str:
    message = EmailMessage()
    message["From"] = settings.smtp_from_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
    return message["Message-Id"] or ""


class SmtpProvider(NotificationProvider):
    name = "smtp"

    async def send(self, to_address: str, subject: str, body: str) -> str:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, _send_smtp_sync, to_address, subject, body)
        except OSError as exc:
            raise NotificationSendError(f"SMTP send failed: {exc}") from exc


def _gmail_credentials():
    """Lazy import: the google-* packages are an optional extra until Gmail OAuth is
    actually configured, so a fresh checkout that hasn't run `pip install -r
    requirements.txt` yet still boots and sends via SMTP."""
    from google.oauth2.credentials import Credentials

    return Credentials(
        token=None,
        refresh_token=settings.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=[GMAIL_SEND_SCOPE, GMAIL_READ_SCOPE],
    )


def _gmail_service():
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = _gmail_credentials()
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _gmail_send_sync(to_address: str, subject: str, body: str) -> str:
    message = EmailMessage()
    message["From"] = settings.gmail_sender
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service = _gmail_service()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return sent.get("id", "")


class GmailProvider(NotificationProvider):
    name = "gmail"

    @staticmethod
    def is_configured() -> bool:
        return bool(
            settings.google_client_id
            and settings.google_client_secret
            and settings.google_refresh_token
            and settings.gmail_sender
        )

    async def send(self, to_address: str, subject: str, body: str) -> str:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, _gmail_send_sync, to_address, subject, body)
        except ImportError as exc:
            raise NotificationSendError(
                "Gmail OAuth is configured but google-api-python-client / google-auth "
                "aren't installed -- run `pip install -r requirements.txt`."
            ) from exc
        except Exception as exc:  # noqa: BLE001 -- googleapiclient raises its own HttpError types
            raise NotificationSendError(f"Gmail API send failed: {exc}") from exc

    def fetch_unread_replies(self) -> list[dict]:
        """Poll for unread mail addressed to GMAIL_SENDER; used by gmail_inbound_service.

        Runs synchronously -- called from a worker's run_in_executor, never from a
        request handler. Returns already-parsed {gmail_id, from_email, subject, body}
        dicts and leaves the actual "mark read + label" step to the caller, which only
        does so once the reply has been safely attached to a QEMS conversation.
        """
        if not self.is_configured():
            return []
        try:
            service = _gmail_service()
            listing = service.users().messages().list(
                userId="me", q="is:unread", labelIds=["INBOX"], maxResults=25
            ).execute()
        except ImportError:
            logger.warning("Gmail inbound polling skipped: google client libraries not installed")
            return []
        except Exception:
            logger.exception("Gmail inbound polling failed")
            return []

        results = []
        for item in listing.get("messages", []):
            try:
                full = service.users().messages().get(
                    userId="me", id=item["id"], format="metadata",
                    metadataHeaders=["From", "Subject"],
                ).execute()
                headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
                snippet = full.get("snippet", "")
                results.append(
                    {
                        "gmail_id": item["id"],
                        "from_email": _extract_email(headers.get("From", "")),
                        "subject": headers.get("Subject", ""),
                        "body": snippet,
                    }
                )
            except Exception:
                logger.exception("Failed to fetch Gmail message %s", item.get("id"))
        return results

    def mark_processed(self, gmail_id: str) -> None:
        if not self.is_configured():
            return
        try:
            service = _gmail_service()
            service.users().messages().modify(
                userId="me", id=gmail_id, body={"removeLabelIds": ["UNREAD"]}
            ).execute()
        except Exception:
            logger.exception("Failed to mark Gmail message %s as read", gmail_id)


def _extract_email(from_header: str) -> str:
    """'Jane Doe <jane@corp.com>' -> 'jane@corp.com'; a bare address passes through."""
    if "<" in from_header and ">" in from_header:
        return from_header.split("<", 1)[1].split(">", 1)[0].strip().lower()
    return from_header.strip().lower()
