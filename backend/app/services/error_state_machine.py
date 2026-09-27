from app.core.exceptions import ConflictError, ValidationError
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
    # An unrecognised target string used to reach ErrorStatus(target) below and raise a
    # bare ValueError, which no handler maps to a clean response -- it fell through to
    # the generic 500 handler (finding D-03). Validate membership first so a malformed
    # or forged status value is a 422, not a crash.
    try:
        target_status = ErrorStatus(target)
    except ValueError as exc:
        valid = ", ".join(s.value for s in ErrorStatus)
        raise ValidationError(f"'{target}' is not a valid status. Must be one of: {valid}") from exc

    if admin_override:
        return

    current_status = ErrorStatus(current)
    if target_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
        raise ConflictError(f"Cannot transition error from '{current}' to '{target}'")
