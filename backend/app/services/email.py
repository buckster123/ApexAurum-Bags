"""
Email Service - Stub implementation.

Currently logs all emails instead of sending. When SMTP is configured,
this will send actual emails via the configured SMTP server.
"""

import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_email(
    to: str,
    subject: str,
    body_html: str,
    from_address: Optional[str] = None,
) -> bool:
    """
    Send an email. Currently a stub that logs instead of sending.
    """
    settings = get_settings()
    sender = from_address or f"{settings.smtp_from_name} <{settings.smtp_from_address}>"

    logger.info(f"[EMAIL STUB] To: {to} | From: {sender} | Subject: {subject}")
    logger.debug(f"[EMAIL STUB] Body preview: {body_html[:200]}...")

    # When SMTP is configured, this will use aiosmtplib
    # if settings.smtp_host:
    #     ... actual SMTP sending ...

    return True


async def send_usage_warning(
    user_email: str,
    user_display_name: Optional[str],
    resource: str,
    percent: int,
    current: int,
    limit: int,
) -> bool:
    """
    Send a usage warning email when user hits 80% or 100% of a limit.
    """
    name = user_display_name or "Alchemist"

    resource_labels = {
        "messages": "messages",
        "messages_haiku": "Haiku messages",
        "messages_sonnet": "Sonnet messages",
        "messages_opus": "Opus messages",
        "suno_generations": "Suno music generations",
        "council_sessions": "Council sessions",
        "jam_sessions": "Jam sessions",
        "nursery_training_jobs": "training jobs",
    }
    resource_label = resource_labels.get(resource, resource)

    if percent >= 100:
        subject = f"ApexAurum: You've reached your {resource_label} limit"
        message = f"You've used all {limit} {resource_label} for this billing period."
        action = "Consider upgrading your tier or purchasing a feature credit pack for additional usage."
    else:
        subject = f"ApexAurum: {percent}% of your {resource_label} used"
        message = f"You've used {current} of {limit} {resource_label} this period ({percent}%)."
        action = "You can continue using the service until you reach your limit."

    body_html = f"""
    <div style="font-family: system-ui, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; background: #0a0a0f; color: #e5e7eb;">
        <div style="text-align: center; margin-bottom: 24px;">
            <span style="font-size: 36px; font-weight: bold; color: #d4af37; font-family: serif;">Au</span>
        </div>
        <h2 style="color: #d4af37; margin-bottom: 16px;">Usage Update</h2>
        <p>Hello {name},</p>
        <p>{message}</p>
        <p>{action}</p>
        <div style="margin: 24px 0; padding: 16px; background: #12121a; border: 1px solid #1e1e2e; border-radius: 8px;">
            <div style="font-size: 14px; color: #9ca3af;">
                {resource_label}: <strong style="color: #d4af37;">{current}/{limit}</strong>
            </div>
        </div>
        <p style="color: #6b7280; font-size: 12px; margin-top: 32px;">
            &mdash; The ApexAurum Team<br>
            <a href="https://frontend-production-5402.up.railway.app/billing" style="color: #d4af37;">Manage your subscription</a>
        </p>
    </div>
    """

    return await send_email(user_email, subject, body_html)
