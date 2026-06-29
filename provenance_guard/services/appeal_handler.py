"""Appeal workflow service."""

from datetime import UTC, datetime
from uuid import uuid4

from provenance_guard.models import AppealRecord, RequestLogRecord, SystemEventRecord
from provenance_guard.services.errors import AppealValidationError


class AppealHandler:
    """Handles creator appeals for completed attribution decisions."""

    def __init__(self, audit_logger):
        self.audit_logger = audit_logger

    def handle(self, request_json):
        request_id = self._new_id("req")
        received_at = self._now()
        creator_id = self._safe_get(request_json, "creator_id")

        request_log = RequestLogRecord(
            request_id=request_id,
            route="/api/v1/appeals",
            method="POST",
            request_status="received",
            received_at=received_at,
            creator_id=creator_id,
        )
        self.audit_logger.log_request_received(request_log)

        try:
            audit_id = self._required_string(request_json, "audit_id")
            creator_id = self._required_string(request_json, "creator_id")
            reason = self._required_string(request_json, "reason")
            contact_email = self._contact_email(request_json)

            original = self.audit_logger.get_attribution_decision(audit_id)
            if original is None:
                self._log_event(
                    request_id=request_id,
                    event_type="appeal_unknown_audit",
                    severity="warning",
                    message="Appeal referenced an unknown audit_id.",
                    details={"audit_id": audit_id},
                    creator_id=creator_id,
                )
                return self._error_response(
                    request_log,
                    "audit_not_found",
                    "audit_id does not exist.",
                    404,
                )

            if original["creator_id"] != creator_id:
                self._log_event(
                    request_id=request_id,
                    audit_id=audit_id,
                    event_type="appeal_creator_mismatch",
                    severity="warning",
                    message="Appeal creator_id did not match original decision.",
                    details={"audit_id": audit_id},
                    creator_id=creator_id,
                )
                return self._error_response(
                    request_log,
                    "creator_mismatch",
                    "creator_id does not match the original audit record.",
                    403,
                )

            if self.audit_logger.has_active_appeal(audit_id):
                self._log_event(
                    request_id=request_id,
                    audit_id=audit_id,
                    event_type="duplicate_appeal",
                    severity="info",
                    message="Duplicate active appeal rejected.",
                    details={"audit_id": audit_id},
                    creator_id=creator_id,
                )
                return self._error_response(
                    request_log,
                    "duplicate_appeal",
                    "An active appeal already exists for this audit_id.",
                    409,
                )

            now = self._now()
            appeal = AppealRecord(
                appeal_id=self._new_id("appeal"),
                audit_id=audit_id,
                creator_id=creator_id,
                original_attribution_result=original["attribution_result"],
                original_ai_likelihood=original["ai_likelihood"],
                original_confidence_score=original["confidence_score"],
                original_confidence_level=original["confidence_level"],
                original_transparency_label=original["transparency_label"],
                reason=reason,
                status="under_review",
                contact_email=contact_email,
                created_at=now,
                updated_at=now,
            )
            self.audit_logger.log_appeal(appeal)
            self.audit_logger.update_request_log(
                RequestLogRecord(
                    request_id=request_id,
                    route="/api/v1/appeals",
                    method="POST",
                    request_status="completed",
                    received_at=received_at,
                    creator_id=creator_id,
                    status_code=201,
                    completed_at=self._now(),
                )
            )

            return {
                "appeal_id": appeal.appeal_id,
                "audit_id": appeal.audit_id,
                "creator_id": appeal.creator_id,
                "status": appeal.status,
                "created_at": appeal.created_at,
            }, 201
        except AppealValidationError as error:
            return self._error_response(
                request_log,
                error.code,
                error.message,
                error.status_code,
            )
        except Exception:
            return self._error_response(
                request_log,
                "internal_error",
                "An unexpected error occurred.",
                500,
            )

    def _required_string(self, request_json, field_name):
        if not isinstance(request_json, dict):
            raise AppealValidationError(
                code="invalid_json",
                message="Request body must be valid JSON.",
                status_code=400,
            )

        value = request_json.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise AppealValidationError(
                code=f"missing_{field_name}",
                message=f"{field_name} is required.",
                status_code=400,
            )
        return value.strip()

    def _contact_email(self, request_json):
        contact = request_json.get("contact") if isinstance(request_json, dict) else None
        if not isinstance(contact, dict):
            return None

        email = contact.get("email")
        return email.strip() if isinstance(email, str) and email.strip() else None

    def _error_response(self, request_log, code, message, status_code):
        self.audit_logger.update_request_log(
            RequestLogRecord(
                request_id=request_log.request_id,
                route=request_log.route,
                method=request_log.method,
                request_status="validation_failed" if status_code < 500 else "failed",
                received_at=request_log.received_at,
                creator_id=request_log.creator_id,
                status_code=status_code,
                error_code=code,
                completed_at=self._now(),
            )
        )
        return {"error": {"code": code, "message": message}}, status_code

    def _log_event(
        self,
        request_id,
        event_type,
        severity,
        message,
        details,
        creator_id=None,
        audit_id=None,
    ):
        self.audit_logger.log_system_event(
            SystemEventRecord(
                event_id=self._new_id("event"),
                request_id=request_id,
                audit_id=audit_id,
                creator_id=creator_id,
                event_type=event_type,
                severity=severity,
                message=message,
                details=details,
                created_at=self._now(),
            )
        )

    def _safe_get(self, request_json, key):
        if isinstance(request_json, dict):
            value = request_json.get(key)
            return value if isinstance(value, str) else None
        return None

    def _now(self):
        return datetime.now(UTC).isoformat()

    def _new_id(self, prefix):
        return f"{prefix}_{uuid4().hex}"
