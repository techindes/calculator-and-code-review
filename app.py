from flask import Flask, Response, abort, render_template, request
from werkzeug.exceptions import HTTPException

from calculator import CalculatorError, calculate


HTTP_ERRORS = {
    400: ("INVALID_REQUEST", "Send valid JSON with exactly left, operator, and right."),
    404: ("NOT_FOUND", "Endpoint not found."),
    405: ("METHOD_NOT_ALLOWED", "This endpoint does not support that HTTP method."),
    413: ("REQUEST_TOO_LARGE", "Request body must not exceed 4096 bytes."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "Send the request with a JSON content type."),
    500: ("INTERNAL_ERROR", "An unexpected server error occurred."),
}


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 4096
    app.config["TRUSTED_HOSTS"] = ["localhost", "127.0.0.1"]

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.after_request
    def secure_response(response: Response) -> Response:
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/calculate")
    def calculate_request() -> tuple[dict[str, str], int]:
        payload = request.get_json()
        if not isinstance(payload, dict) or set(payload) != {"left", "operator", "right"}:
            abort(400)
        try:
            result = calculate(payload["left"], payload["operator"], payload["right"])
        except CalculatorError as error:
            status_code = 400 if error.code in ("INVALID_INPUT", "INVALID_OPERATOR") else 422
            return {"error": error.code, "message": str(error)}, status_code
        return {"result": result}, 200

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException) -> Response:
        code, message = HTTP_ERRORS.get(error.code, ("HTTP_ERROR", error.name))
        response = error.get_response()
        response.set_data(app.json.dumps({"error": code, "message": message}))
        response.content_type = "application/json"
        return response

    return app