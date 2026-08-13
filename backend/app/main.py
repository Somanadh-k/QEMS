import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.routers import ai, auth, decisions, errors, evidence, lookups, rebuttals, reports
from app.core.config import get_settings
from app.core.exceptions import QEMSError
from app.core.middleware import RateLimitMiddleware, RequestLoggingMiddleware

settings = get_settings()
logger = logging.getLogger("qems.errors")

app = FastAPI(title="QEMS API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    limited_prefixes=("/api/v1/auth/login", "/api/v1/errors/") ,
    limit_per_minute=settings.login_rate_limit_per_minute,
)


@app.exception_handler(QEMSError)
async def qems_error_handler(_request: Request, exc: QEMSError) -> JSONResponse:
    """Global exception-handling middleware (Section 9.5) -> structured JSON errors."""
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


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


@app.get("/health")
async def health() -> dict[str, str]:
    """Health-check endpoint for orchestration (Section 5, Availability)."""
    return {"status": "ok"}
