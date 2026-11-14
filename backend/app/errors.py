"""Uniform JSON error responses: {"error": {"code", "message", "details"}}."""
import logging
from flask import jsonify
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

log = logging.getLogger("terrawatt.errors")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def bad_request(message, details=None):
    return ApiError(400, "bad_request", message, details)


def not_found(message="Resource not found"):
    return ApiError(404, "not_found", message)


def _payload(code, message, details=None):
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return body


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def _api_error(e):
        return jsonify(_payload(e.code, e.message, e.details)), e.status

    @app.errorhandler(ValidationError)
    def _validation(e):
        details = [{"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]} for err in e.errors()]
        return jsonify(_payload("validation_error", "Some fields are invalid.", details)), 422

    @app.errorhandler(HTTPException)
    def _http(e):
        return jsonify(_payload(e.name.lower().replace(" ", "_"), e.description)), e.code

    @app.errorhandler(Exception)
    def _unhandled(e):
        log.exception("Unhandled error")
        return jsonify(_payload("internal_error", "Something went wrong on our side.")), 500
