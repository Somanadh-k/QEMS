"""Append-only audit writer with a tamper-evident hash chain.

Append-only is enforced by design here (no update/delete methods) and by grant in the
database (see migration a1b2c3d4e5f6 notes). A code convention that says "never
updated" is a comment; a revoked grant is a control.
"""

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActorType, AuditLog

# Fixed key for the transaction-scoped advisory lock that serialises chain writes.
_AUDIT_CHAIN_LOCK = 941_726_301


class AuditLogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        action: str,
        actor_id: int | None = None,
        actor_type: str = ActorType.USER,
        error_id: int | None = None,
        before_value: dict | None = None,
        after_value: dict | None = None,
        reason: str | None = None,
        request_id: str | None = None,
        insight_id: int | None = None,
    ) -> AuditLog:
        # The chain is only meaningful if writers agree on their predecessor. Two
        # concurrent transactions would otherwise read the same tip and produce a fork
        # that verification reports as a break. A transaction-scoped advisory lock
        # serialises just this insert; it is released on commit or rollback, and audit
        # write volume is low enough that the contention cost is irrelevant.
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _AUDIT_CHAIN_LOCK})

        prev_hash = (
            await self.db.execute(
                select(AuditLog.row_hash).order_by(AuditLog.audit_id.desc()).limit(1)
            )
        ).scalar_one_or_none()

        # Set created_at explicitly rather than leaning on the server default: the hash
        # must cover the value actually stored, and the server default is not visible on
        # the Python object until after flush.
        created_at = datetime.now(timezone.utc)

        entry = AuditLog(
            error_id=error_id,
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            before_value=before_value,
            after_value=after_value,
            reason=reason,
            request_id=request_id,
            insight_id=insight_id,
            prev_hash=prev_hash,
            created_at=created_at,
        )
        entry.row_hash = entry.compute_hash(prev_hash, created_at)

        self.db.add(entry)
        await self.db.flush()
        return entry

    async def verify_chain(self, limit: int | None = None) -> dict:
        """Walk the chain and report the first break, if any.

        This does not prevent tampering — it makes tampering detectable, which is the
        property an external auditor actually asks for.
        """
        query = select(AuditLog).order_by(AuditLog.audit_id.asc())
        if limit:
            query = query.limit(limit)
        rows = list((await self.db.execute(query)).scalars().all())

        expected_prev: str | None = None
        for row in rows:
            if row.row_hash is None:
                # Rows written before the chain existed are reported, not treated as breaks.
                expected_prev = row.row_hash
                continue
            recomputed = row.compute_hash(row.prev_hash, row.created_at)
            if row.prev_hash != expected_prev:
                return {
                    "valid": False,
                    "checked": len(rows),
                    "broken_at": row.audit_id,
                    "reason": "prev_hash does not match the preceding row",
                }
            if recomputed != row.row_hash:
                return {
                    "valid": False,
                    "checked": len(rows),
                    "broken_at": row.audit_id,
                    "reason": "row content does not match its stored hash",
                }
            expected_prev = row.row_hash

        return {"valid": True, "checked": len(rows), "broken_at": None, "reason": None}
