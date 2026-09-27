"""Quality Signal Engine (proposal QS-01).

The pipeline, and the layer that owns each step:

  1. embed             deterministic
  2. gate              deterministic  <- decides whether an AI call happens at all
  3. retrieve (kNN)    deterministic
  4. count             deterministic  <- SQL. the model never counts.
  5. score / band      deterministic  <- pure function in services/recurrence.py
  6. narrate           inferred       <- the ONLY step a model touches
  7. persist           deterministic  <- ai_insights, with full provenance

Because steps 1-5 are independent of step 6, an OpenAI outage costs the prose and none of
the arithmetic. That is the whole reason for the split.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ActorType,
    AIInsight,
    Error,
    InsightStatus,
    InsightType,
)
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.error_repository import ErrorRepository
from app.services.embedding_service import (
    OFFLINE_MODEL_NAME,
    generate_embedding,
    is_offline_model,
)
from app.services.recurrence import (
    MIN_CORPUS_FOR_SIGNAL,
    contexts_match,
    MIN_NEIGHBOURS_FOR_SIGNAL,
    RecurrenceMetrics,
    is_probable_duplicate,
    score_recurrence,
    thresholds_for,
)

logger = logging.getLogger("qems.signal")

NEIGHBOUR_LIMIT = 25
RECENT_WINDOW_DAYS = 90
QUARTER_DAYS = 90


class SignalStatus:
    READY = "READY"
    PENDING = "PENDING"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"      # the corpus itself is too small
    NO_COMPARABLE_FINDINGS = "NO_COMPARABLE_FINDINGS"  # corpus is fine; this error is novel
    DUPLICATE_SUSPECTED = "DUPLICATE_SUSPECTED"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


def _fingerprint(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def source_text(error: Error) -> str:
    """Exactly what gets embedded. Kept in one place so the stored hash always matches."""
    return f"{error.title}\n{error.description}"


def source_hash(error: Error) -> str:
    return hashlib.sha256(source_text(error).encode()).hexdigest()


class SignalService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.errors = ErrorRepository(db)
        self.audit = AuditLogRepository(db)

    # ------------------------------------------------------------- embedding
    async def ensure_embedding(self, error: Error) -> bool:
        """Embed on creation, or re-embed when the source text has changed since.

        `embedding_source_hash` is what makes a stale vector detectable: editing a
        description after the fact would otherwise leave the error permanently retrieved
        against text nobody can see any more.
        """
        current_hash = source_hash(error)
        if error.description_embedding is not None and error.embedding_source_hash == current_hash:
            return False

        result = await generate_embedding(source_text(error))
        error.description_embedding = result.vector
        error.embedding_model = result.model
        error.embedded_at = datetime.now(timezone.utc)
        error.embedding_source_hash = current_hash

        # A changed description invalidates any insight derived from the old text.
        await self.db.execute(
            AIInsight.__table__.update()
            .where(
                AIInsight.error_id == error.error_id,
                AIInsight.status == InsightStatus.FRESH,
            )
            .values(status=InsightStatus.STALE)
        )
        await self.db.flush()
        return True

    # --------------------------------------------------------------- metrics
    async def _corpus_size(self, embedding_model: str | None) -> int:
        return (
            await self.db.execute(
                select(func.count())
                .select_from(Error)
                .where(
                    Error.description_embedding.isnot(None),
                    Error.embedding_model == embedding_model,
                )
            )
        ).scalar_one()

    async def _compute_metrics(
        self, error: Error, neighbour_ids: list[int]
    ) -> RecurrenceMetrics:
        """Every figure the reviewer will read, computed in SQL.

        Quarter windows are relative to the error's own creation time rather than to
        `now()`, so re-running the signal months later reproduces the same numbers.
        """
        if not neighbour_ids:
            return RecurrenceMetrics()

        anchor = error.created_at or datetime.now(timezone.utc)
        if anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)

        recent_cutoff = anchor - timedelta(days=RECENT_WINDOW_DAYS)
        prev_quarter_start = anchor - timedelta(days=QUARTER_DAYS * 2)

        row = (
            await self.db.execute(
                select(
                    func.count().filter(Error.created_at >= recent_cutoff).label("similar_90d"),
                    func.count()
                    .filter(
                        Error.created_at >= recent_cutoff,
                        Error.process_id.isnot(None),
                        Error.process_id == error.process_id,
                    )
                    .label("same_process"),
                    func.count()
                    .filter(
                        Error.created_at >= recent_cutoff,
                        Error.department_id == error.department_id,
                    )
                    .label("same_team"),
                    func.count()
                    .filter(
                        Error.created_at >= recent_cutoff,
                        Error.category_id == error.category_id,
                    )
                    .label("same_category"),
                    func.count()
                    .filter(Error.created_at >= recent_cutoff)
                    .label("current_quarter"),
                    func.count()
                    .filter(
                        Error.created_at >= prev_quarter_start,
                        Error.created_at < recent_cutoff,
                    )
                    .label("previous_quarter"),
                ).where(Error.error_id.in_(neighbour_ids))
            )
        ).one()

        return RecurrenceMetrics(
            similar_90d=row.similar_90d,
            same_process=row.same_process,
            same_team=row.same_team,
            same_category=row.same_category,
            current_quarter_count=row.current_quarter,
            previous_quarter_count=row.previous_quarter,
            prior_capa_ineffective=False,  # wired up with the CAPA register (KB-07)
        )

    # ---------------------------------------------------------------- signal
    async def compute(
        self, error: Error, *, visible_department_ids: list[int] | None = None
    ) -> dict:
        """Produce (and persist) the recurrence signal for one error."""
        await self.ensure_embedding(error)

        corpus = await self._corpus_size(error.embedding_model)
        if corpus < MIN_CORPUS_FOR_SIGNAL:
            # A confident risk band drawn from nine historical rows destroys trust
            # permanently on day one. Say "not enough history" and mean it.
            return {
                "status": SignalStatus.INSUFFICIENT_HISTORY,
                "corpus_size": corpus,
                "required": MIN_CORPUS_FOR_SIGNAL,
            }

        ceiling, duplicate_floor = thresholds_for(error.embedding_model)
        neighbours = await self.errors.find_neighbours(
            error.description_embedding,
            exclude_error_id=error.error_id,
            limit=NEIGHBOUR_LIMIT,
            max_distance=ceiling,
            department_ids=visible_department_ids,
            embedding_model=error.embedding_model,
        )

        nearest = neighbours[0] if neighbours else None
        if nearest is not None and is_probable_duplicate(
            nearest[1],
            duplicate_floor,
            # Same control, same team — otherwise near-identical wording is just a shared
            # template, not a re-filing of one incident. An unknown process on either
            # side is treated as unknown rather than as a mismatch (see contexts_match).
            same_context=contexts_match(
                category_a=error.category_id, category_b=nearest[0].category_id,
                department_a=error.department_id, department_b=nearest[0].department_id,
                process_a=error.process_id, process_b=nearest[0].process_id,
            ),
            days_apart=(
                abs((error.date_discovered - nearest[0].date_discovered).days)
                if error.date_discovered and nearest[0].date_discovered
                else None
            ),
        ):
            return {
                "status": SignalStatus.DUPLICATE_SUSPECTED,
                "duplicate_of": {
                    "error_id": nearest[0].error_id,
                    "qa_error_code": nearest[0].qa_error_code,
                    "distance": round(nearest[1], 4),
                },
            }

        if len(neighbours) < MIN_NEIGHBOURS_FOR_SIGNAL:
            # The gate. No AI call happens below this line, which is what keeps the
            # feature affordable — most errors never reach the model at all.
            return {
                "status": SignalStatus.NO_COMPARABLE_FINDINGS,
                "corpus_size": corpus,
                "neighbours_found": len(neighbours),
                "required": MIN_NEIGHBOURS_FOR_SIGNAL,
            }

        neighbour_ids = [n[0].error_id for n in neighbours]
        metrics = await self._compute_metrics(error, neighbour_ids)
        score, band, breakdown = score_recurrence(metrics, error.severity)

        fingerprint = _fingerprint(
            {
                "error": error.error_id,
                "source": error.embedding_source_hash,
                "neighbours": sorted(neighbour_ids),
                "severity": error.severity,
            }
        )

        cached = (
            await self.db.execute(
                select(AIInsight).where(
                    AIInsight.input_fingerprint == fingerprint,
                    AIInsight.status == InsightStatus.FRESH,
                )
            )
        ).scalar_one_or_none()
        if cached is not None:
            return self._as_response(cached, neighbours)

        narrative, narration_status = await self._narrate(error, metrics, band, neighbours)

        # Supersede rather than overwrite: the record of what was actually shown at
        # decision time has to survive a recompute.
        await self.db.execute(
            AIInsight.__table__.update()
            .where(
                AIInsight.error_id == error.error_id,
                AIInsight.insight_type == InsightType.RECURRENCE,
                AIInsight.status == InsightStatus.FRESH,
            )
            .values(status=InsightStatus.SUPERSEDED)
        )

        insight = AIInsight(
            error_id=error.error_id,
            insight_type=InsightType.RECURRENCE,
            model_name=error.embedding_model or OFFLINE_MODEL_NAME,
            input_fingerprint=fingerprint,
            retrieved_error_ids=neighbour_ids,
            metrics={
                "similar_90d": metrics.similar_90d,
                "same_process": metrics.same_process,
                "same_team": metrics.same_team,
                "same_category": metrics.same_category,
                "qoq_delta_pct": round(metrics.qoq_delta_pct, 2),
                "current_quarter_count": metrics.current_quarter_count,
                "previous_quarter_count": metrics.previous_quarter_count,
                "nearest_distance": round(neighbours[0][1], 4),
                "corpus_size": corpus,
            },
            score_breakdown=breakdown,
            risk_score=score,
            risk_band=band,
            ai_output=narrative,
            # ai_gateway.py's recurrence_narrative() already registers this version in
            # ai_prompt_versions (via _ensure_prompt_version) before returning, and puts
            # it in the narrative dict it hands back -- but nothing ever copied it onto
            # the insight row's own FK column, so a successful narration still showed
            # "Prompt: n/a" in provenance right next to real generated text.
            prompt_version=narrative.get("prompt_version") if narrative else None,
            status=narration_status,
        )
        self.db.add(insight)
        await self.db.flush()

        await self.audit.create(
            action="AI_RECURRENCE_SIGNAL",
            actor_type=ActorType.SYSTEM_AI,
            error_id=error.error_id,
            after_value={"risk_band": band, "risk_score": score, "status": narration_status},
            insight_id=insight.insight_id,
            reason=f"{metrics.similar_90d} similar findings in {RECENT_WINDOW_DAYS} days",
        )

        return self._as_response(insight, neighbours)

    async def _narrate(
        self, error: Error, metrics: RecurrenceMetrics, band: str, neighbours: list
    ) -> tuple[dict | None, str]:
        """The one inferred step. Returns (output, insight_status).

        The model receives the already-computed facts and produces language only. It is
        given no field in which to express a decision, and it cannot alter the band.
        """
        from app.services.ai_gateway import AIGateway, AIUnavailable

        try:
            output = await AIGateway(self.db).recurrence_narrative(
                error=error, metrics=metrics, band=band, neighbours=neighbours
            )
            return output, InsightStatus.FRESH
        except AIUnavailable as exc:
            # Deliberate: the deterministic half above is already complete and correct.
            logger.info("Narration unavailable (%s); serving metrics only", exc)
            return None, InsightStatus.DEGRADED

    def _as_response(self, insight: AIInsight, neighbours: list) -> dict:
        by_id = {n[0].error_id: n for n in neighbours}
        return {
            "status": SignalStatus.DEGRADED
            if insight.status == InsightStatus.DEGRADED
            else SignalStatus.READY,
            "insight_id": insight.insight_id,
            "risk_band": insight.risk_band,
            "risk_score": float(insight.risk_score) if insight.risk_score is not None else None,
            "metrics": insight.metrics,
            "score_breakdown": insight.score_breakdown,
            "narrative": insight.ai_output,
            "neighbours": [
                {
                    "error_id": eid,
                    "qa_error_code": by_id[eid][0].qa_error_code,
                    "title": by_id[eid][0].title,
                    "status": by_id[eid][0].status,
                    "severity": by_id[eid][0].severity,
                    "created_at": by_id[eid][0].created_at,
                    "distance": round(by_id[eid][1], 4),
                }
                for eid in (insight.retrieved_error_ids or [])
                if eid in by_id
            ],
            "provenance": {
                "model": insight.model_name,
                "prompt_version": insight.prompt_version,
                "generated_at": insight.created_at,
                "retrieved_error_ids": insight.retrieved_error_ids,
                "offline_embedder": is_offline_model(insight.model_name),
            },
            "reviewer_action": insight.reviewer_action,
            "disclaimer": (
                "Computed figures are from the QEMS database. Any narrative is "
                "AI-generated and advisory. QA remains responsible for the decision."
            ),
        }
