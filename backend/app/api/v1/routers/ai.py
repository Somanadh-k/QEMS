from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models import Category, Department, User
from app.repositories.error_repository import ErrorRepository
from app.schemas.ai import (
    NLSearchRequest,
    NLSearchResponse,
    ReportSummaryRequest,
    ReportSummaryResponse,
    RootCauseRequest,
    RootCauseResponse,
    SeverityPredictionRequest,
    SeverityPredictionResponse,
    SimilarErrorItem,
    SmartRecommendationRequest,
    SmartRecommendationResponse,
)
from app.services.ai_service import AIService, get_ai_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/root-cause", response_model=RootCauseResponse)
async def root_cause(
    payload: RootCauseRequest,
    db: AsyncSession = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
    _user: User = Depends(require_role("QA Reviewer", "Admin")),
):
    """Section 11.8 / 13.1 — Gemini in the original report, OpenAI here."""
    errors = ErrorRepository(db)
    error = await errors.get_by_id(payload.error_id)
    if error is None:
        raise NotFoundError(f"Error {payload.error_id} not found")

    similar_context = "(none found)"
    if error.description_embedding is not None:
        similar = await errors.find_similar_closed(error.description_embedding, exclude_error_id=error.error_id)
        if similar:
            similar_context = "\n".join(f"- {e.qa_error_code}: {e.title}" for e in similar)

    suggestion = await ai.root_cause_analysis(
        error_id=error.error_id,
        title=error.title,
        description=error.description,
        category=str(error.category_id),
        similar_context=similar_context,
    )
    return RootCauseResponse(**suggestion.content)


@router.get("/similar/{error_id}", response_model=list[SimilarErrorItem])
async def similar_errors(
    error_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("QA Reviewer", "Admin")),
):
    """Section 11.8 / 13.2 — top-N historically similar closed errors via embedding similarity."""
    errors = ErrorRepository(db)
    error = await errors.get_by_id(error_id)
    if error is None:
        raise NotFoundError(f"Error {error_id} not found")
    if error.description_embedding is None:
        return []

    similar = await errors.find_similar_closed(error.description_embedding, exclude_error_id=error_id)
    return [
        SimilarErrorItem(error_id=e.error_id, qa_error_code=e.qa_error_code, title=e.title, status=e.status)
        for e in similar
    ]


@router.post("/severity-prediction", response_model=SeverityPredictionResponse)
async def severity_prediction(
    payload: SeverityPredictionRequest,
    ai: AIService = Depends(get_ai_service),
    _user: User = Depends(get_current_user),
):
    """Section 13.3 — inspector may accept or override the suggestion."""
    suggestion = await ai.predict_severity(title=payload.title, description=payload.description)
    return SeverityPredictionResponse(**suggestion.content)


@router.post("/report-summary", response_model=ReportSummaryResponse)
async def report_summary(
    payload: ReportSummaryRequest,
    db: AsyncSession = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
    _user: User = Depends(require_role("QA Reviewer", "Admin", "Viewer")),
):
    """Section 13.4 — appended to exported reports (Section 11.7)."""
    errors = ErrorRepository(db)
    matched, _total = await errors.list(department_id=payload.department_id, page=1, page_size=100)
    errors_summary = "\n".join(f"- {e.qa_error_code} [{e.severity}] {e.title} ({e.status})" for e in matched)
    suggestion = await ai.summarize_report(
        date_from=payload.date_from, date_to=payload.date_to, errors_summary=errors_summary or "(no errors)"
    )
    return ReportSummaryResponse(**suggestion.content)


@router.post("/smart-recommendation", response_model=SmartRecommendationResponse)
async def smart_recommendation(
    payload: SmartRecommendationRequest,
    db: AsyncSession = Depends(get_db),
    ai: AIService = Depends(get_ai_service),
    _user: User = Depends(require_role("QA Reviewer", "Admin")),
):
    """Section 13.5 — likely owner/assignee + estimated SLA risk at creation time."""
    errors = ErrorRepository(db)
    history, _total = await errors.list(department_id=payload.department_id, page=1, page_size=50)
    history_summary = "\n".join(f"- {e.title} -> {e.status}" for e in history) or "(no history)"

    category = (
        await db.execute(select(Category).where(Category.category_id == payload.category_id))
    ).scalar_one_or_none()
    department = (
        await db.execute(select(Department).where(Department.department_id == payload.department_id))
    ).scalar_one_or_none()

    suggestion = await ai.recommend_assignee_and_sla_risk(
        category=category.name if category else "unknown",
        department=department.name if department else "unknown",
        history_summary=history_summary,
    )
    return SmartRecommendationResponse(**suggestion.content)


@router.post("/nl-search", response_model=NLSearchResponse)
async def nl_search(
    payload: NLSearchRequest,
    ai: AIService = Depends(get_ai_service),
    _user: User = Depends(get_current_user),
):
    """Section 13.6 — translates free text into structured filters for /api/v1/errors."""
    suggestion = await ai.nl_search_to_filters(query=payload.query)
    return NLSearchResponse(**suggestion.content)
