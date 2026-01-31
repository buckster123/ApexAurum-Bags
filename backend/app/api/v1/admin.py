"""
Admin API Endpoints - User management, stats, and system controls.

All endpoints require is_admin=True on the authenticated user.
"""

import logging
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import text

from app.database import get_db
from app.models.user import User
from app.models.billing import Subscription, CreditBalance, Coupon
from app.models.feedback import BugReport
from app.models.conversation import Conversation, Message
from app.auth.deps import get_current_user
from app.services.llm_provider import get_available_providers, PROVIDER_MODELS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


# ═══════════════════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════════════════

class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: Optional[str]
    tier: str
    messages_used: int
    messages_limit: Optional[int]
    credit_balance: int
    is_admin: bool
    created_at: datetime


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int


class UpdateAdminRequest(BaseModel):
    is_admin: bool


class UpdateTierRequest(BaseModel):
    tier: str  # free, pro, opus


class TierGrantUpdate(BaseModel):
    tier: str
    grants: dict  # {"together": true, "groq": {"expires_at": "2026-03-01"}}


class UserGrantUpdate(BaseModel):
    provider: str
    enabled: bool = True
    expires_at: Optional[str] = None
    note: Optional[str] = None


class ProviderStatus(BaseModel):
    id: str
    name: str
    available: bool
    model_count: int


class StatsResponse(BaseModel):
    # Core
    total_users: int
    total_messages: int
    total_conversations: int
    active_coupons: int
    users_by_tier: dict
    # Features
    total_music_tasks: int
    music_by_status: dict
    total_council_sessions: int
    council_by_state: dict
    total_jam_sessions: int
    # Nursery
    total_nursery_datasets: int = 0
    total_nursery_jobs: int = 0
    nursery_jobs_by_status: dict = {}
    total_nursery_models: int = 0
    total_nursery_apprentices: int = 0
    # Storage
    total_vault_files: int
    total_vault_storage_mb: float
    total_neural_vectors: int
    # Providers
    providers: list[ProviderStatus]


# ═══════════════════════════════════════════════════════════════════════════════
# Admin Check Dependency
# ═══════════════════════════════════════════════════════════════════════════════

async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency that requires admin access."""
    if not getattr(user, 'is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


# ═══════════════════════════════════════════════════════════════════════════════
# User Management
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/users", response_model=UserListResponse)
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, max_length=200),
):
    """List all users with their subscription info."""
    query = select(User).order_by(User.created_at.desc())

    if search:
        query = query.where(User.email.ilike(f"%{search}%"))

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()

    # Get subscription and credit info for each user
    user_list = []
    for user in users:
        # Get subscription
        sub_result = await db.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        subscription = sub_result.scalar_one_or_none()

        # Get credit balance
        credit_result = await db.execute(
            select(CreditBalance).where(CreditBalance.user_id == user.id)
        )
        credit_balance = credit_result.scalar_one_or_none()

        user_list.append(UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            tier=subscription.tier if subscription else "free_trial",
            messages_used=subscription.messages_used if subscription else 0,
            messages_limit=subscription.messages_limit if subscription else 50,
            credit_balance=credit_balance.balance_cents if credit_balance else 0,
            is_admin=user.is_admin,
            created_at=user.created_at,
        ))

    # Get total count
    count_query = select(func.count(User.id))
    if search:
        count_query = count_query.where(User.email.ilike(f"%{search}%"))
    count_result = await db.execute(count_query)
    total = count_result.scalar()

    return UserListResponse(users=user_list, total=total)


@router.patch("/users/{user_id}/admin")
async def update_user_admin(
    user_id: UUID,
    request: UpdateAdminRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Toggle admin status for a user."""
    # Prevent self-demotion
    if user_id == admin.id and not request.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove your own admin status"
        )

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_admin = request.is_admin
    await db.commit()

    logger.info(f"Admin {admin.email} set is_admin={request.is_admin} for user {user.email}")

    return {"status": "updated", "user_id": str(user_id), "is_admin": request.is_admin}


