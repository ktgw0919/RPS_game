"""Application error type and REST exception handling.

REST responses use a `{code, message}` body where `code` is a shared
`ErrorCode` (ARCHITECTURE.md §3.1/§4.1). `AppError` carries the code plus the
HTTP status to return.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.models import ErrorCode, ErrorResponse

# Default HTTP status per error code for REST endpoints (ARCHITECTURE.md §3.1).
_DEFAULT_STATUS: dict[ErrorCode, int] = {
    ErrorCode.ROOM_NOT_FOUND: 404,
    ErrorCode.ROOM_FULL: 409,
    ErrorCode.ROOM_CLOSED: 410,
    ErrorCode.DISPLAY_NAME_INVALID: 422,
}


class AppError(Exception):
    """Domain error carrying a shared ErrorCode and an HTTP status."""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.message = message or code.value
        self.status_code = status_code or _DEFAULT_STATUS.get(code, 400)
        super().__init__(self.message)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        body = ErrorResponse(code=exc.code, message=exc.message)
        return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))
