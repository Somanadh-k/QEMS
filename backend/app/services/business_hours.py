"""Business-hours arithmetic for SLA clocks.

This is the single function every SLA number in the product depends on, so it is a pure
function of its inputs: no database, no clock, no I/O. That makes it exhaustively
testable, which matters because the failure mode is not a crash — it is a plausible
wrong number in a leadership pack.

Correctness notes:

* All arithmetic happens in the calendar's own timezone. A 24-business-hour SLA raised
  at 16:00 on the Friday of a long weekend is due Tuesday afternoon, not Saturday.
* DST is handled by converting to local time and walking whole days: adding "8 working
  hours" must mean eight hours of wall-clock work, even on the day a clock shifts.
* Holidays and non-working weekdays are excluded entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class WorkCalendar:
    timezone: str = "UTC"
    workday_start: time = time(9, 0)
    workday_end: time = time(17, 0)
    workdays: tuple[int, ...] = (1, 2, 3, 4, 5)  # ISO weekday: Mon=1 .. Sun=7
    holidays: frozenset[date] = field(default_factory=frozenset)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def seconds_per_workday(self) -> float:
        start = timedelta(hours=self.workday_start.hour, minutes=self.workday_start.minute)
        end = timedelta(hours=self.workday_end.hour, minutes=self.workday_end.minute)
        return max((end - start).total_seconds(), 0.0)

    def is_workday(self, day: date) -> bool:
        return day.isoweekday() in self.workdays and day not in self.holidays


def _local(moment: datetime, cal: WorkCalendar) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("business-hours arithmetic requires timezone-aware datetimes")
    return moment.astimezone(cal.tz)


def _window_for(day: date, cal: WorkCalendar) -> tuple[datetime, datetime]:
    """The working window on `day`, as tz-aware local datetimes."""
    return (
        datetime.combine(day, cal.workday_start, tzinfo=cal.tz),
        datetime.combine(day, cal.workday_end, tzinfo=cal.tz),
    )


def elapsed_business_seconds(start: datetime, end: datetime, cal: WorkCalendar) -> float:
    """Working seconds between two instants. Never negative, never exceeds wall time."""
    if end <= start:
        return 0.0

    local_start, local_end = _local(start, cal), _local(end, cal)
    total = 0.0
    day = local_start.date()

    while day <= local_end.date():
        if cal.is_workday(day):
            window_open, window_close = _window_for(day, cal)
            segment_start = max(local_start, window_open)
            segment_end = min(local_end, window_close)
            if segment_end > segment_start:
                total += (segment_end - segment_start).total_seconds()
        day += timedelta(days=1)

    return total


def add_business_hours(start: datetime, hours: float, cal: WorkCalendar) -> datetime:
    """The instant `hours` working hours after `start`, as a UTC datetime.

    A start outside working hours rolls forward to the next window opening, so an error
    raised at 22:00 does not silently consume its budget overnight.
    """
    if cal.seconds_per_workday <= 0:
        raise ValueError("calendar has a zero-length working day")

    remaining = float(hours) * 3600.0
    cursor = _local(start, cal)

    # Guard against a calendar with no working days at all rather than looping forever.
    safety_limit = 3650
    days_examined = 0

    while remaining > 0:
        if days_examined > safety_limit:
            raise ValueError("calendar defines no reachable working time")

        day = cursor.date()
        if not cal.is_workday(day):
            cursor = datetime.combine(day + timedelta(days=1), cal.workday_start, tzinfo=cal.tz)
            days_examined += 1
            continue

        window_open, window_close = _window_for(day, cal)
        if cursor < window_open:
            cursor = window_open
        if cursor >= window_close:
            cursor = datetime.combine(day + timedelta(days=1), cal.workday_start, tzinfo=cal.tz)
            days_examined += 1
            continue

        available = (window_close - cursor).total_seconds()
        if remaining <= available:
            return (cursor + timedelta(seconds=remaining)).astimezone(ZoneInfo("UTC"))

        remaining -= available
        cursor = datetime.combine(day + timedelta(days=1), cal.workday_start, tzinfo=cal.tz)
        days_examined += 1

    return cursor.astimezone(ZoneInfo("UTC"))


def consumption_ratio(
    start: datetime, now: datetime, budget_hours: float, cal: WorkCalendar, paused_seconds: float = 0.0
) -> float:
    """Fraction of the budget consumed. 0.8 is at-risk, >= 1.0 is a breach."""
    if budget_hours <= 0:
        return 0.0
    consumed = max(elapsed_business_seconds(start, now, cal) - paused_seconds, 0.0)
    return consumed / (budget_hours * 3600.0)
