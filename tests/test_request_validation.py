"""Tests for submit request validation.

These tests protect the API gateway boundary. Expected invalid requests should
fail before expensive signal work begins. Unexpected behavior would be creating
appealable audit decisions for malformed or unsupported requests.
"""

import pytest

from provenance_guard.services.errors import SubmitValidationError
from provenance_guard.services.request_validator import RequestValidator


def test_valid_submit_request_returns_envelope_and_audit_context(valid_submit_request):
    """A valid request should become a routeable envelope and appealable audit context."""
    envelope, audit_context = RequestValidator().validate_submit_request(
        request_json=valid_submit_request,
        request_id="req_123",
        received_at="2026-06-29T00:00:00Z",
    )

    assert envelope.creator_id == "user_123"
    assert envelope.content_type == "text"
    assert audit_context.audit_id.startswith("audit_")


def test_missing_creator_id_fails_before_audit_id(valid_submit_request):
    """Missing creator_id should fail with 400 because appeals cannot link it."""
    request_json = dict(valid_submit_request)
    request_json.pop("creator_id")

    with pytest.raises(SubmitValidationError) as error:
        RequestValidator().validate_submit_request(
            request_json=request_json,
            request_id="req_123",
            received_at="2026-06-29T00:00:00Z",
        )

    assert error.value.status_code == 400
    assert error.value.code == "missing_creator_id"


def test_unsupported_content_type_returns_415(valid_submit_request):
    """v1 is text-only; unsupported types should fail clearly instead of routing."""
    request_json = dict(valid_submit_request, content_type="image")

    with pytest.raises(SubmitValidationError) as error:
        RequestValidator().validate_submit_request(
            request_json=request_json,
            request_id="req_123",
            received_at="2026-06-29T00:00:00Z",
        )

    assert error.value.status_code == 415
    assert error.value.code == "unsupported_content_type"
