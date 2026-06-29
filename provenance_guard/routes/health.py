"""Health endpoint route."""

from flask import Blueprint, jsonify

from provenance_guard import config


def create_health_blueprint(audit_logger):
    blueprint = Blueprint("health", __name__)

    @blueprint.get("/api/v1/health")
    def health():
        database_reachable = audit_logger.is_reachable()
        status_code = 200 if database_reachable else 503
        response_status = "ok" if database_reachable else "degraded"
        database_status = "reachable" if database_reachable else "unreachable"

        return jsonify(
            {
                "status": response_status,
                "service": config.SERVICE_NAME,
                "version": config.API_VERSION,
                "database": database_status,
            }
        ), status_code

    return blueprint
