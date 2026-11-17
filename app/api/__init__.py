"""HTTP API layer: authentication, RBAC, error envelope and routers.

``register_routers(app)`` imports every module in this package that defines a module-level ``router``
(in alphabetical order, so route precedence is deterministic) and includes it. Every route is given the
common 401/403/422/429 responses and an ``x-roles`` OpenAPI extension naming the roles allowed to call it.
"""
from __future__ import annotations

import importlib
import pkgutil

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.errors import COMMON_RESPONSES

_NOT_ROUTERS = {"deps", "errors", "schemas", "common"}


def _roles_of(dependant) -> tuple[str, ...] | None:
    roles = getattr(dependant.call, "roles", None)
    if roles:
        return tuple(roles)
    for sub in dependant.dependencies:
        found = _roles_of(sub)
        if found:
            return found
    return None


def _document(router) -> None:
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        route.responses = {**COMMON_RESPONSES, **route.responses}
        roles = _roles_of(route.dependant)
        route.openapi_extra = {**(route.openapi_extra or {}), "x-roles": list(roles) if roles else ["public"]}


def register_routers(app: FastAPI) -> list[str]:
    registered = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if info.name in _NOT_ROUTERS:
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        router = getattr(module, "router", None)
        if router is None:
            continue
        _document(router)
        app.include_router(router)
        registered.append(info.name)
    return registered
