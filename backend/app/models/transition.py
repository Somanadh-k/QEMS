"""Typed lifecycle transition ledger (proposal SM-10).

Transition history was previously inferable only from generically-typed audit rows.
Promoting it to its own table makes "how long did this sit in Rebuttal Raised" a query
rather than an archaeology exercise, and gives escalated/reopened work somewhere to be
counted — finding F-08 noted that `qa_decisions` permits 'Escalated' while the status
enum has no matching state, so an escalated error was indistinguishable from an
unstarted one in every list and count.
"""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ErrorTransition(Base):
    __tablename__ = "error_transitions"
    __table_args__ = (Index("idx_transition_error", "error_id", "occurred_at"),)

    transition_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    error_id: Mapped[int] = mapped_column(
        ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="USER")
    # Required for any move that is not a normal forward step.
    reason: Mapped[str | None] = mapped_column(Text)
    rule_applied: Mapped[str | None] = mapped_column(String(60))
    round_no: Mapped[int] = mapped_column(nullable=False, default=1)
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
