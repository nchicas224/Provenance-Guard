"""Flask application factory."""

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from provenance_guard import config
from provenance_guard.pipelines.text_pipeline import TextPipeline
from provenance_guard.routes.appeals import create_appeals_blueprint
from provenance_guard.routes.health import create_health_blueprint
from provenance_guard.routes.submit import create_submit_blueprint
from provenance_guard.scoring.confidence_scorer import ConfidenceScorer
from provenance_guard.services.appeal_handler import AppealHandler
from provenance_guard.services.audit_logger import AuditLogger
from provenance_guard.services.content_type_router import ContentTypeRouter
from provenance_guard.services.request_validator import RequestValidator
from provenance_guard.services.response_formatter import ResponseFormatter
from provenance_guard.services.submit_service import SubmitService
from provenance_guard.signals.groq_signal_service import GroqSignalService
from provenance_guard.signals.stylometric_signal_service import StylometricSignalService


def create_app(database_path="provenance_guard.db"):
    app = Flask(__name__)

    audit_logger = AuditLogger(database_path)
    limiter = Limiter(key_func=_rate_limit_key)
    limiter.init_app(app)

    groq_signal_service = GroqSignalService()
    stylometric_signal_service = StylometricSignalService()
    confidence_scorer = ConfidenceScorer()
    text_pipeline = TextPipeline(
        groq_signal_service=groq_signal_service,
        stylometric_signal_service=stylometric_signal_service,
        confidence_scorer=confidence_scorer,
        audit_logger=audit_logger,
    )
    router = ContentTypeRouter(text_pipeline=text_pipeline)
    response_formatter = ResponseFormatter(audit_logger=audit_logger)
    submit_service = SubmitService(
        audit_logger=audit_logger,
        validator=RequestValidator(),
        router=router,
        response_formatter=response_formatter,
    )
    appeal_handler = AppealHandler(audit_logger=audit_logger)

    app.register_blueprint(create_submit_blueprint(submit_service, limiter))
    app.register_blueprint(create_appeals_blueprint(appeal_handler))
    app.register_blueprint(create_health_blueprint(audit_logger))

    @app.errorhandler(429)
    def rate_limited(_error):
        return jsonify(
            {
                "error": {
                    "code": "rate_limited",
                    "message": "Too many submissions. Please wait before trying again.",
                }
            }
        ), 429

    return app


def _rate_limit_key():
    request_json = request.get_json(silent=True) if request.method == "POST" else None
    if isinstance(request_json, dict):
        creator_id = request_json.get("creator_id")
        if isinstance(creator_id, str) and creator_id.strip():
            return creator_id.strip()
    return get_remote_address()
