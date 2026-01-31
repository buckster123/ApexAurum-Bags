"""
Feedback Endpoints - Bug reports from beta testers.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.feedback import BugReport
from app.auth.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Feedback"])


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class BugReportRequest(BaseModel):
    category: str = Field(..., pattern="^(bug|feedback|question)$")
    description: str = Field(..., min_length=10, max_length=5000)
    page: Optional[str] = Field(None, max_length=200)
    browser_info: Optional[str] = Field(None, max_length=500)


class BugReportResponse(BaseModel):
    id: str
    category: str
    description: str
    page: Optional[str]
    status: str
    created_at: str

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════════════════════
# USER ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/feedback/report", response_model=BugReportResponse)
async def submit_report(
    request: BugReportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a bug report or feedback."""
    report = BugReport(
        user_id=user.id,
        category=request.category,
        description=request.description,
        page=request.page,
        browser_info=request.browser_info,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    logger.info(f"Bug report submitted by {user.email}: [{request.category}] {request.description[:80]}")

    return BugReportResponse(
        id=str(report.id),
        category=report.category,
        description=report.description,
        page=report.page,
        status=report.status,
        created_at=report.created_at.isoformat(),
    )
