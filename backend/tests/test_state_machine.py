import pytest

from app.core.exceptions import ConflictError
from app.models import ErrorStatus
from app.services.error_state_machine import assert_valid_transition


def test_open_to_in_review_is_allowed():
    assert_valid_transition(ErrorStatus.OPEN, ErrorStatus.IN_REVIEW)


def test_open_to_closed_is_rejected():
    with pytest.raises(ConflictError):
        assert_valid_transition(ErrorStatus.OPEN, ErrorStatus.CLOSED)


def test_in_review_can_go_to_rebuttal_or_qa_decision():
    assert_valid_transition(ErrorStatus.IN_REVIEW, ErrorStatus.REBUTTAL_RAISED)
    assert_valid_transition(ErrorStatus.IN_REVIEW, ErrorStatus.QA_DECISION_PENDING)


def test_closed_has_no_outgoing_transitions():
    with pytest.raises(ConflictError):
        assert_valid_transition(ErrorStatus.CLOSED, ErrorStatus.OPEN)


def test_admin_override_bypasses_state_machine():
    # No exception raised even though Open -> Closed is not a normal transition.
    assert_valid_transition(ErrorStatus.OPEN, ErrorStatus.CLOSED, admin_override=True)


def test_qa_decision_pending_to_resolved_or_rejected():
    assert_valid_transition(ErrorStatus.QA_DECISION_PENDING, ErrorStatus.RESOLVED)
    assert_valid_transition(ErrorStatus.QA_DECISION_PENDING, ErrorStatus.REJECTED)
    with pytest.raises(ConflictError):
        assert_valid_transition(ErrorStatus.QA_DECISION_PENDING, ErrorStatus.IN_REVIEW)
