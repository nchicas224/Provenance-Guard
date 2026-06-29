"""Submit endpoint route."""

from flask import Blueprint, jsonify, request


def create_submit_blueprint(submit_service):
    blueprint = Blueprint("submit", __name__)

    @blueprint.post("/api/v1/submit")
    def submit():
        request_json = request.get_json(silent=True)
        response_body, status_code = submit_service.handle(request_json)
        return jsonify(response_body), status_code

    return blueprint
