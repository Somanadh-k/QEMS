"""Incoming Gmail replies -> QEMS conversation (Feature 2's "two-way Gmail" requirement).

    Gmail -> fetch_unread_replies() -> parse QEMS-YYYY-NNNNN -> validate sender
           -> MessageService.create_message() -> mark_processed()

Runs from workers/scheduler.py:run_gmail_inbound_tick, never from a request handler --
polling Gmail is a background concern, not something a client request should block on.
A no-op (not an error) whenever GmailProvider isn't configured, so this never affects
apps that don't use Gmail OAuth.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActorType, Error, MessageType, User
from app.repositories.audit_log_repository import AuditLogRepository
from app.services.message_service import MessageService
from app.services.notification_providers import GmailProvider

logger = logging.getLogger("qems.gmail_inbound")

QEMS_ID_RE = re.compile(r"QEMS-\d{4}-\d{5}")


async def process_inbound(db: AsyncSession) -> dict:
    provider = GmailProvider()
    if not provider.is_configured():
        return {"skipped": True, "reason": "Gmail OAuth not configured"}

    summary = {"skipped": False, "fetched": 0, "attached": 0, "rejected_unknown_error": 0, "rejected_unknown_sender": 0}
    audit = AuditLogRepository(db)

    for raw in provider.fetch_unread_replies():
        summary["fetched"] += 1
        qems_code_match = QEMS_ID_RE.search(raw["subject"]) or QEMS_ID_RE.search(raw["body"])
        if not qems_code_match:
            provider.mark_processed(raw["gmail_id"])
            continue
        qems_code = qems_code_match.group(0)

        error = (
            await db.execute(select(Error).where(Error.qa_error_code == qems_code))
        ).scalar_one_or_none()
        if error is None:
            summary["rejected_unknown_error"] += 1
            await audit.create(
                action="GMAIL_REPLY_REJECTED", actor_type=ActorType.SYSTEM,
                reason=f"Unknown QEMS code {qems_code}",
            )
            provider.mark_processed(raw["gmail_id"])
            continue

        sender = (
            await db.execute(select(User).where(User.email == raw["from_email"]))
        ).scalar_one_or_none()
        # Only a party already on this error may extend its conversation by email --
        # otherwise anyone who knows the error code could inject messages into it.
        if sender is None or sender.user_id not in (error.raised_by, error.assigned_to):
            summary["rejected_unknown_sender"] += 1
            await audit.create(
                action="GMAIL_REPLY_REJECTED", actor_type=ActorType.SYSTEM, error_id=error.error_id,
                reason=f"Sender {raw['from_email']} is not a party to {qems_code}",
            )
            provider.mark_processed(raw["gmail_id"])
            continue

        await MessageService(db).create_message(
            error, sender, raw["body"], parent_message_id=None, message_type=MessageType.TEXT
        )
        await audit.create(
            actor_id=sender.user_id, action="GMAIL_REPLY_PROCESSED", actor_type=ActorType.SYSTEM,
            error_id=error.error_id, after_value={"gmail_id": raw["gmail_id"]},
        )
        provider.mark_processed(raw["gmail_id"])
        summary["attached"] += 1

    await db.commit()
    logger.info("gmail_inbound_tick %s", summary)
    return summary
