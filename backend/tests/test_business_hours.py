"""Business-hours arithmetic — the function every SLA number depends on.

Pure function, so these tests need no database and no network. The failure mode being
guarded against is not a crash but a plausible wrong number, so the cases here are the
awkward ones: DST boundaries, long weekends, starts outside working hours.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.business_hours import (
    WorkCalendar,
    add_business_hours,
    consumption_ratio,
    elapsed_business_seconds,
)

UTC = ZoneInfo("UTC")
LONDON = "Europe/London"

CAL = WorkCalendar(timezone=LONDON, workday_start=time(9, 0), workday_end=time(17, 0))


def london(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(LONDON))


def test_elapsed_within_a_single_working_day():
    start, end = london(2026, 3, 10, 10, 0), london(2026, 3, 10, 15, 30)
    assert elapsed_business_seconds(start, end, CAL) == 5.5 * 3600


def test_elapsed_excludes_evenings():
    # 16:00 Tuesday to 10:00 Wednesday is 18 wall hours but only 2 working hours.
    start, end = london(2026, 3, 10, 16, 0), london(2026, 3, 11, 10, 0)
    assert elapsed_business_seconds(start, end, CAL) == 2 * 3600


def test_elapsed_excludes_weekends():
    # Friday 16:00 -> Monday 10:00 = 1h Friday + 1h Monday.
    start, end = london(2026, 3, 13, 16, 0), london(2026, 3, 16, 10, 0)
    assert elapsed_business_seconds(start, end, CAL) == 2 * 3600


def test_elapsed_excludes_holidays():
    cal = WorkCalendar(
        timezone=LONDON, workday_start=time(9, 0), workday_end=time(17, 0),
        holidays=frozenset({date(2026, 3, 11)}),
    )
    start, end = london(2026, 3, 10, 16, 0), london(2026, 3, 12, 10, 0)
    assert elapsed_business_seconds(start, end, cal) == 2 * 3600


def test_elapsed_is_never_negative():
    start, end = london(2026, 3, 10, 15, 0), london(2026, 3, 10, 9, 0)
    assert elapsed_business_seconds(start, end, CAL) == 0.0


def test_add_hours_rolls_over_the_evening():
    # 15:00 + 4 working hours = 2h today, 2h tomorrow -> 11:00 next working day.
    due = add_business_hours(london(2026, 3, 10, 15, 0), 4, CAL)
    assert due.astimezone(ZoneInfo(LONDON)) == london(2026, 3, 11, 11, 0)


def test_add_hours_from_outside_working_hours_starts_at_next_opening():
    # Raised at 22:00 — the budget must not burn overnight.
    due = add_business_hours(london(2026, 3, 10, 22, 0), 2, CAL)
    assert due.astimezone(ZoneInfo(LONDON)) == london(2026, 3, 11, 11, 0)


def test_the_long_weekend_case_from_the_proposal():
    """24 business hours raised Friday 16:00 before a Monday holiday.

    1h Friday + 8h Tuesday + 8h Wednesday + 7h Thursday = 24h, so due Thursday 16:00.
    A naive calendar-hours implementation would have said Saturday afternoon.
    """
    cal = WorkCalendar(
        timezone=LONDON, workday_start=time(9, 0), workday_end=time(17, 0),
        holidays=frozenset({date(2026, 3, 16)}),
    )
    due = add_business_hours(london(2026, 3, 13, 16, 0), 24, cal)
    assert due.astimezone(ZoneInfo(LONDON)) == london(2026, 3, 19, 16, 0)


def test_dst_spring_forward_preserves_working_hours():
    """UK clocks jump forward on 2026-03-29. Eight working hours must stay eight."""
    start = london(2026, 3, 27, 9, 0)          # Friday before the change
    due = add_business_hours(start, 16, CAL)   # two full working days
    local_due = due.astimezone(ZoneInfo(LONDON))
    # 8h Friday + 8h Monday. Monday 30 March is already BST, so the clock crossed the
    # transition and still delivered exactly sixteen hours of working time.
    assert local_due == london(2026, 3, 30, 17, 0)
    # And the reverse computation agrees.
    assert elapsed_business_seconds(start, due, CAL) == pytest.approx(16 * 3600, abs=1)


def test_dst_autumn_back_preserves_working_hours():
    """UK clocks fall back on 2026-10-25."""
    start = london(2026, 10, 23, 9, 0)
    due = add_business_hours(start, 16, CAL)
    assert elapsed_business_seconds(start, due, CAL) == pytest.approx(16 * 3600, abs=1)


def test_elapsed_never_exceeds_wall_clock_time():
    """Property: working time is always a subset of real time, for any pair."""
    base = london(2026, 6, 1, 0, 0)
    for start_offset in range(0, 400, 37):
        for span in range(1, 300, 41):
            start = base + timedelta(hours=start_offset)
            end = start + timedelta(hours=span)
            business = elapsed_business_seconds(start, end, CAL)
            assert 0 <= business <= (end - start).total_seconds()


def test_elapsed_is_monotonic_in_the_end_instant():
    start = london(2026, 6, 1, 9, 0)
    previous = 0.0
    for hours in range(0, 200, 7):
        value = elapsed_business_seconds(start, start + timedelta(hours=hours), CAL)
        assert value >= previous
        previous = value


def test_consumption_ratio_flags_at_risk_and_breach():
    start = london(2026, 3, 10, 9, 0)
    assert consumption_ratio(start, london(2026, 3, 10, 15, 30), 8, CAL) == pytest.approx(0.8125)
    assert consumption_ratio(start, london(2026, 3, 11, 10, 0), 8, CAL) > 1.0


def test_paused_time_is_not_charged():
    start = london(2026, 3, 10, 9, 0)
    now = london(2026, 3, 10, 17, 0)
    full = consumption_ratio(start, now, 8, CAL)
    paused = consumption_ratio(start, now, 8, CAL, paused_seconds=4 * 3600)
    assert full == pytest.approx(1.0)
    assert paused == pytest.approx(0.5)


def test_zero_length_workday_is_rejected_not_looped():
    cal = WorkCalendar(timezone="UTC", workday_start=time(9, 0), workday_end=time(9, 0))
    with pytest.raises(ValueError):
        add_business_hours(datetime(2026, 3, 10, 9, 0, tzinfo=UTC), 1, cal)


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError):
        elapsed_business_seconds(datetime(2026, 3, 10, 9, 0), datetime(2026, 3, 10, 10, 0), CAL)
