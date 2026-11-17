"""Route protection. Requirements 7.1, 7.4, 7.5, 7.6, 17.4.

``require_roles(*roles)`` is the only gate for non-public routes: 401 for a missing or invalid token
(raised by ``current_user``), 403 plus an ``access_denied`` audit event when the role is not allowed.
Public routes (no dependency): health, login, policy lookup, customer intake, customer status, demo.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.api.auth import ROLES, CurrentUser, current_user
from app.db import audit
from app.db.session import get_session

INVESTIGATE_ROLES = ROLES  # console read access: all four roles
ASSESS_ROLES = ("Investigator", "Fraud_Team", "Administrator")
ADMIN_ROLES = ("Administrator",)


def require_roles(*roles: str):
    """FastAPI dependency factory: returns the CurrentUser when their role is in ``roles``."""
    allowed = frozenset(roles)
    unknown = allowed - set(ROLES)
    if unknown:
        raise ValueError(f"Unknown role(s): {sorted(unknown)}")
    permission = "|".join(roles)[:64]

    def dependency(request: Request, user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in allowed:
            with get_session() as session:
                audit.log_denied(session, user.id, permission, entity_type="route",
                                 entity_id=f"{request.method} {request.url.path}"[:64])
            raise HTTPException(403, "You do not have permission to perform this action.")
        return user

    dependency.roles = tuple(roles)  # read by app.api.register_routers to document the route's role
    return dependency
