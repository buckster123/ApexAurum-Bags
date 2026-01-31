"""
Rate limiter instance - extracted to avoid circular imports.

Both main.py and API endpoint modules import from here.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Rate limiter (in-memory for beta, can switch to Redis later)
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
