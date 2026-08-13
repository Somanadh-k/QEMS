class QEMSError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(QEMSError):
    status_code = 404
    code = "not_found"


class PermissionDeniedError(QEMSError):
    status_code = 403
    code = "permission_denied"


class ValidationError(QEMSError):
    status_code = 422
    code = "validation_error"


class ConflictError(QEMSError):
    status_code = 409
    code = "conflict"


class UnauthorizedError(QEMSError):
    status_code = 401
    code = "unauthorized"


class AIServiceError(QEMSError):
    """Raised when the OpenAI API call itself fails (auth, rate limit, timeout, etc.)."""

    status_code = 503
    code = "ai_service_unavailable"
