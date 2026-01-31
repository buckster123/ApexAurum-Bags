"""
ApexAurum Cloud - Centralized Error Tracking Service

GDPR-compliant error logging with:
- PII sanitization (emails, tokens, passwords, UUIDs stripped)
- One-way user hashing (SHA-256 with server salt)
- No IP address storage
- Configurable auto-purge
- Admin toggle via SystemSettings
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.error_log import ErrorLog

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# Settings Cache (avoid DB hit on every error)
# ═══════════════════════════════════════════════════════════════════════════════

_settings_cache: Optional[dict] = None
_settings_cache_time: float = 0
_CACHE_TTL = 60  # seconds

DEFAULT_SETTINGS = {
    "enabled": True,
    "min_severity": "warning",  # warning, error, critical
    "retention_days": 30,
}

SEVERITY_ORDER = {"warning": 0, "error": 1, "critical": 2}

VALID_CATEGORIES = {
    "backend_exception", "http_error", "tool_failure",
    "frontend_error", "llm_error", "webhook_error",
}


async def get_tracking_settings(db: AsyncSession) -> dict:
    """Get error tracking settings with 60s cache."""
    global _settings_cache, _settings_cache_time

    now = time.time()
    if _settings_cache is not None and (now - _settings_cache_time) < _CACHE_TTL:
        return _settings_cache

    try:
        from app.models.system import SystemSettings
        result = await db.execute(
            select(SystemSettings).where(SystemSettings.key == "error_tracking")
        )
        row = result.scalar_one_or_none()
        settings = {**DEFAULT_SETTINGS, **(row.value if row else {})}
    except Exception:
        settings = DEFAULT_SETTINGS.copy()

    _settings_cache = settings
    _settings_cache_time = now
    return settings


def invalidate_settings_cache():
    """Force settings reload on next call."""
    global _settings_cache, _settings_cache_time
    _settings_cache = None
    _settings_cache_time = 0


# ═══════════════════════════════════════════════════════════════════════════════
# PII Sanitization
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns to strip from error messages
_EMAIL_RE = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
_TOKEN_RE = re.compile(r'(Bearer\s+|token[=:]\s*|api[_-]?key[=:]\s*)[A-Za-z0-9_.+/=-]{10,}', re.IGNORECASE)
_PASSWORD_RE = re.compile(r'(password|passwd|secret)[=:]\s*\S+', re.IGNORECASE)
_UUID_PATH_RE = re.compile(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE)
_LONG_HEX_RE = re.compile(r'[0-9a-f]{32,}', re.IGNORECASE)

# Keys forbidden in context dicts
_FORBIDDEN_CONTEXT_KEYS = {
    "email", "password", "passwd", "secret", "token",
    "api_key", "apikey", "authorization", "cookie",
    "ip", "ip_address", "remote_addr",
}


def sanitize_text(text: Optional[str]) -> Optional[str]:
    """Remove PII from error messages and stacktraces."""
    if not text:
        return text

    # Truncate very long messages
    if len(text) > 5000:
        text = text[:5000] + "...[truncated]"

    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _TOKEN_RE.sub("[TOKEN]", text)
    text = _PASSWORD_RE.sub("[REDACTED]", text)
    text = _UUID_PATH_RE.sub("/[UUID]", text)
    text = _LONG_HEX_RE.sub("[HEX]", text)
    return text


def sanitize_context(ctx: Optional[dict]) -> Optional[dict]:
    """Remove forbidden keys from context metadata."""
    if not ctx:
        return ctx

    return {
        k: v for k, v in ctx.items()
        if k.lower() not in _FORBIDDEN_CONTEXT_KEYS
    }


def anonymize_user_id(user_id) -> Optional[str]:
    """One-way hash of user_id with server salt. Returns None if no user_id."""
    if not user_id:
        return None
    from app.config import get_settings
    salt = get_settings().secret_key
    raw = f"{salt}:{user_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# Core: log_error()
# ═══════════════════════════════════════════════════════════════════════════════

async def log_error(
    db: AsyncSession,
    category: str,
    error_type: str,
    message: str,
    severity: str = "error",
    stacktrace: Optional[str] = None,
    endpoint: Optional[str] = None,
    http_method: Optional[str] = None,
    status_code: Optional[int] = None,
    response_time_ms: Optional[float] = None,
    user_id=None,
    context: Optional[dict] = None,
) -> Optional[ErrorLog]:
    """
    Log an error entry. Checks enabled status and severity filter.

    Returns the created ErrorLog or None if skipped.
    """
    try:
        # Check if tracking is enabled
        settings = await get_tracking_settings(db)
        if not settings.get("enabled", True):
            return None

        # Check minimum severity
        min_sev = settings.get("min_severity", "warning")
        if SEVERITY_ORDER.get(severity, 1) < SEVERITY_ORDER.get(min_sev, 0):
            return None

        # Validate category
        if category not in VALID_CATEGORIES:
            category = "backend_exception"

        # Sanitize everything
        entry = ErrorLog(
            category=category,
            severity=severity,
            error_type=str(error_type)[:200],
            message=sanitize_text(str(message)) or "Unknown error",
            stacktrace=sanitize_text(stacktrace),
            endpoint=str(endpoint)[:300] if endpoint else None,
            http_method=str(http_method)[:10] if http_method else None,
            status_code=status_code,
            response_time_ms=response_time_ms,
            user_hash=anonymize_user_id(user_id),
            context=sanitize_context(context),
        )

        db.add(entry)
        await db.commit()
        return entry

    except Exception as e:
        # Never let error tracking break the application
        logger.debug(f"Error tracking failed (non-fatal): {e}")
        try:
            await db.rollback()
        except Exception:
            pass
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Purge & Stats
# ═══════════════════════════════════════════════════════════════════════════════

async def purge_old_errors(db: AsyncSession, retention_days: Optional[int] = None) -> int:
    """Delete error logs older than retention period. Returns count deleted."""
    try:
        if retention_days is None:
            settings = await get_tracking_settings(db)
            retention_days = settings.get("retention_days", 30)

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await db.execute(
            delete(ErrorLog).where(ErrorLog.created_at < cutoff)
        )
        await db.commit()
        count = result.rowcount
        if count > 0:
            logger.info(f"Purged {count} error logs older than {retention_days} days")
        return count
    except Exception as e:
        logger.debug(f"Error purge failed (non-fatal): {e}")
        try:
            await db.rollback()
        except Exception:
            pass
        return 0


async def get_error_stats(db: AsyncSession, hours: int = 24) -> dict:
    """Get aggregated error statistics for the dashboard."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Total count
    total = await db.scalar(
        select(func.count(ErrorLog.id)).where(ErrorLog.created_at >= since)
    ) or 0

    # By category
    cat_query = await db.execute(
        select(ErrorLog.category, func.count(ErrorLog.id))
        .where(ErrorLog.created_at >= since)
        .group_by(ErrorLog.category)
    )
    by_category = {cat: count for cat, count in cat_query.fetchall()}

    # By severity
    sev_query = await db.execute(
        select(ErrorLog.severity, func.count(ErrorLog.id))
        .where(ErrorLog.created_at >= since)
        .group_by(ErrorLog.severity)
    )
    by_severity = {sev: count for sev, count in sev_query.fetchall()}

    # Top endpoints
    ep_query = await db.execute(
        select(ErrorLog.endpoint, func.count(ErrorLog.id))
        .where(and_(ErrorLog.created_at >= since, ErrorLog.endpoint.isnot(None)))
        .group_by(ErrorLog.endpoint)
        .order_by(func.count(ErrorLog.id).desc())
        .limit(10)
    )
    top_endpoints = [{"endpoint": ep, "count": count} for ep, count in ep_query.fetchall()]

    # Hourly trend (last 24h)
    from sqlalchemy import extract
    hourly_query = await db.execute(
        select(
            func.date_trunc('hour', ErrorLog.created_at).label('hour'),
            func.count(ErrorLog.id)
        )
        .where(ErrorLog.created_at >= since)
        .group_by('hour')
        .order_by('hour')
    )
    hourly_trend = [
        {"hour": h.isoformat() if h else None, "count": c}
        for h, c in hourly_query.fetchall()
    ]

    # Total in DB (all time)
    total_all = await db.scalar(select(func.count(ErrorLog.id))) or 0

    return {
        "total": total,
        "total_all_time": total_all,
        "hours": hours,
        "by_category": by_category,
        "by_severity": by_severity,
        "top_endpoints": top_endpoints,
        "hourly_trend": hourly_trend,
    }
