"""
Public Error Reporting Endpoint

Accepts frontend error reports. Rate-limited, unauthenticated.
No PII accepted or stored.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.rate_limit import limiter
from app.services.error_tracking import log_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/errors", tags=["Errors"])


class FrontendErrorReport(BaseModel):
    error_type: str = Field(..., max_length=200)
    message: str = Field(..., max_length=2000)
    source: Optional[str] = Field(None, max_length=200)  # filename only, not full path
    line: Optional[int] = None
    column: Optional[int] = None
    page: Optional[str] = Field(None, max_length=300)  # URL path, not full URL


@router.post("/report")
@limiter.limit("10/minute")
async def report_frontend_error(
    request: Request,
    report: FrontendErrorReport,
    db: AsyncSession = Depends(get_db),
):
    """
    Report a frontend JavaScript error. Unauthenticated, rate-limited.

    No PII is accepted or stored. Source should be filename only.
    """
    context = {}
    if report.source:
        context["source"] = report.source
    if report.line is not None:
        context["line"] = report.line
    if report.column is not None:
        context["column"] = report.column
    if report.page:
        context["page"] = report.page

    await log_error(
        db=db,
        category="frontend_error",
        error_type=report.error_type,
        message=report.message,
        severity="error",
        context=context if context else None,
    )

    return {"status": "received"}
