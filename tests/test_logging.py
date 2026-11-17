"""Structured logging carries request id and no PII (Req 17.8)."""
import io
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.logging_setup import RequestContextMiddleware, configure_logging, get_logger, resolve_request_id

CLAIMANT = "Jane Q. Claimant"


def _client(buf):
    configure_logging(stream=buf)
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/x")
    def x():
        get_logger().info("claim_viewed", event_type="claim_access", claimant_name=CLAIMANT, text="doc body")
        return {"ok": True}

    return TestClient(app)


def test_log_has_request_id_and_no_pii():
    buf = io.StringIO()
    r = _client(buf).get("/x", headers={"X-Request-ID": "abc-12345678"})
    rec = json.loads(buf.getvalue().strip().splitlines()[-1])
    assert rec["request_id"] == "abc-12345678" == r.headers["x-request-id"]
    assert rec["event_type"] == "claim_access"
    assert CLAIMANT not in buf.getvalue() and "doc body" not in buf.getvalue()


def test_malformed_request_id_replaced():
    rid = resolve_request_id("bad id\n<script>")
    assert rid != "bad id\n<script>" and len(rid) == 36
