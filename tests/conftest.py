"""Shared pytest fixtures for Provenance Guard tests."""

from pathlib import Path

import pytest

from provenance_guard.app import create_app
from provenance_guard.models import SignalOutput


@pytest.fixture
def app(monkeypatch, request):
    """Create a test app with an isolated SQLite database.

    Expected: tests can exercise the real Flask routes without touching the
    developer database. Unexpected: tests leaking audit rows across cases.
    """
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    artifact_dir = Path(".pytest_artifacts")
    artifact_dir.mkdir(exist_ok=True)
    database_path = artifact_dir / f"{request.node.name}.db"

    app = create_app(database_path=database_path)
    app.config.update(TESTING=True)
    return app


@pytest.fixture
def client(app):
    """Return Flask's test client for API-level tests."""
    return app.test_client()


@pytest.fixture
def valid_submit_request():
    """Canonical valid text request used by submit endpoint tests."""
    return {
        "creator_id": "user_123",
        "content_type": "text",
        "content": "This is a short creative paragraph. It has enough structure to test.",
        "metadata": {"platform": "writing_platform", "submission_id": "post_456"},
    }


class FakeGroqSignalService:
    """Stable Groq fake so tests do not depend on network or model drift."""

    def analyze(self, normalized_text, metadata, audit_context):
        return SignalOutput(
            name="groq_semantic",
            version="v1",
            status="completed",
            ai_likelihood=0.58,
            confidence=0.60,
            confidence_label="medium",
            raw_output={
                "reasons": ["Stable fake semantic reason."],
                "limitations": ["Stable fake limitation."],
            },
            explanation="Reasons: Stable fake semantic reason. Limitations: Stable fake limitation.",
            error=None,
        )
