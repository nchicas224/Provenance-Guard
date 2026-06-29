"""Request validation service."""

from uuid import uuid4

from provenance_guard import config
from provenance_guard.models import AuditContext, RequestEnvelope
from provenance_guard.services.errors import SubmitValidationError


class RequestValidator:
    """Validates public submit request envelopes."""

    def validate_submit_request(self, request_json, request_id, received_at):
        if not isinstance(request_json, dict):
            raise SubmitValidationError(
                code="invalid_json",
                message="Request body must be valid JSON.",
                status_code=400,
            )

        creator_id = self._required_string(request_json, "creator_id")
        content_type = self._required_string(request_json, "content_type")
        content = self._required_string(request_json, "content")
        metadata = request_json.get("metadata") or {}

        if not isinstance(metadata, dict):
            raise SubmitValidationError(
                code="invalid_metadata",
                message="metadata must be an object when provided.",
                status_code=400,
            )

        if content_type != "text":
            raise SubmitValidationError(
                code="unsupported_content_type",
                message="v1 supports text submissions only.",
                status_code=415,
            )

        if not content.strip():
            raise SubmitValidationError(
                code="empty_content",
                message="content must not be empty.",
                status_code=400,
            )

        if len(content) > config.MAX_TEXT_CHARS:
            raise SubmitValidationError(
                code="payload_too_large",
                message=f"text submissions must be {config.MAX_TEXT_CHARS} characters or fewer.",
                status_code=413,
            )

        audit_id = f"audit_{uuid4().hex}"
        envelope = RequestEnvelope(
            request_id=request_id,
            creator_id=creator_id,
            content_type=content_type,
            content=content,
            metadata=metadata,
            received_at=received_at,
        )
        audit_context = AuditContext(
            request_id=request_id,
            audit_id=audit_id,
            creator_id=creator_id,
            content_type=content_type,
            received_at=received_at,
            status="processing",
        )

        return envelope, audit_context

    def _required_string(self, request_json, field_name):
        value = request_json.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise SubmitValidationError(
                code=f"missing_{field_name}",
                message=f"{field_name} is required.",
                status_code=400,
            )
        return value