@router.patch("/users/{user_id}/tier")
async def update_user_tier(
    user_id: UUID,
    request: UpdateTierRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Change a user's subscription tier (admin override)."""
    if request.tier not in ["free_trial", "seeker", "adept", "opus", "azothic"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tier must be 'free_trial', 'seeker', 'adept', 'opus', or 'azothic'"
        )

    # Get or create subscription
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        # Create subscription for user
        from uuid import uuid4
        subscription = Subscription(
            user_id=user_id,
            stripe_customer_id=f"admin_override_{uuid4().hex[:8]}",
            tier=request.tier,
            status="active",
        )
        db.add(subscription)
    else:
        subscription.tier = request.tier

    # Update message limits based on tier
    from app.config import TIER_LIMITS
    tier_config = TIER_LIMITS.get(request.tier, TIER_LIMITS["free_trial"])
    subscription.messages_limit = tier_config["messages_per_month"]

    await db.commit()

    logger.info(f"Admin {admin.email} set tier={request.tier} for user {user_id}")

    return {"status": "updated", "user_id": str(user_id), "tier": request.tier}


@router.get("/users/{user_id}/usage")
async def get_user_usage(
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed usage summary for a specific user (admin only)."""
    from app.services.usage import UsageService, FeatureCreditService, get_current_period
    from app.config import TIER_LIMITS

    # Get user's tier
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )
    subscription = result.scalar_one_or_none()
    tier = subscription.tier if subscription else "free_trial"
    tier_config = TIER_LIMITS.get(tier, TIER_LIMITS["free_trial"])

    # Get usage counters
    usage_svc = UsageService(db)
    counters = await usage_svc.get_usage_summary(user_id)

    # Get feature credits
    credit_svc = FeatureCreditService(db)
    feature_credits = await credit_svc.get_credit_summary(user_id)

    return {
        "user_id": str(user_id),
        "tier": tier,
        "period": get_current_period(),
        "counters": counters,
        "feature_credits": feature_credits,
        "tier_limits": {
            "messages_per_month": tier_config.get("messages_per_month"),
            "opus_messages_per_month": tier_config.get("opus_messages_per_month"),
            "council_sessions_per_month": tier_config.get("council_sessions_per_month"),
            "suno_generations_per_month": tier_config.get("suno_generations_per_month"),
            "jam_sessions_per_month": tier_config.get("jam_sessions_per_month"),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Stats
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get system-wide statistics including all platform features."""
    # --- Core counts ---
    user_count = await db.execute(select(func.count(User.id)))
    total_users = user_count.scalar() or 0

    try:
        msg_count = await db.execute(select(func.count(Message.id)))
        total_messages = msg_count.scalar() or 0
    except Exception:
        total_messages = 0

    try:
        conv_count = await db.execute(select(func.count(Conversation.id)))
        total_conversations = conv_count.scalar() or 0
    except Exception:
        total_conversations = 0

    coupon_count = await db.execute(
        select(func.count(Coupon.id)).where(Coupon.is_active == True)
    )
    active_coupons = coupon_count.scalar() or 0

    # --- Users by tier ---
    tier_query = await db.execute(
        select(Subscription.tier, func.count(Subscription.id))
        .group_by(Subscription.tier)
    )
    tier_results = tier_query.fetchall()

    users_by_tier = {"Free Trial": 0, "Seeker": 0, "Adept": 0, "Opus": 0, "Azothic": 0}
    tier_names = {"free_trial": "Free Trial", "seeker": "Seeker", "adept": "Adept", "opus": "Opus", "azothic": "Azothic"}

    for tier, count in tier_results:
        name = tier_names.get(tier, tier)
        if name in users_by_tier:
            users_by_tier[name] = count

    users_with_sub = sum(users_by_tier.values())
    users_by_tier["Free Trial"] += total_users - users_with_sub

    # --- Music tasks ---
    total_music_tasks = 0
    music_by_status = {}
    try:
        from app.models.music import MusicTask
        music_count = await db.execute(select(func.count(MusicTask.id)))
        total_music_tasks = music_count.scalar() or 0

        music_status_query = await db.execute(
            select(MusicTask.status, func.count(MusicTask.id))
            .group_by(MusicTask.status)
        )
        music_by_status = {s: c for s, c in music_status_query.fetchall()}
    except Exception as e:
        logger.debug(f"Music stats unavailable: {e}")

    # --- Council sessions ---
    total_council_sessions = 0
    council_by_state = {}
    try:
        from app.models.council import DeliberationSession
        council_count = await db.execute(select(func.count(DeliberationSession.id)))
        total_council_sessions = council_count.scalar() or 0

        council_state_query = await db.execute(
            select(DeliberationSession.state, func.count(DeliberationSession.id))
            .group_by(DeliberationSession.state)
        )
        council_by_state = {s: c for s, c in council_state_query.fetchall()}
    except Exception as e:
        logger.debug(f"Council stats unavailable: {e}")

    # --- Jam sessions ---
    total_jam_sessions = 0
    try:
        from app.models.jam import JamSession
        jam_count = await db.execute(select(func.count(JamSession.id)))
        total_jam_sessions = jam_count.scalar() or 0
    except Exception as e:
        logger.debug(f"Jam stats unavailable: {e}")

    # --- Nursery ---
    total_nursery_datasets = 0
    total_nursery_jobs = 0
    nursery_jobs_by_status = {}
    total_nursery_models = 0
    total_nursery_apprentices = 0
    try:
        from app.models.nursery import NurseryDataset, NurseryTrainingJob, NurseryModelRecord, NurseryApprentice

        ds_count = await db.execute(select(func.count(NurseryDataset.id)))
        total_nursery_datasets = ds_count.scalar() or 0

        job_count = await db.execute(select(func.count(NurseryTrainingJob.id)))
        total_nursery_jobs = job_count.scalar() or 0

        # Jobs by status breakdown
        job_status_query = await db.execute(
            select(NurseryTrainingJob.status, func.count(NurseryTrainingJob.id))
            .group_by(NurseryTrainingJob.status)
        )
        nursery_jobs_by_status = {status: count for status, count in job_status_query.fetchall()}

        model_count = await db.execute(select(func.count(NurseryModelRecord.id)))
        total_nursery_models = model_count.scalar() or 0

        ap_count = await db.execute(select(func.count(NurseryApprentice.id)))
        total_nursery_apprentices = ap_count.scalar() or 0
    except Exception as e:
        logger.debug(f"Nursery stats unavailable: {e}")

    # --- Vault (files) ---
    total_vault_files = 0
    total_vault_storage_mb = 0.0
    try:
        from app.models.file import File
        file_count = await db.execute(select(func.count(File.id)))
        total_vault_files = file_count.scalar() or 0

        storage_result = await db.execute(select(func.coalesce(func.sum(File.size_bytes), 0)))
        total_bytes = storage_result.scalar() or 0
        total_vault_storage_mb = round(total_bytes / (1024 * 1024), 1)
    except Exception as e:
        logger.debug(f"Vault stats unavailable: {e}")

    # --- Neural vectors (raw SQL - pgvector table) ---
    total_neural_vectors = 0
    try:
        vector_result = await db.execute(text("SELECT COUNT(*) FROM user_vectors"))
        total_neural_vectors = vector_result.scalar() or 0
    except Exception as e:
        logger.debug(f"Neural vector stats unavailable: {e}")

    # --- Provider status ---
    providers_raw = get_available_providers()
    providers = [
        ProviderStatus(
            id=p["id"],
            name=p["name"],
            available=p["available"],
            model_count=len(PROVIDER_MODELS.get(p["id"], {})),
        )
        for p in providers_raw
    ]

    return StatsResponse(
        total_users=total_users,
        total_messages=total_messages,
        total_conversations=total_conversations,
        active_coupons=active_coupons,
        users_by_tier=users_by_tier,
        total_music_tasks=total_music_tasks,
        music_by_status=music_by_status,
        total_council_sessions=total_council_sessions,
        council_by_state=council_by_state,
        total_jam_sessions=total_jam_sessions,
        total_nursery_datasets=total_nursery_datasets,
        total_nursery_jobs=total_nursery_jobs,
        nursery_jobs_by_status=nursery_jobs_by_status,
        total_nursery_models=total_nursery_models,
        total_nursery_apprentices=total_nursery_apprentices,
        total_vault_files=total_vault_files,
        total_vault_storage_mb=total_vault_storage_mb,
        total_neural_vectors=total_neural_vectors,
        providers=providers,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# BUG REPORTS
# ═══════════════════════════════════════════════════════════════════════════════

class AdminReportResponse(BaseModel):
    id: str
    user_email: str
    category: str
    page: Optional[str] = None
    description: str
    browser_info: Optional[str] = None
    status: str
    admin_notes: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class AdminReportListResponse(BaseModel):
    reports: list[AdminReportResponse]
    total: int


class UpdateReportRequest(BaseModel):
    status: Optional[str] = Field(None, pattern="^(open|acknowledged|resolved|closed)$")
    admin_notes: Optional[str] = Field(None, max_length=2000)


@router.get("/reports", response_model=AdminReportListResponse)
async def list_reports(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    status_filter: Optional[str] = Query(None, alias="status", max_length=20),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List bug reports with optional status filter."""
    query = select(BugReport).order_by(BugReport.created_at.desc())

    if status_filter:
        query = query.where(BugReport.status == status_filter)

    # Get total count
    count_query = select(func.count(BugReport.id))
    if status_filter:
        count_query = count_query.where(BugReport.status == status_filter)
    total = await db.scalar(count_query) or 0

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    reports = result.scalars().all()

    # Fetch user emails
    user_ids = [r.user_id for r in reports]
    users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
    users_map = {u.id: u.email for u in users_result.scalars().all()}

    return AdminReportListResponse(
        reports=[
            AdminReportResponse(
                id=str(r.id),
                user_email=users_map.get(r.user_id, "unknown"),
                category=r.category,
                page=r.page,
                description=r.description,
                browser_info=r.browser_info,
                status=r.status,
                admin_notes=r.admin_notes,
                created_at=r.created_at.isoformat(),
                updated_at=r.updated_at.isoformat() if r.updated_at else None,
            )
            for r in reports
        ],
        total=total,
    )


@router.patch("/reports/{report_id}")
async def update_report(
    report_id: UUID,
    request: UpdateReportRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a bug report's status or admin notes."""
    from datetime import timezone

    result = await db.execute(select(BugReport).where(BugReport.id == report_id))
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if request.status is not None:
        report.status = request.status
    if request.admin_notes is not None:
        report.admin_notes = request.admin_notes

    report.updated_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(f"Report {report_id} updated by {admin.email}: status={report.status}")

    return {"success": True, "status": report.status}


# ═══════════════════════════════════════════════════════════════════════════════
# PLATFORM GRANTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/grants")
async def get_platform_grants(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all platform provider grants."""
    from app.models.system import SystemSettings
    from app.config import GRANTABLE_PROVIDERS

    # Tier-level grants from system_settings
    result = await db.execute(
        select(SystemSettings).where(SystemSettings.key == "platform_tier_grants")
    )
    row = result.scalar_one_or_none()
    tier_grants = row.value if row else {}

    # User-level grants: find users with platform_grants in settings
    # Use ORM query to avoid json/jsonb type issues with raw SQL
    all_users = await db.execute(select(User))
    user_grants = []
    for user_row in all_users.scalars():
        if user_row.settings and isinstance(user_row.settings.get("platform_grants"), dict):
            grants = user_row.settings["platform_grants"]
            if grants:  # non-empty
                user_grants.append({
                    "user_id": str(user_row.id),
                    "email": user_row.email,
                    "display_name": user_row.display_name,
                    "grants": grants,
                })

    return {
        "grantable_providers": GRANTABLE_PROVIDERS,
        "tier_grants": tier_grants,
        "user_grants": user_grants,
    }


@router.put("/grants/tier")
async def set_tier_grants(
    request: TierGrantUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Set platform grants for a tier (full replace for that tier)."""
    from app.models.system import SystemSettings
    from app.config import TIER_LIMITS, GRANTABLE_PROVIDERS
    from app.services.provider_access import invalidate_tier_grants_cache

    # Validate tier
    if request.tier not in TIER_LIMITS:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {request.tier}")

    # Validate providers in grants
    for provider in request.grants:
        if provider not in GRANTABLE_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}")

    # Upsert system_settings row
    result = await db.execute(
        select(SystemSettings).where(SystemSettings.key == "platform_tier_grants")
    )
    settings_row = result.scalar_one_or_none()

    if settings_row:
        current = settings_row.value or {}
        current[request.tier] = request.grants
        settings_row.value = current
        settings_row.updated_at = datetime.now(timezone.utc)
        settings_row.updated_by = admin.id
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(settings_row, "value")
    else:
        settings_row = SystemSettings(
            key="platform_tier_grants",
            value={request.tier: request.grants},
            updated_at=datetime.now(timezone.utc),
            updated_by=admin.id,
        )
        db.add(settings_row)

    await db.commit()
    invalidate_tier_grants_cache()

    return {"status": "ok", "tier": request.tier, "grants": request.grants}


@router.put("/grants/user/{user_id}")
async def set_user_grant(
    user_id: UUID,
    request: UserGrantUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Grant or update a user's platform access to a provider."""
    from app.config import GRANTABLE_PROVIDERS

    if request.provider not in GRANTABLE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {request.provider}")

    # Find user
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update settings
    if not target_user.settings:
        target_user.settings = {}
    if "platform_grants" not in target_user.settings:
        target_user.settings["platform_grants"] = {}

    if request.enabled:
        grant_value = True
        if request.expires_at or request.note:
            grant_value = {}
            if request.expires_at:
                grant_value["expires_at"] = request.expires_at
            if request.note:
                grant_value["note"] = request.note
            grant_value["granted_by"] = str(admin.id)
            grant_value["granted_at"] = datetime.now(timezone.utc).isoformat()
        target_user.settings["platform_grants"][request.provider] = grant_value
    else:
        target_user.settings["platform_grants"].pop(request.provider, None)

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(target_user, "settings")
    await db.commit()

    return {
        "status": "ok",
        "user_id": str(user_id),
        "provider": request.provider,
        "enabled": request.enabled,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ERROR TRACKING
# ═══════════════════════════════════════════════════════════════════════════════

class ErrorLogResponse(BaseModel):
    id: str
    category: str
    severity: str
    error_type: str
    message: str
    stacktrace: Optional[str] = None
    endpoint: Optional[str] = None
    http_method: Optional[str] = None
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    user_hash: Optional[str] = None
    context: Optional[dict] = None
    created_at: str


class ErrorListResponse(BaseModel):
    errors: list[ErrorLogResponse]
    total: int


class ErrorSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    min_severity: Optional[str] = Field(None, pattern="^(warning|error|critical)$")
    retention_days: Optional[int] = Field(None, ge=1, le=365)


@router.get("/errors", response_model=ErrorListResponse)
async def list_errors(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    category: Optional[str] = Query(None, max_length=30),
    severity: Optional[str] = Query(None, max_length=10),
    endpoint: Optional[str] = Query(None, max_length=300),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List error logs with filters."""
    from datetime import timedelta
    from app.models.error_log import ErrorLog

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = select(ErrorLog).where(ErrorLog.created_at >= since)

    if category:
        query = query.where(ErrorLog.category == category)
    if severity:
        query = query.where(ErrorLog.severity == severity)
    if endpoint:
        query = query.where(ErrorLog.endpoint.ilike(f"%{endpoint}%"))

    # Count
    count_query = select(func.count(ErrorLog.id)).where(ErrorLog.created_at >= since)
    if category:
        count_query = count_query.where(ErrorLog.category == category)
    if severity:
        count_query = count_query.where(ErrorLog.severity == severity)
    if endpoint:
        count_query = count_query.where(ErrorLog.endpoint.ilike(f"%{endpoint}%"))
    total = await db.scalar(count_query) or 0

    query = query.order_by(ErrorLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    errors = result.scalars().all()

    return ErrorListResponse(
        errors=[
            ErrorLogResponse(
                id=str(e.id),
                category=e.category,
                severity=e.severity,
                error_type=e.error_type,
                message=e.message,
                stacktrace=e.stacktrace,
                endpoint=e.endpoint,
                http_method=e.http_method,
                status_code=e.status_code,
                response_time_ms=e.response_time_ms,
                user_hash=e.user_hash,
                context=e.context,
                created_at=e.created_at.isoformat(),
            )
            for e in errors
        ],
        total=total,
    )


@router.get("/errors/stats")
async def get_error_stats_endpoint(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    hours: int = Query(24, ge=1, le=720),
):
    """Get aggregated error statistics."""
    from app.services.error_tracking import get_error_stats
    return await get_error_stats(db, hours)


@router.get("/errors/settings")
async def get_error_settings(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get current error tracking settings."""
    from app.services.error_tracking import get_tracking_settings
    return await get_tracking_settings(db)


@router.put("/errors/settings")
async def update_error_settings(
    request: ErrorSettingsRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update error tracking settings."""
    from app.models.system import SystemSettings
    from app.services.error_tracking import get_tracking_settings, invalidate_settings_cache

    # Get current
    current = await get_tracking_settings(db)

    # Merge updates
    if request.enabled is not None:
        current["enabled"] = request.enabled
    if request.min_severity is not None:
        current["min_severity"] = request.min_severity
    if request.retention_days is not None:
        current["retention_days"] = request.retention_days

    # Upsert
    result = await db.execute(
        select(SystemSettings).where(SystemSettings.key == "error_tracking")
    )
    row = result.scalar_one_or_none()

    if row:
        row.value = current
        row.updated_at = datetime.now(timezone.utc)
        row.updated_by = admin.id
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(row, "value")
    else:
        row = SystemSettings(
            key="error_tracking",
            value=current,
            updated_at=datetime.now(timezone.utc),
            updated_by=admin.id,
        )
        db.add(row)

    await db.commit()
    invalidate_settings_cache()

    logger.info(f"Error tracking settings updated by {admin.email}: {current}")
    return current


@router.delete("/errors/purge")
async def purge_errors(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    confirm: bool = Query(False),
):
    """Manually purge error logs. Requires confirm=true."""
    if not confirm:
        from app.models.error_log import ErrorLog
        total = await db.scalar(select(func.count(ErrorLog.id))) or 0
        return {"warning": "Add ?confirm=true to purge", "total_records": total}

    from app.services.error_tracking import purge_old_errors
    deleted = await purge_old_errors(db, retention_days=0)
    logger.info(f"Error logs purged by {admin.email}: {deleted} entries deleted")
    return {"status": "purged", "deleted": deleted}


@router.get("/errors/export")
async def export_errors(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    format: str = Query("json", pattern="^(json|csv)$"),
    hours: int = Query(24, ge=1, le=720),
    category: Optional[str] = Query(None, max_length=30),
    severity: Optional[str] = Query(None, max_length=10),
):
    """Export error logs as JSON or CSV (up to 5000 records)."""
    from datetime import timedelta
    from app.models.error_log import ErrorLog

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = select(ErrorLog).where(ErrorLog.created_at >= since)

    if category:
        query = query.where(ErrorLog.category == category)
    if severity:
        query = query.where(ErrorLog.severity == severity)

    query = query.order_by(ErrorLog.created_at.desc()).limit(5000)
    result = await db.execute(query)
    errors = result.scalars().all()

    records = [
        {
            "id": str(e.id),
            "category": e.category,
            "severity": e.severity,
            "error_type": e.error_type,
            "message": e.message,
            "endpoint": e.endpoint,
            "http_method": e.http_method,
            "status_code": e.status_code,
            "response_time_ms": e.response_time_ms,
            "user_hash": e.user_hash,
            "context": e.context,
            "created_at": e.created_at.isoformat(),
        }
        for e in errors
    ]

    if format == "csv":
        import csv
        import io
        from fastapi.responses import StreamingResponse

        output = io.StringIO()
        if records:
            writer = csv.DictWriter(output, fieldnames=records[0].keys())
            writer.writeheader()
            for r in records:
                # Flatten context to string for CSV
                r["context"] = str(r["context"]) if r["context"] else ""
                writer.writerow(r)

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=error_logs.csv"},
        )

    return {"errors": records, "count": len(records)}


@router.delete("/grants/user/{user_id}/{provider}")
async def revoke_user_grant(
    user_id: UUID,
    provider: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a user's platform grant for a specific provider."""
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if target_user.settings and "platform_grants" in target_user.settings:
        target_user.settings["platform_grants"].pop(provider, None)
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(target_user, "settings")
        await db.commit()

    return {"status": "ok", "user_id": str(user_id), "provider": provider, "revoked": True}
