"""Submit workflow orchestration service."""

from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from provenance_guard.models import RequestLogRecord


class SubmitService:
    """Coordinates the submit request workflow."""

    def __init__(self, audit_logger, validator, router, response_formatter):
        self.audit_logger = audit_logger
        self.validator = validator
        self.router = router
        self.response_formatter = response_formatter

    def handle(self, request_json):
        started_at = perf_counter()
        received_at = self._now()
        request_id = self._new_id("req")

        creator_id = self._safe_get(request_json, "creator_id")
        content_type = self._safe_get(request_json, "content_type")

        request_log = RequestLogRecord(
            request_id=request_id,
            route="/api/v1/submit",
            method="POST",
            request_status="received",
            received_at=received_at,
            creator_id=creator_id,
            content_type=content_type,
        )
        self.audit_logger.log_request_received(request_log)

        try:
            envelope, audit_context = self.validator.validate_submit_request(
                request_json=request_json,
                request_id=request_id,
                received_at=received_at,
            )

            self.audit_logger.update_request_log(
                replace(
                    request_log,
                    request_status="processing",
                    creator_id=envelope.creator_id,
                    content_type=envelope.content_type,
                )
            )

            pipeline_result = self.router.route(envelope, audit_context)
            response_body = self.response_formatter.format(pipeline_result)

            self.audit_logger.update_request_log(
                replace(
                    request_log,
                    request_status="completed",
                    creator_id=envelope.creator_id,
                    content_type=envelope.content_type,
                    status_code=200,
                    completed_at=self._now(),
                    duration_ms=self._duration_ms(started_at),
                )
            )
            return response_body, 200
        except SubmitValidationError as error:
            self.audit_logger.update_request_log(
                replace(
                    request_log,
                    request_status="validation_failed",
                    status_code=error.status_code,
                    error_code=error.code,
                    completed_at=self._now(),
                    duration_ms=self._duration_ms(started_at),
                )
            )
            return {"error": {"code": error.code, "message": error.message}}, error.status_code
        except Exception:
            self.audit_logger.update_request_log(
                replace(
                    request_log,
                    request_status="failed",
                    status_code=500,
                    error_code="internal_error",
                    completed_at=self._now(),
                    duration_ms=self._duration_ms(started_at),
                )
            )
            return {
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                }
            }, 500

    def _safe_get(self, request_json, key):
        if isinstance(request_json, dict):
            value = request_json.get(key)
            return value if isinstance(value, str) else None
        return None

    def _now(self):
        return datetime.now(UTC).isoformat()

    def _new_id(self, prefix):
        return f"{prefix}_{uuid4().hex}"

    def _duration_ms(self, started_at):
        return int((perf_counter() - started_at) * 1000)


class SubmitValidationError(Exception):
    """Validation error that maps directly to an HTTP response."""

    def __init__(self, code, message, status_code):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
