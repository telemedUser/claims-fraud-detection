"""Error envelope, route documentation and internal claim routes. Requirements 16.1, 16.2, 16.3, 18.1, 7.1."""
import pytest

from app import jobs


def test_422_envelope_names_failing_fields(client):
    r = client.post("/api/policies/lookup", json={"policy_number": "POL-1001", "date_of_birth": "not-a-date"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert set(err) == {"code", "message", "fields", "request_id"}
    assert err["code"] == "validation_error"
    assert any(f["field"] == "date_of_birth" for f in err["fields"])
    assert err["request_id"] == r.headers["X-Request-ID"]


def test_http_errors_use_envelope_with_empty_fields(client):
    for r in (client.get("/api/claims/CLM-NOPE/status"), client.get("/api/nope")):
        assert r.status_code == 404
        e = r.json()["error"]
        assert e["code"] == "not_found" and e["fields"] == [] and e["request_id"]


def test_every_route_documents_common_errors_and_role():
    from app.main import app
    schema = app.openapi()
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            assert {"401", "403", "422", "429"} <= set(op["responses"]), (method, path)
            assert op["x-roles"], (method, path)
    assert schema["paths"]["/api/internal/reset"]["post"]["x-roles"] == ["Administrator"]
    assert schema["paths"]["/api/claims"]["post"]["x-roles"] == ["public"]
    for p in ("/api/policies/lookup", "/api/claims/{claim_id}/status", "/api/demo/{kind}",
              "/api/internal/claims", "/api/internal/claims/{claim_id}"):
        assert p in schema["paths"]


@pytest.mark.parametrize("role", ["Investigator", "Ops_Manager"])
def test_internal_list_filters(client, auth_headers, role):
    h = auth_headers(role)
    assert client.get("/api/internal/claims?band=bogus", headers=h).status_code == 422
    assert client.get("/api/internal/claims?date_from=2030-01-02&date_to=2030-01-01", headers=h).status_code == 422
    r = client.get("/api/internal/claims?band=low&status=completed&provider=x&category=Cardiac&assignee=bob", headers=h)
    assert r.status_code == 200 and r.json() == []
    assert r.headers["X-Filters-Not-Applied"] == "assignee"


def test_internal_create_requires_assess_role_and_validates(client, auth_headers):
    assert client.post("/api/internal/claims", data={"payload": "{}"}).status_code == 401
    assert client.post("/api/internal/claims", data={"payload": "{}"}, headers=auth_headers("Ops_Manager")).status_code == 403
    r = client.post("/api/internal/claims", data={"payload": "{}"}, headers=auth_headers("Investigator"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_internal_detail_404(client, auth_headers):
    r = client.get("/api/internal/claims/CLM-NOPE", headers=auth_headers("Investigator"))
    assert r.status_code == 404 and r.json()["error"]["message"] == "Claim not found"
    assert jobs.JOBS.get("CLM-NOPE") is None
