"""Role matrix: every OpenAPI operation x {anonymous + four roles} against a declared permission table.

Requirements 7.1, 7.4, 7.5, 20.2.

PERMISSIONS is written out by hand (not derived from ``x-roles``) so that a route whose protection
changes, or a new route without an entry, fails this test.
"""
import re

import pytest

ALL = {"Investigator", "Ops_Manager", "Fraud_Team", "Administrator"}
ASSESS = {"Investigator", "Fraud_Team", "Administrator"}
PUBLIC = "public"

PERMISSIONS = {
    ("GET", "/api/health"): PUBLIC,
    ("POST", "/api/auth/login"): PUBLIC,
    ("POST", "/api/policies/lookup"): PUBLIC,
    ("POST", "/api/claims"): PUBLIC,
    ("GET", "/api/claims/{claim_id}/status"): PUBLIC,
    ("GET", "/api/demo/{kind}"): PUBLIC,
    ("GET", "/api/demo/{token}/{doc_type}.pdf"): PUBLIC,
    ("GET", "/api/me"): ALL,  # authenticated-only; documented as x-roles ["public"] (no role gate)
    ("GET", "/api/internal/overview"): ALL,
    ("GET", "/api/internal/claims"): ALL,
    ("GET", "/api/internal/claims/{claim_id}"): ALL,
    ("GET", "/api/internal/claims/{claim_id}/documents/{index}"): ALL,
    ("POST", "/api/internal/claims"): ASSESS,
    ("POST", "/api/assess"): ASSESS,
    ("POST", "/api/internal/reset"): {"Administrator"},
    ("GET", "/api/internal/settings"): ALL,
    ("GET", "/api/internal/claimants"): ALL,
    ("GET", "/api/internal/claimants/{claimant_id}"): ALL,
    ("POST", "/api/internal/settings/llm"): {"Administrator"},
    ("POST", "/api/findings/{finding_id}/feedback"): {"Investigator", "Fraud_Team"},
    ("POST", "/api/claims/{claim_id}/decisions"): {"Investigator", "Fraud_Team"},
}
# Routes with no role gate in code (x-roles == ["public"]) that still require a valid token.
AUTH_ONLY = {("GET", "/api/me")}

ROLE_PARAMS = ["anonymous", "Investigator", "Ops_Manager", "Fraud_Team", "Administrator"]
CASES = [(m, p, r) for (m, p) in sorted(PERMISSIONS) for r in ROLE_PARAMS]


def _operations():
    from app.main import app
    schema = app.openapi()
    return {(m.upper(), p): op for p, ops in schema["paths"].items() for m, op in ops.items()}


def test_table_covers_exactly_the_openapi_operations():
    ops = set(_operations())
    assert ops == set(PERMISSIONS), {"undeclared": sorted(ops - set(PERMISSIONS)),
                                     "stale": sorted(set(PERMISSIONS) - ops)}


def test_x_roles_matches_table():
    for key, op in _operations().items():
        expected = PERMISSIONS[key]
        if key in AUTH_ONLY or expected == PUBLIC:
            assert op["x-roles"] == [PUBLIC], key
        else:
            assert set(op["x-roles"]) == expected, key


@pytest.mark.parametrize("method,path,role", CASES)
def test_role_matrix(client, auth_headers, method, path, role):
    expected = PERMISSIONS[(method, path)]
    url = re.sub(r"\{[^}]+\}", "x", path)
    headers = {} if role == "anonymous" else auth_headers(role)
    kwargs = {"headers": headers}
    if method == "POST" and path in ("/api/internal/claims", "/api/assess", "/api/claims"):
        kwargs["data"] = {"payload" if path != "/api/assess" else "claim": "{}"}
    elif method == "POST":
        kwargs["json"] = {}

    status = client.request(method, url, **kwargs).status_code

    public = expected == PUBLIC
    if role == "anonymous":
        if public:
            assert status not in (401, 403), (method, path, status)
        else:
            assert status == 401, (method, path, status)
    elif public or role in expected:
        assert status not in (401, 403), (method, path, role, status)
    else:
        assert status == 403, (method, path, role, status)
