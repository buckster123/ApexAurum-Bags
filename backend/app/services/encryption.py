"""
Encryption Service

Handles secure encryption/decryption of sensitive data like API keys.
Uses Fernet (symmetric encryption) with key derived from JWT_SECRET.
"""

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _derive_key(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from the JWT secret."""
    # SHA-256 produces exactly 32 bytes, perfect for Fernet
    return base64.urlsafe_b64encode(
        hashlib.sha256(secret.encode()).digest()
    )


def get_cipher(secret: str) -> Fernet:
    """Get a Fernet cipher instance for the given secret."""
    return Fernet(_derive_key(secret))


def encrypt_value(plaintext: str, secret: str) -> str:
    """
    Encrypt a string value.

    Args:
        plaintext: The value to encrypt
        secret: The secret key (JWT_SECRET)

    Returns:
        Base64-encoded encrypted string
    """
    cipher = get_cipher(secret)
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, secret: str) -> Optional[str]:
    """
    Decrypt an encrypted string value.

    Args:
        ciphertext: The encrypted value
        secret: The secret key (JWT_SECRET)

    Returns:
        Decrypted string, or None if decryption fails
    """
    try:
        cipher = get_cipher(secret)
        return cipher.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.warning("Failed to decrypt value - invalid token")
        return None
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        return None


def mask_api_key(key: str) -> str:
    """
    Create a masked version of an API key for display.

    Handles multiple provider key formats:
    - Anthropic: sk-ant-... -> sk-ant-...xxxx
    - Groq: gsk_... -> gsk_...xxxx
    - Generic sk-: sk-...xxxx
    - Other: ***...xxxx

    Args:
        key: The full API key

    Returns:
        Masked key showing only prefix and last 4 chars
    """
    if not key or len(key) < 10:
        return "****"

    suffix = key[-4:]

    if key.startswith("sk-ant"):
        return f"sk-ant-...{suffix}"
    elif key.startswith("gsk_"):
        return f"gsk_...{suffix}"
    elif key.startswith("sk-"):
        return f"sk-...{suffix}"
    else:
        return f"***...{suffix}"
