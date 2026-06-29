"""Submit endpoint route."""

from flask import Blueprint, jsonify, request

from provenance_guard import config


def create_submit_blueprint(submit_service, limiter=None):
    blueprint = Blueprint("submit", __name__)

    def submit():
        request_json = request.get_json(silent=True)
        response_body, status_code = submit_service.handle(request_json)
        return jsonify(response_body), status_code

    if limiter:
        submit = limiter.limit(
            f"{config.SUBMIT_RATE_LIMIT_PER_MINUTE};{config.SUBMIT_RATE_LIMIT_PER_DAY}"
        )(submit)

    blueprint.add_url_rule("/api/v1/submit", view_func=submit, methods=["POST"])
    return blueprint
