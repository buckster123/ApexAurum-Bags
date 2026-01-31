"""
Device Management Endpoints

CRUD operations for registered hardware devices (ApexPocket, etc.).
Uses JWT auth since these are accessed from the web UI.
"""

import json
import logging
import secrets
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.device import Device
from app.models.user import User
from app.auth.deps import get_current_user
from app.auth.password import hash_password

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Schemas ---

class DeviceCreateRequest(BaseModel):
    device_name: str
    device_type: str = "apex_pocket"

    @field_validator("device_name")
    @classmethod
    def validate_device_name(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 100:
            raise ValueError("Device name must be between 1 and 100 characters")
        return v


class DeviceUpdateRequest(BaseModel):
    device_name: Optional[str] = None

    @field_validator("device_name")
    @classmethod
    def validate_device_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v or len(v) > 100:
                raise ValueError("Device name must be between 1 and 100 characters")
        return v


class DeviceResponse(BaseModel):
    id: str
    device_name: str
    device_type: str
    status: str
    token_prefix: str
    soul_state: Optional[dict] = None
    last_seen_at: Optional[str] = None
    firmware_version: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class DeviceCreateResponse(BaseModel):
    id: str
    device_name: str
    device_type: str
    token: str
    token_prefix: str
    config_json: str
    created_at: str

    class Config:
        from_attributes = True


class DeviceRotateResponse(BaseModel):
    id: str
    token: str
    token_prefix: str
    config_json: str

    class Config:
        from_attributes = True


# --- Helpers ---

def _generate_device_token() -> str:
    """Generate a device API token: apex_dev_ + 32 hex chars = 41 chars total."""
    return "apex_dev_" + secrets.token_hex(16)


def _build_config_json(device_id: str, token: str) -> str:
    """Build the device configuration JSON string."""
    config = {
        "cloud_url": "https://backend-production-507c.up.railway.app",
        "device_token": token,
        "device_id": device_id,
        "api_version": "v1",
    }
    return json.dumps(config, indent=2)


def _device_to_response(device: Device) -> DeviceResponse:
    """Convert a Device model to a DeviceResponse."""
    return DeviceResponse(
        id=str(device.id),
        device_name=device.device_name,
        device_type=device.device_type,
        status=device.status,
        token_prefix=device.token_prefix,
        soul_state=device.soul_state,
        last_seen_at=device.last_seen_at.isoformat() if device.last_seen_at else None,
        firmware_version=device.firmware_version,
        created_at=device.created_at.isoformat(),
    )


async def _get_user_device(
    device_id: str, user: User, db: AsyncSession
) -> Device:
    """Fetch a device owned by the given user, or raise 404."""
    result = await db.execute(
        select(Device).where(Device.id == device_id, Device.user_id == user.id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )
    return device


# --- Endpoints ---

@router.get("/", response_model=list[DeviceResponse])
async def list_devices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all devices belonging to the current user."""
    result = await db.execute(
        select(Device)
        .where(Device.user_id == user.id)
        .order_by(Device.created_at.desc())
    )
    devices = result.scalars().all()

    return [_device_to_response(d) for d in devices]


@router.post("/", response_model=DeviceCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    request: DeviceCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new device.

    Returns the plaintext token exactly once. Store it securely --
    it cannot be retrieved again.
    """
    # Check device limit (max 5 per user)
    count_result = await db.execute(
        select(func.count()).select_from(Device).where(Device.user_id == user.id)
    )
    device_count = count_result.scalar()

    if device_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum of 5 devices per user",
        )

    # Generate token and hash it
    plaintext_token = _generate_device_token()
    token_hash = hash_password(plaintext_token)
    token_prefix = plaintext_token[:13]

    # Create device
    device = Device(
        user_id=user.id,
        device_name=request.device_name,
        device_type=request.device_type,
        token_hash=token_hash,
        token_prefix=token_prefix,
        status="active",
        soul_state={},
    )

    db.add(device)
    await db.commit()
    await db.refresh(device)

    device_id_str = str(device.id)
    config_json = _build_config_json(device_id_str, plaintext_token)

    logger.info(f"Device created: {device.device_name} ({device.device_type}) for user {user.id}")

    return DeviceCreateResponse(
        id=device_id_str,
        device_name=device.device_name,
        device_type=device.device_type,
        token=plaintext_token,
        token_prefix=token_prefix,
        config_json=config_json,
        created_at=device.created_at.isoformat(),
    )


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get details for a specific device."""
    device = await _get_user_device(device_id, user, db)
    return _device_to_response(device)


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    request: DeviceUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a device's name."""
    device = await _get_user_device(device_id, user, db)

    if request.device_name is not None:
        device.device_name = request.device_name

    await db.commit()
    await db.refresh(device)

    return _device_to_response(device)


@router.post("/{device_id}/revoke", response_model=DeviceResponse)
async def revoke_device(
    device_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Revoke a device's token.

    The device will receive 401 on its next API call.
    """
    device = await _get_user_device(device_id, user, db)

    device.status = "revoked"
    await db.commit()
    await db.refresh(device)

    logger.info(f"Device revoked: {device.device_name} (id={device.id})")

    return _device_to_response(device)


@router.post("/{device_id}/rotate", response_model=DeviceRotateResponse)
async def rotate_device_token(
    device_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Rotate a device's API token.

    Generates a new token and invalidates the old one.
    Returns the new plaintext token exactly once.
    """
    device = await _get_user_device(device_id, user, db)

    # Generate new token
    plaintext_token = _generate_device_token()
    device.token_hash = hash_password(plaintext_token)
    device.token_prefix = plaintext_token[:13]
    device.status = "active"

    await db.commit()
    await db.refresh(device)

    device_id_str = str(device.id)
    config_json = _build_config_json(device_id_str, plaintext_token)

    logger.info(f"Device token rotated: {device.device_name} (id={device.id})")

    return DeviceRotateResponse(
        id=device_id_str,
        token=plaintext_token,
        token_prefix=device.token_prefix,
        config_json=config_json,
    )


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a device."""
    device = await _get_user_device(device_id, user, db)

    await db.delete(device)
    await db.commit()

    logger.info(f"Device deleted: {device.device_name} (id={device.id})")
