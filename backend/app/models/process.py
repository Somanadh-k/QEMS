"""Business process dimension (proposal QS-01).

Recurrence is a property of a *process*, not of a category: "identity verification not
performed" recurring inside Account Maintenance is a systemic control weakness, while
the same category spread evenly across twelve processes is background noise. The
existing schema had no way to express that distinction.
"""

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Process(Base):
    __tablename__ = "processes"

    process_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.department_id"))
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    department: Mapped["Department | None"] = relationship()
