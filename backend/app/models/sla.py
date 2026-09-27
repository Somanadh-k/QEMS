"""SLA, aging and escalation engine (proposal SLA-02).

Replaces the single-hop `categories -> sla_policies` lookup, which ignored severity
entirely (finding F-01: every seeded category pointed at the Medium policy, so a
Critical error and a Low error both received 72 hours).

Two ideas carry the design:

* **Stage-scoped clocks.** One budget per stage (respond, rebut, decide, close) rather
  than one deadline for the whole error, so lateness is attributable.
* **Clock ownership.** `sla_clock_owner_role` records whose court the ball is in. Time
  spent waiting on operations is not charged to QA, and vice versa. Without this the
  breach metric measures the wrong team and gets argued into irrelevance.
"""

from datetime import date, datetime, time
from enum import StrEnum

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SLAStage(StrEnum):
    RESPOND = "RESPOND"   # owner acknowledges the finding
    REBUT = "REBUT"       # operations submits a rebuttal, if any
    DECIDE = "DECIDE"     # QA records the final decision
    CLOSE = "CLOSE"


class SLAState(StrEnum):
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"
    PAUSED = "PAUSED"
    MET = "MET"


class SLAEventType(StrEnum):
    START = "START"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    AT_RISK = "AT_RISK"
    BREACH = "BREACH"
    MET = "MET"


class BusinessCalendar(Base):
    __tablename__ = "business_calendars"

    calendar_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    timezone: Mapped[str] = mapped_column(String(60), nullable=False, default="UTC")
    workday_start: Mapped[time] = mapped_column(Time, nullable=False)
    workday_end: Mapped[time] = mapped_column(Time, nullable=False)
    # ISO weekday numbers: Monday = 1 ... Sunday = 7.
    workdays: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)

    holidays: Mapped[list["CalendarHoliday"]] = relationship(
        back_populates="calendar", cascade="all, delete-orphan"
    )


class CalendarHoliday(Base):
    __tablename__ = "calendar_holidays"

    calendar_id: Mapped[int] = mapped_column(
        ForeignKey("business_calendars.calendar_id", ondelete="CASCADE"), primary_key=True
    )
    holiday_date: Mapped[date] = mapped_column(Date, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120))

    calendar: Mapped["BusinessCalendar"] = relationship(back_populates="holidays")


class SLAMatrix(Base):
    """Effective-dated budgets. NULL in a dimension is a wildcard; most specific wins.

    Policies are versioned rather than edited: retroactively re-baselining a running
    clock rewrites history, so the row that applied when a stage started is the row that
    governs it (recorded on the sla_events START row).
    """

    __tablename__ = "sla_matrix"
    __table_args__ = (
        CheckConstraint("budget_hours > 0", name="ck_sla_matrix_budget_positive"),
        CheckConstraint(
            "stage IN ('RESPOND','REBUT','DECIDE','CLOSE')", name="ck_sla_matrix_stage"
        ),
        Index("idx_sla_matrix_lookup", "severity", "stage", "effective_from"),
    )

    sla_id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.category_id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.department_id"))
    severity: Mapped[str | None] = mapped_column(String(20))
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    budget_hours: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    business_hours_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    calendar_id: Mapped[int | None] = mapped_column(ForeignKey("business_calendars.calendar_id"))
    effective_from: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    effective_to: Mapped[datetime | None]

    @property
    def specificity(self) -> int:
        """How many dimensions this row pins down — the tie-break for policy resolution."""
        return sum(
            1 for v in (self.category_id, self.department_id, self.severity) if v is not None
        )


class SLAEvent(Base):
    """Append-only clock history; the authoritative SLA record.

    `errors.sla_state` is a derived cache that can be rebuilt entirely from this table.
    """

    __tablename__ = "sla_events"
    __table_args__ = (Index("idx_sla_events_error", "error_id", "occurred_at"),)

    event_id: Mapped[int] = mapped_column(primary_key=True)
    error_id: Mapped[int] = mapped_column(
        ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    owner_role: Mapped[str | None] = mapped_column(String(50))
    due_at: Mapped[datetime | None]
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    sla_id: Mapped[int | None] = mapped_column(ForeignKey("sla_matrix.sla_id"))


class EscalationRule(Base):
    __tablename__ = "escalation_rules"
    __table_args__ = (
        CheckConstraint(
            "trigger IN ('AT_RISK','BREACH','LEVEL_TIMEOUT')", name="ck_escalation_trigger"
        ),
    )

    rule_id: Mapped[int] = mapped_column(primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    severity_min: Mapped[str | None] = mapped_column(String(20))
    target_role: Mapped[str | None] = mapped_column(String(50))
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    # Stops a recovering worker from re-firing the same escalation every tick.
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=720)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Escalation(Base):
    __tablename__ = "escalations"
    __table_args__ = (
        # The line that prevents an escalation storm after a worker restart: replaying a
        # missed window can only ever produce one row per (error, level, rule, recipient).
        # Scoped per-recipient (not just per-rule) because a rule can fan out to every
        # user holding target_role -- e.g. 6 QA Reviewers -- and each of them legitimately
        # gets their own escalation/email; the old (error, level, rule) scope collided on
        # the 2nd recipient of any multi-target rule.
        UniqueConstraint("error_id", "level", "rule_id", "escalated_to", name="ux_escalation_once"),
        Index("idx_escalation_open", "acknowledged_at"),
    )

    escalation_id: Mapped[int] = mapped_column(primary_key=True)
    error_id: Mapped[int] = mapped_column(
        ForeignKey("errors.error_id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rule_id: Mapped[int] = mapped_column(ForeignKey("escalation_rules.rule_id"), nullable=False)
    escalated_to: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    acknowledged_at: Mapped[datetime | None]
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    # Acknowledging alone is not enough — a commitment has to be recorded with it.
    next_action: Mapped[str | None] = mapped_column(Text)
    eta: Mapped[datetime | None]
