"""Appeals endpoint route."""

from flask import Blueprint, jsonify, request


def create_appeals_blueprint(appeal_handler):
    blueprint = Blueprint("appeals", __name__)

    @blueprint.post("/api/v1/appeals")
    def appeals():
        request_json = request.get_json(silent=True)
        response_body, status_code = appeal_handler.handle(request_json)
        return jsonify(response_body), status_code

    return blueprint
