"""AI-generated notification copy (Feature 2's "dynamic content" requirement).

Deliberately tiny and separate from AIGateway (ai_gateway.py): that gateway is
schema-constrained, versioned and cost-ledgered because its output can become an
AIInsight a reviewer acts on. A notification subject line carries no such weight -- if
this fails or is disabled, the caller (notification_service.dispatch_event) falls back
to the deterministic template unconditionally. That fallback is not a degraded mode to
be logged or monitored; it is the expected behaviour whenever no OpenAI key is configured.
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI, OpenAIError

from app.core.config import get_settings
from app.services.embedding_service import api_key_is_usable

logger = logging.getLogger("qems.ai_notification")
settings = get_settings()

_PROMPT = """\
You write one-line professional email subjects and short bodies for a QA error \
management system. You will be given an event type and computed fields (already \
correct; never alter them). Do not invent facts not present in the fields.

Respond as JSON: {"subject": str (max 120 chars), "body": str (max 600 chars, plain text)}
"""


async def narrate(event_type: str, context: dict) -> tuple[str, str] | None:
    """Returns (subject, body) or None -- callers must always have a deterministic
    template ready to use instead."""
    if not settings.ai_narration_enabled or not api_key_is_usable():
        return None

    safe_context = {k: v for k, v in context.items() if v is not None}
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=[
                {"role": "system", "content": _PROMPT},
                {"role": "user", "content": f"event_type: {event_type}\nfields: {json.dumps(safe_context, default=str)}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            timeout=8,
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        subject, body = parsed.get("subject"), parsed.get("body")
        if not isinstance(subject, str) or not isinstance(body, str) or not subject or not body:
            return None
        return subject[:200], body[:2000]
    except (OpenAIError, json.JSONDecodeError, ValueError, TimeoutError) as exc:
        logger.warning("AI notification narration failed, using template fallback: %s", exc)
        return None
