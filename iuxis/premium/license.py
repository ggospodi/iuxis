"""
Premium license validation.
Validates an offline license key file at ~/.iuxis/license.key using HMAC-SHA256.
No network calls required — fully local-first.
"""

import functools
import hmac
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("iuxis.premium")

LICENSE_PATH = Path.home() / ".iuxis" / "license.key"
_SECRET_ENV = "IUXIS_LICENSE_SECRET"


def _compute_signature(data: dict) -> str:
    """Recompute expected HMAC-SHA256 signature from license fields."""
    secret = os.environ.get(_SECRET_ENV, "")
    if not secret:
        return ""
    payload = "|".join([
        data.get("email", ""),
        data.get("license_key", ""),
        data.get("plan", ""),
        data.get("issued_at", ""),
        data.get("expires_at", ""),
    ])
    return hmac.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


def is_premium() -> bool:
    """
    Check if premium features are licensed.

    Reads ~/.iuxis/license.key (JSON), validates:
      1. File exists and is valid JSON
      2. License has not expired
      3. HMAC-SHA256 signature matches (requires IUXIS_LICENSE_SECRET env var)

    Returns True if all checks pass, False otherwise.
    """
    if not LICENSE_PATH.exists():
        logger.debug("[Premium] No license file found at %s", LICENSE_PATH)
        return False

    try:
        data = json.loads(LICENSE_PATH.read_text().strip())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("[Premium] Failed to read license file: %s", e)
        return False

    # Check expiry
    expires_raw = data.get("expires_at", "")
    if not expires_raw:
        logger.warning("[Premium] License missing expires_at field")
        return False

    try:
        expires = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expires:
            logger.info("[Premium] License expired on %s", expires_raw)
            return False
    except ValueError:
        logger.warning("[Premium] Invalid expires_at format: %s", expires_raw)
        return False

    # Validate HMAC signature
    secret = os.environ.get(_SECRET_ENV, "")
    if not secret:
        logger.warning("[Premium] %s env var not set — cannot validate", _SECRET_ENV)
        return False

    expected = _compute_signature(data)
    provided = data.get("signature", "")
    if not hmac.compare_digest(expected, provided):
        logger.warning("[Premium] Invalid license signature")
        return False

    logger.debug("[Premium] License valid — plan=%s, expires=%s",
                 data.get("plan", "unknown"), expires_raw)
    return True


def require_premium(feature_name: str):
    """
    Decorator for premium features.
    Checks license and returns error dict if not licensed.
    Supports both sync and async functions.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not is_premium():
                logger.info("[Premium] Access denied for feature: %s", feature_name)
                return {
                    "error": "premium_required",
                    "feature": feature_name,
                    "message": f"'{feature_name}' requires Iuxis Premium. Visit iuxis.ai/pricing"
                }
            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not is_premium():
                logger.info("[Premium] Access denied for feature: %s", feature_name)
                return {
                    "error": "premium_required",
                    "feature": feature_name,
                    "message": f"'{feature_name}' requires Iuxis Premium. Visit iuxis.ai/pricing"
                }
            return await func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    return decorator
