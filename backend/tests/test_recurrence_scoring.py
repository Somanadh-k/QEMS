"""Recurrence scorer — the arithmetic the model is never allowed to perform."""

import pytest

from app.services.recurrence import (
    BAND_HIGH,
    BAND_MEDIUM,
    WEIGHTS,
    RecurrenceMetrics,
    is_probable_duplicate,
    score_recurrence,
)


def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_no_history_scores_low():
    score, band, _ = score_recurrence(RecurrenceMetrics(), "Low")
    assert band == "LOW"
    assert score < BAND_MEDIUM


def test_the_worked_example_from_the_proposal_lands_high():
    """17 similar, 8 same process, +34% QoQ, Critical -> HIGH."""
    metrics = RecurrenceMetrics(
        similar_90d=17, same_process=8, same_team=5,
        previous_quarter_count=50, current_quarter_count=67,
    )
    score, band, breakdown = score_recurrence(metrics, "Critical")
    assert metrics.qoq_delta_pct == pytest.approx(34.0)
    assert band == "HIGH"
    assert score >= BAND_HIGH
    assert sum(c["contribution"] for c in breakdown["components"]) == pytest.approx(score, abs=0.01)


def test_failed_prior_capa_pushes_a_borderline_case_up():
    base = RecurrenceMetrics(similar_90d=8, same_process=4,
                             previous_quarter_count=10, current_quarter_count=11)
    without, band_without, _ = score_recurrence(base, "Medium")

    with_failed_capa = RecurrenceMetrics(
        similar_90d=8, same_process=4, previous_quarter_count=10,
        current_quarter_count=11, prior_capa_ineffective=True,
    )
    with_score, _, _ = score_recurrence(with_failed_capa, "Medium")
    assert with_score == pytest.approx(without + 10.0, abs=0.01)


def test_score_is_bounded_at_both_ends():
    worst = score_recurrence(
        RecurrenceMetrics(similar_90d=9999, same_process=9999,
                          previous_quarter_count=1, current_quarter_count=9999,
                          prior_capa_ineffective=True),
        "Critical",
    )[0]
    assert worst <= 100.0
    assert score_recurrence(RecurrenceMetrics(), "Low")[0] >= 0.0


def test_volume_saturates_so_one_cluster_cannot_swamp_the_scale():
    a = score_recurrence(RecurrenceMetrics(similar_90d=20), "Medium")[0]
    b = score_recurrence(RecurrenceMetrics(similar_90d=2000), "Medium")[0]
    assert a == b


def test_rise_from_a_zero_baseline_does_not_divide_by_zero():
    m = RecurrenceMetrics(similar_90d=4, previous_quarter_count=0, current_quarter_count=4)
    assert m.qoq_delta_pct == 50.0
    score_recurrence(m, "High")  # must not raise


def test_a_falling_trend_never_contributes_negatively():
    falling = RecurrenceMetrics(similar_90d=5, previous_quarter_count=100, current_quarter_count=10)
    _, _, breakdown = score_recurrence(falling, "Medium")
    trend = next(c for c in breakdown["components"] if c["name"] == "trend")
    assert trend["contribution"] == 0.0


def test_process_concentration_is_a_ratio_not_a_count():
    concentrated = RecurrenceMetrics(similar_90d=10, same_process=10)
    diffuse = RecurrenceMetrics(similar_90d=10, same_process=1)
    assert score_recurrence(concentrated, "Medium")[0] > score_recurrence(diffuse, "Medium")[0]


def test_duplicate_detection_separates_refiling_from_recurrence():
    assert is_probable_duplicate(0.01) is True
    assert is_probable_duplicate(0.18) is False
    assert is_probable_duplicate(None) is False


def test_shared_template_wording_is_not_a_duplicate():
    """Two separate breaches written from the same template must not be suppressed.

    This is the failure that matters: quality teams reuse wording, so text distance alone
    would classify genuinely distinct recurrences as re-filings and hide the pattern.
    """
    # Near-identical text, but different process/team context.
    assert is_probable_duplicate(0.01, same_context=False) is False
    # Near-identical text and same context, but months apart — not one incident.
    assert is_probable_duplicate(0.01, same_context=True, days_apart=90) is False
    # Near-identical, same context, same week — a genuine re-filing.
    assert is_probable_duplicate(0.01, same_context=True, days_apart=1) is True


# --- context matching (finding O-01) -----------------------------------------

def _ctx(cat_a=1, cat_b=1, dep_a=1, dep_b=1, proc_a=5, proc_b=5):
    from app.services.recurrence import contexts_match
    return contexts_match(category_a=cat_a, category_b=cat_b, department_a=dep_a,
                          department_b=dep_b, process_a=proc_a, process_b=proc_b)


def test_identical_context_matches():
    assert _ctx() is True


def test_different_category_or_department_is_a_different_context():
    assert _ctx(cat_b=2) is False
    assert _ctx(dep_b=2) is False


def test_different_known_processes_do_not_match():
    """When both processes are known, a mismatch is real evidence of a different context."""
    assert _ctx(proc_a=5, proc_b=6) is False


def test_unknown_process_does_not_rule_a_duplicate_out():
    """O-01 regression.

    A record predating the process column carries NULL. Treating that as a mismatch made
    two byte-identical findings from the same team on the same day permanently
    unmatchable. Unknown must mean unknown, not different.
    """
    assert _ctx(proc_a=None, proc_b=6) is True
    assert _ctx(proc_a=6, proc_b=None) is True
    assert _ctx(proc_a=None, proc_b=None) is True


def test_unknown_process_still_requires_the_other_signals():
    """Unknown process must not rule a duplicate *in* either."""
    assert _ctx(proc_a=None, proc_b=6, cat_b=99) is False
    assert _ctx(proc_a=None, proc_b=6, dep_b=99) is False
