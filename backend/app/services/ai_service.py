"""AI Component (Section 13).

The original report specified the Google Gemini API for every AI-assisted capability
listed below. Per project decision, this implementation uses OpenAI instead:
  - Gemini `generateContent`      -> OpenAI Chat Completions (`chat.completions.create`)
  - Gemini embeddings endpoint    -> OpenAI Embeddings (`embeddings.create`)
Nothing else about the feature set changes: root-cause analysis, similarity search,
severity prediction, report summarization, smart recommendations, and NL search all
still work exactly as specified, with a human reviewer always in the loop (13.7 —
AI output is always a suggestion, never an automatic action).
"""

import json
import logging
import time
from dataclasses import dataclass

from openai import AsyncOpenAI, OpenAIError

from app.core.config import get_settings
from app.core.exceptions import AIServiceError

logger = logging.getLogger("qems.ai")
settings = get_settings()

_ROOT_CAUSE_CACHE_TTL_SECONDS = 3600
_root_cause_cache: dict[int, tuple[float, dict]] = {}  # 13.7: cache AI responses per error


@dataclass
class AISuggestion:
    """Every AI response is wrapped in this so callers/UI always know it's a suggestion (13.7)."""

    label: str
    content: dict


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


class AIService:
    def __init__(self):
        self.client = _client()

    async def generate_embedding(self, text: str) -> list[float]:
        """13.2: embed error descriptions at creation time for later similarity search."""
        try:
            response = await self.client.embeddings.create(
                model=settings.openai_embedding_model,
                input=text,
            )
        except OpenAIError as exc:
            raise AIServiceError(f"OpenAI embeddings call failed: {exc}") from exc
        return response.data[0].embedding

    async def root_cause_analysis(
        self, *, error_id: int, title: str, description: str, category: str, similar_context: str
    ) -> AISuggestion:
        """13.1: candidate root-cause explanation shown to the QA Reviewer as a suggestion."""
        cached = _root_cause_cache.get(error_id)
        if cached and time.monotonic() - cached[0] < _ROOT_CAUSE_CACHE_TTL_SECONDS:
            return AISuggestion(label="AI Suggestion", content=cached[1])

        prompt = (
            "You are a quality-engineering assistant. Given a QA error, suggest the most "
            "likely root cause. Respond as JSON: {\"suggested_root_cause\": str, "
            "\"confidence\": \"Low\"|\"Medium\"|\"High\"}.\n\n"
            f"Title: {title}\nCategory: {category}\nDescription: {description}\n\n"
            f"Historically similar closed errors (may be empty):\n{similar_context}"
        )
        content = await self._chat_json(prompt)
        _root_cause_cache[error_id] = (time.monotonic(), content)
        return AISuggestion(label="AI Suggestion", content=content)

    async def predict_severity(self, *, title: str, description: str) -> AISuggestion:
        """13.3: suggest an initial severity; inspector may accept or override."""
        prompt = (
            "Classify the severity of this QA error as one of Low, Medium, High, Critical. "
            "Respond as JSON: {\"suggested_severity\": str, \"rationale\": str}.\n\n"
            f"Title: {title}\nDescription: {description}"
        )
        content = await self._chat_json(prompt)
        return AISuggestion(label="AI Suggestion", content=content)

    async def summarize_report(self, *, date_from: str, date_to: str, errors_summary: str) -> AISuggestion:
        """13.4: concise narrative appended to an exported report."""
        prompt = (
            f"Summarize QA errors from {date_from} to {date_to} into a concise narrative "
            "covering key trends, recurring categories, and notable overdue items. "
            "Respond as JSON: {\"summary\": str}.\n\n"
            f"Errors:\n{errors_summary}"
        )
        content = await self._chat_json(prompt)
        return AISuggestion(label="AI Suggestion", content=content)

    async def recommend_assignee_and_sla_risk(
        self, *, category: str, department: str, history_summary: str
    ) -> AISuggestion:
        """13.5: likely owner/assignee + estimated SLA risk at error-creation time."""
        prompt = (
            "Based on category/department history, recommend a likely owner/assignee and "
            "estimate SLA risk (Low, Medium, High). Respond as JSON: "
            "{\"recommended_owner_hint\": str, \"sla_risk\": str, \"reasoning\": str}.\n\n"
            f"Category: {category}\nDepartment: {department}\nHistory:\n{history_summary}"
        )
        content = await self._chat_json(prompt)
        return AISuggestion(label="AI Suggestion", content=content)

    async def nl_search_to_filters(self, *, query: str) -> AISuggestion:
        """13.6: translate a plain-language query into structured /api/v1/errors filter params."""
        prompt = (
            "Translate this natural-language request into QEMS error-list filter parameters. "
            'Respond as JSON with only known keys: {"status": str|null, "severity": str|null, '
            '"department_name": str|null, "category_name": str|null, "date_from": str|null, '
            '"date_to": str|null}.\n\n'
            f"Request: {query}"
        )
        content = await self._chat_json(prompt)
        return AISuggestion(label="AI Suggestion", content=content)

    async def _chat_json(self, prompt: str) -> dict:
        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_chat_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
        except OpenAIError as exc:
            raise AIServiceError(f"OpenAI chat completion call failed: {exc}") from exc
        raw = response.choices[0].message.content or "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("AI response was not valid JSON: %s", raw)
            return {"raw_response": raw}


def get_ai_service() -> "AIService":
    return AIService()
