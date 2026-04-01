"""
Premium license validation.
CURRENT STATE: Stub — always returns True (development mode).
TODO: Wire to real Lemon Squeezy key validation before public launch.
"""

import functools
import logging

logger = logging.getLogger("iuxis.premium")

# STUB: Set to False to test premium gates during development
_STUB_PREMIUM_ENABLED = True


def is_premium() -> bool:
    """Check if premium features are licensed. Currently stubbed to True."""
    if _STUB_PREMIUM_ENABLED:
        return True
    # TODO: Real key validation
    # import os, json
    # key_path = os.path.expanduser("~/.iuxis/license.key")
    # if not os.path.exists(key_path): return False
    # with open(key_path) as f: data = json.load(f)
    # return validate_key(data)
    return False


def require_premium(feature_name: str):
    """
    Decorator for premium features.
    In stub mode: always passes through.
    In production: checks license and returns error dict if not licensed.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not is_premium():
                logger.info(f"[Premium] Access denied for feature: {feature_name}")
                return {
                    "error": "premium_required",
                    "feature": feature_name,
                    "message": f"'{feature_name}' requires Iuxis Premium. Visit iuxis.ai/pricing"
                }
            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not is_premium():
                logger.info(f"[Premium] Access denied for feature: {feature_name}")
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
