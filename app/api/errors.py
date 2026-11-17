"""Uniform error envelope. Requirements 16.2, 16.3.

Every error response has the shape ``{"error": {"code", "message", "fields", "request_id"}}``.
``fields`` is a list of ``{"field", "message"}`` for 422 validation failures and empty otherwise.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_setup import current_request_id

_CODES = {400: "bad_request", 401: "unauthenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
          409: "conflict", 413: "payload_too_large", 422: "validation_error", 429: "rate_limited",
          500: "internal_error", 503: "unavailable"}


class FieldError(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    fields: list[FieldError] = []
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody


def error_code(status: int) -> str:
    return _CODES.get(status, "client_error" if status < 500 else "server_error")


def envelope(status: int, message: str, fields: list[dict] | None = None, headers: dict | None = None) -> JSONResponse:
    body = {"error": {"code": error_code(status), "message": message, "fields": fields or [],
                      "request_id": current_request_id()}}
    return JSONResponse(body, status_code=status, headers=headers)


def _field_name(loc: tuple) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header", "cookie")]
    return ".".join(parts) or ".".join(str(p) for p in loc)


async def _http_exception(_request: Request, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return envelope(exc.status_code, message, headers=getattr(exc, "headers", None))


async def _validation_error(_request: Request, exc: RequestValidationError):
    fields = [{"field": _field_name(tuple(e.get("loc", ()))), "message": str(e.get("msg", "Invalid value"))}
              for e in exc.errors()]
    names = ", ".join(dict.fromkeys(f["field"] for f in fields if f["field"]))
    return envelope(422, f"Invalid request: {names}." if names else "Invalid request.", fields)


async def _unhandled(_request: Request, _exc: Exception):
    return envelope(500, "Something went wrong. Please try again.")


def install(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(HTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)


# Documented on every route (Requirement 16.1): auth, permission, validation and rate-limit failures.
COMMON_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorEnvelope, "description": "Missing or invalid bearer token"},
    403: {"model": ErrorEnvelope, "description": "Role not permitted"},
    422: {"model": ErrorEnvelope, "description": "Validation failed; `fields` names the failing inputs"},
    429: {"model": ErrorEnvelope, "description": "Rate limit exceeded; see Retry-After"},
}
