from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class QADecision(Base):
    __tablename__ = "qa_decisions"
    __table_args__ = (
        CheckConstraint("decision IN ('Resolved','Rejected','Escalated')", name="ck_qa_decision_value"),
    )

    decision_id: Mapped[int] = mapped_column(primary_key=True)
    error_id: Mapped[int] = mapped_column(ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=False)
    decided_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    error: Mapped["Error"] = relationship(back_populates="decisions")
