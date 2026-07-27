import functools
import traceback
import logging

from fastapi import HTTPException

from ..config import settings

logger = logging.getLogger(__name__)


def handle_errors(func):
    """Decorator to catch exceptions in async route handlers.

    Logs full traceback in all environments.
    In DEV: re-raises the exception (full traceback in response).
    In PROD: returns a clean HTTP 500 with the exception message.
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as e:
            tb = traceback.format_exc()
            logger.error("Unhandled error in %s:\n%s", func.__name__, tb)

            if settings.ENVIRONMENT.upper() == "DEV":
                raise
            else:
                detail_msg = str(e) if str(e) else "An internal error occurred."
                raise HTTPException(status_code=500, detail=detail_msg)

    return wrapper
