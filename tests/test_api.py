"""API tests for submit, health, and appeal workflows.

Expected: the Flask API returns documented JSON shapes and status codes.
Unexpected: routes leaking internals, skipping audit IDs, or accepting appeals
that do not match the original creator.
"""

from provenance_guard.models import SignalOutput
from provenance_guard.signals.groq_signal_service import GroqSignalService


def test_health_endpoint_returns_ok(client):
    """Health should check SQLite only and return the documented shape."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["database"] == "reachable"


def test_submit_missing_creator_id_returns_400(client, valid_submit_request):
    """Missing creator_id is invalid and should not create an audit_id response."""
    request_json = dict(valid_submit_request)
    request_json.pop("creator_id")

    response = client.post("/api/v1/submit", json=request_json)

    assert response.status_code == 400
    assert response.json["error"]["code"] == "missing_creator_id"
    assert "audit_id" not in response.json


def test_submit_success_returns_structured_response(client, monkeypatch, valid_submit_request):
    """Valid submit should return the planned structured attribution response."""

    def fake_analyze(self, normalized_text, metadata, audit_context):
        return SignalOutput(
            name="groq_semantic",
            version="v1",
            status="completed",
            ai_likelihood=0.58,
            confidence=0.60,
            confidence_label="medium",
            raw_output={},
            explanation="fake",
            error=None,
        )

    monkeypatch.setattr(GroqSignalService, "analyze", fake_analyze)

    response = client.post("/api/v1/submit", json=valid_submit_request)

    assert response.status_code == 200
    assert response.json["audit_id"].startswith("audit_")
    assert response.json["creator_id"] == "user_123"
    assert response.json["attribution_result"] in {
        "likely_ai",
        "likely_human",
        "uncertain",
    }
    assert "transparency_label" in response.json
    assert len(response.json["signals"]) == 2


def test_valid_appeal_returns_under_review(client, monkeypatch, valid_submit_request):
    """Appeals should link to the original audit_id and creator_id."""

    def fake_analyze(self, normalized_text, metadata, audit_context):
        return SignalOutput(
            name="groq_semantic",
            version="v1",
            status="completed",
            ai_likelihood=0.82,
            confidence=0.90,
            confidence_label="high",
            raw_output={},
            explanation="fake",
            error=None,
        )

    monkeypatch.setattr(GroqSignalService, "analyze", fake_analyze)
    submit_response = client.post("/api/v1/submit", json=valid_submit_request)
    audit_id = submit_response.json["audit_id"]

    appeal_response = client.post(
        "/api/v1/appeals",
        json={
            "audit_id": audit_id,
            "creator_id": "user_123",
            "reason": "This is my original work and I can provide drafts.",
        },
    )

    assert appeal_response.status_code == 201
    assert appeal_response.json["status"] == "under_review"
    assert appeal_response.json["audit_id"] == audit_id
