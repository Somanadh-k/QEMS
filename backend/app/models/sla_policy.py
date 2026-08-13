from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SLAPolicy(Base):
    __tablename__ = "sla_policies"
    __table_args__ = (CheckConstraint("sla_hours > 0", name="ck_sla_hours_positive"),)

    sla_policy_id: Mapped[int] = mapped_column(primary_key=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    sla_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    categories: Mapped[list["Category"]] = relationship(back_populates="sla_policy")
