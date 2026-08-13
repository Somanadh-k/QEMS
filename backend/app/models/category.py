from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Category(Base):
    __tablename__ = "categories"

    category_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    sla_policy_id: Mapped[int | None] = mapped_column(ForeignKey("sla_policies.sla_policy_id"))

    sla_policy: Mapped["SLAPolicy | None"] = relationship(back_populates="categories")
