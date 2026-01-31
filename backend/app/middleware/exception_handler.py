"""Exception handler middleware for structured error responses."""

import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from ..exceptions import IsoException

logger = logging.getLogger(__name__)


async def iso_exception_handler(request: Request, exc: IsoException) -> JSONResponse:
    """
    Handle custom exceptions and return structured JSON responses.

    Logs error details and converts exception to standardized JSON format.

    Args:
        request: FastAPI request object
        exc: IsoException instance

    Returns:
        JSONResponse with error details
    """
    logger.error(
        f"IsoException: {exc.error_code.value}",
        extra={
            "error_code": exc.error_code.value,
            "path": request.url.path,
            "method": request.method,
            "details": exc.details,
            "status_code": exc.status_code
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )
