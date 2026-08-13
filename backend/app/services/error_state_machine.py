from app.core.exceptions import ConflictError
from app.models import ErrorStatus

# Section 7.6 Workflow Diagram (Error State Machine)
ALLOWED_TRANSITIONS: dict[ErrorStatus, set[ErrorStatus]] = {
    ErrorStatus.OPEN: {ErrorStatus.IN_REVIEW},
    ErrorStatus.IN_REVIEW: {ErrorStatus.REBUTTAL_RAISED, ErrorStatus.QA_DECISION_PENDING},
    ErrorStatus.REBUTTAL_RAISED: {ErrorStatus.QA_DECISION_PENDING},
    ErrorStatus.QA_DECISION_PENDING: {ErrorStatus.RESOLVED, ErrorStatus.REJECTED},
    ErrorStatus.RESOLVED: {ErrorStatus.CLOSED},
    ErrorStatus.REJECTED: {ErrorStatus.CLOSED},
    ErrorStatus.CLOSED: set(),
}


def assert_valid_transition(current: str, target: str, admin_override: bool = False) -> None:
    if admin_override:
        return
    current_status = ErrorStatus(current)
    target_status = ErrorStatus(target)
    if target_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
        raise ConflictError(f"Cannot transition error from '{current}' to '{target}'")
