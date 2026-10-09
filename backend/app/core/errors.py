"""The single error envelope: {"error": {"code", "message", "correlation_id", "details"}}."""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import correlation_id_var

log = structlog.get_logger()


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}


class ValidationFailed(AppError):
    status_code = 422
    code = "VALIDATION_FAILED"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"

    def __init__(self, message: str = "Not found.", **kw: Any) -> None:
        super().__init__(message, **kw)


class Unauthenticated(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"

    def __init__(self, message: str = "Log in to continue.", **kw: Any) -> None:
        super().__init__(message, **kw)


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"

    def __init__(self, message: str = "You don't have permission to do that.", **kw: Any) -> None:
        super().__init__(message, **kw)


class InvalidState(AppError):
    status_code = 409
    code = "INVALID_STATE"


class Conflict(AppError):
    status_code = 409


def envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": correlation_id_var.get(),
            "details": details or {},
        }
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(envelope(exc.code, exc.message, exc.details), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(p) for p in err.get("loc", ()) if p != "body"),
                "reason": err.get("msg", "invalid"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            envelope("VALIDATION_FAILED", "Some fields are invalid.", {"fields": fields}), 422
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHENTICATED"}.get(
            exc.status_code, "HTTP_ERROR"
        )
        return JSONResponse(envelope(code, str(exc.detail)), exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error_type=type(exc).__name__)
        return JSONResponse(envelope("INTERNAL_ERROR", "Something went wrong."), 500)
