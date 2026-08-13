from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Rebuttal(Base):
    __tablename__ = "rebuttals"

    rebuttal_id: Mapped[int] = mapped_column(primary_key=True)
    error_id: Mapped[int] = mapped_column(ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=False)
    raised_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    error: Mapped["Error"] = relationship(back_populates="rebuttals")
