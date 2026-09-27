"""Governance risk score — pure function, so tested exhaustively without a database."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Error
from app.services.risk_service import WEIGHTS, compute_risk


def make_error(severity="Medium", age_days=0.0):
    e = Error(title="t", description="d", category_id=1, severity=severity,
              department_id=1, raised_by=1, date_discovered=datetime.now(timezone.utc).date())
    e.created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
    return e


def test_weights_sum_to_one():
    """If these drift apart the score silently stops being a percentage."""
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_score_is_bounded():
    worst = compute_risk(make_error("Critical", age_days=365), sla_ratio=99,
                         recurrence_band="HIGH", has_open_rebuttal=True, business_impact=1.0)[0]
    best = compute_risk(make_error("Low"), sla_ratio=0)[0]
    assert 0 <= best <= worst <= 100


def test_severity_dominates_an_otherwise_identical_pair():
    critical = compute_risk(make_error("Critical"))[0]
    low = compute_risk(make_error("Low"))[0]
    assert critical > low


def test_breach_outranks_a_fresh_critical():
    """A breached High must sort above an untouched Critical — the queue's whole point."""
    breached_high = compute_risk(make_error("High"), sla_ratio=1.4, recurrence_band="HIGH")[0]
    fresh_critical = compute_risk(make_error("Critical"), sla_ratio=0.0)[0]
    assert breached_high > fresh_critical


def test_breakdown_contributions_reconstruct_the_score():
    """The popover must be able to explain the number exactly, not approximately."""
    score, breakdown = compute_risk(make_error("High"), sla_ratio=0.5,
                                    recurrence_band="MEDIUM", has_open_rebuttal=True)
    assert sum(c["contribution"] for c in breakdown["components"]) == pytest.approx(score, abs=0.01)
    assert {c["name"] for c in breakdown["components"]} == set(WEIGHTS)


def test_age_saturates_rather_than_growing_forever():
    a = compute_risk(make_error("Medium", age_days=30))[0]
    b = compute_risk(make_error("Medium", age_days=3000))[0]
    assert a == b


def test_recurrence_band_absent_contributes_nothing():
    with_band = compute_risk(make_error("Medium"), recurrence_band="HIGH")[0]
    without = compute_risk(make_error("Medium"), recurrence_band=None)[0]
    assert with_band > without
