"""
Device Authentication Dependencies

Authenticates hardware devices (ApexPocket) using long-lived API tokens.
Device tokens use format: apex_dev_<32 hex chars>
Separate from JWT auth - used only by /api/v1/pocket/* endpoints.
"""

import logging
from datetime import datetime

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.auth.password import verify_password
from app.models.device import Device
from app.models.user import User

logger = logging.getLogger(__name__)

# Reuse the same HTTPBearer security scheme
security = HTTPBearer()

DEVICE_TOKEN_PREFIX = "apex_dev_"
DEVICE_TOKEN_PREFIX_LEN = 13  # "apex_dev_" (9) + 4 hex chars


async def get_device_and_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> tuple:
    """
    Authenticate a hardware device via Bearer token.

    Returns (Device, User) tuple.
    Raises 401 if token is invalid, revoked, or user not found.
    """
    token = credentials.credentials

    # Device tokens start with apex_dev_
    if not token.startswith(DEVICE_TOKEN_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid device token format")

    # Extract prefix for O(1) database lookup
    token_prefix = token[:DEVICE_TOKEN_PREFIX_LEN]

    # Find active devices matching this prefix
    result = await db.execute(
        select(Device)
        .where(Device.token_prefix == token_prefix)
        .where(Device.status == "active")
    )
    candidates = result.scalars().all()

    # Verify full token against hash (handles prefix collisions)
    for device in candidates:
        if verify_password(token, device.token_hash):
            # Update last seen
            device.last_seen_at = datetime.utcnow()
            await db.commit()

            # Load owner
            user_result = await db.execute(
                select(User).where(User.id == device.user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                logger.warning(f"Device {device.id} owner not found (user_id={device.user_id})")
                raise HTTPException(status_code=401, detail="Device owner not found")

            return device, user

    raise HTTPException(status_code=401, detail="Invalid or revoked device token")
