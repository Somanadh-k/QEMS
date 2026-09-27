import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.v1.routers import (
    ai,
    auth,
    decisions,
    errors,
    evidence,
    governance,
    lookups,
    messages,
    notifications,
    rebuttals,
    reports,
    signal,
)
from app.core.config import get_settings
from app.core.exceptions import QEMSError
from app.core.middleware import RateLimitMiddleware, RequestLoggingMiddleware
from app.workers.scheduler import build_scheduler

settings = get_settings()
logger = logging.getLogger("qems.errors")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start the background workers alongside the API (finding F-06).

    SLA breach detection, escalation and trend analysis are all fundamentally background
    work; before this the application had no scheduler at all and everything had to
    happen inside a request.
    """
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("Background scheduler started: %s", [j.id for j in scheduler.get_jobs()])
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="QEMS API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
# Auth keeps the strict login-grade limit. Read paths under /errors/ previously shared it,
# so a reviewer refreshing a detail page six times in a minute received a 429 — and the
# new sub-resources (/signal, /sla, /precedents) would have inherited the same bucket.
app.add_middleware(
    RateLimitMiddleware,
    limited_prefixes=("/api/v1/auth/login",),
    limit_per_minute=settings.login_rate_limit_per_minute,
)
app.add_middleware(
    RateLimitMiddleware,
    limited_prefixes=("/api/v1/errors/",),
    limit_per_minute=settings.api_rate_limit_per_minute,
)


@app.exception_handler(QEMSError)
async def qems_error_handler(_request: Request, exc: QEMSError) -> JSONResponse:
    """Global exception-handling middleware (Section 9.5) -> structured JSON errors."""
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request: Request, exc: IntegrityError) -> JSONResponse:
    """A bad foreign key is the client's mistake, not a server fault.

    Referencing a category, department, process or user that does not exist previously
    escaped as an opaque 500 "An unexpected error occurred", which tells an API consumer
    nothing about what to correct. Constraint violations map to 422 with the offending
    constraint named; anything else remains a 500.
    """
    origin = str(getattr(exc, "orig", exc))
    constraint = ""
    for token in origin.split('"'):
        if token.endswith("_fkey") or token.endswith("_key") or token.startswith("ck_"):
            constraint = token
            break

    if "ForeignKeyViolation" in origin or "_fkey" in origin:
        message = (
            f"A referenced record does not exist ({constraint})."
            if constraint else "A referenced record does not exist."
        )
        code = "invalid_reference"
    elif "UniqueViolation" in origin or "duplicate key" in origin:
        message = f"That value is already in use ({constraint})." if constraint else "Duplicate value."
        code = "duplicate_value"
    elif "CheckViolation" in origin:
        message = f"A field failed validation ({constraint})." if constraint else "Invalid field value."
        code = "invalid_value"
    else:
        logger.exception("Unhandled database integrity error")
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "An unexpected error occurred"}},
        )

    logger.warning("Integrity error mapped to 422: %s", origin[:300])
    return JSONResponse(status_code=422, content={"error": {"code": code, "message": message}})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Section 9.5 — never leak a raw 500 traceback; always return structured JSON."""
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500, content={"error": {"code": "internal_error", "message": "An unexpected error occurred"}}
    )


API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(errors.router, prefix=API_PREFIX)
app.include_router(evidence.router, prefix=API_PREFIX)
app.include_router(rebuttals.router, prefix=API_PREFIX)
app.include_router(decisions.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
app.include_router(ai.router, prefix=API_PREFIX)
app.include_router(lookups.router, prefix=API_PREFIX)
app.include_router(signal.router, prefix=API_PREFIX)
app.include_router(governance.router, prefix=API_PREFIX)
app.include_router(messages.router, prefix=API_PREFIX)
app.include_router(notifications.router, prefix=API_PREFIX)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health-check endpoint for orchestration (Section 5, Availability)."""
    return {"status": "ok"}
