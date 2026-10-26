import json
import unittest
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
from unittest.mock import patch

from app import create_app
from calculator import CalculatorError, calculate, format_result, parse_operand


class CalculatorTests(unittest.TestCase):
    def test_arithmetic_and_formatting(self):
        cases = [
            ("2", "+", "3", "5"),
            ("5", "-", "8", "-3"),
            ("-2", "*", "4", "-8"),
            ("-2", "*", "-4", "8"),
            ("7", "/", "2", "3.5"),
            ("7", "/", "-2", "-3.5"),
            ("0.1", "+", "0.2", "0.3"),
            ("0.3", "-", "0.2", "0.1"),
            ("0.1", "*", "0.2", "0.02"),
            ("1.50", "+", "2.50", "4"),
            ("5", "+", "5", "10"),
            ("-0", "*", "3", "0"),
            ("0", "/", "3", "0"),
            (".5", "+", "5.", "5.5"),
            ("+002", "+", "1", "3"),
            ("9007199254740993", "+", "1", "9007199254740994"),
            ("1", "/", "3", "0." + "3" * 28),
            ("2", "/", "3", "0." + "6" * 27 + "7"),
        ]
        for left, operator, right, expected in cases:
            with self.subTest(left=left, operator=operator, right=right):
                self.assertEqual(calculate(left, operator, right), expected)

    def test_half_even_rounding(self):
        cases = [
            ("1." + "0" * 27 + "5", "1"),
            ("1." + "0" * 26 + "15", "1." + "0" * 26 + "2"),
            ("-1." + "0" * 26 + "15", "-1." + "0" * 26 + "2"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(calculate(value, "+", "0"), expected)

    def test_result_can_be_reused_without_float_conversion(self):
        result = calculate("0.1", "+", "0.2")
        self.assertEqual(calculate(result, "+", "0.1"), "0.4")

    def test_invalid_operands(self):
        values = [
            "", " ", " 1", "1 ", ".", "+", "-", "1.2.3", "1,000",
            "1e3", "1_000", "NaN", "sNaN", "Infinity", "-Infinity",
            "2+3", "__import__('os')", "\u0661", "1\n", "--2",
            "1" * 101, None, True, 1, 0.1, [], {},
        ]
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(CalculatorError) as caught:
                    parse_operand(value)
                self.assertEqual(caught.exception.code, "INVALID_INPUT")

    def test_invalid_operators(self):
        for operator in ("%", "**", "add", "", " +", None, True, [], {}):
            with self.subTest(operator=operator):
                with self.assertRaises(CalculatorError) as caught:
                    calculate("1", operator, "2")
                self.assertEqual(caught.exception.code, "INVALID_OPERATOR")

    def test_zero_divisors(self):
        for left in ("5", "0"):
            for right in ("0", "-0", "+0", "0.00", "-.0"):
                with self.subTest(left=left, right=right):
                    with self.assertRaises(CalculatorError) as caught:
                        calculate(left, "/", right)
                    self.assertEqual(caught.exception.code, "DIVISION_BY_ZERO")

    def test_operand_length_boundary(self):
        value = "0" * 99 + "1"
        self.assertEqual(parse_operand(value), Decimal("1"))
        self.assertEqual(calculate(value, "+", "0"), "1")

    def test_result_length_boundary(self):
        value = "1" + "0" * 99
        result = calculate(value, "*", "1")
        self.assertEqual(result, value)
        self.assertEqual(calculate(result, "/", "10"), "1" + "0" * 98)
        with self.assertRaises(CalculatorError) as caught:
            calculate(value, "*", "10")
        self.assertEqual(caught.exception.code, "RESULT_OUT_OF_RANGE")

    def test_small_result_does_not_silently_become_zero(self):
        value = "0." + "0" * 97 + "1"
        self.assertEqual(calculate(value, "*", "1"), value)
        with self.assertRaises(CalculatorError) as caught:
            calculate(value, "/", "10")
        self.assertEqual(caught.exception.code, "RESULT_OUT_OF_RANGE")

    def test_nonfinite_results_are_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                with self.assertRaises(CalculatorError) as caught:
                    format_result(Decimal(value))
                self.assertEqual(caught.exception.code, "RESULT_OUT_OF_RANGE")

    def test_calculation_isolated_from_caller_context(self):
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_DOWN
            context.traps[Inexact] = True
            context.clear_flags()
            self.assertEqual(calculate("2", "/", "3"), "0." + "6" * 27 + "7")
            self.assertEqual(context.prec, 2)
            self.assertEqual(context.rounding, ROUND_DOWN)
            self.assertTrue(context.traps[Inexact])
            self.assertFalse(context.flags[Inexact])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.payload = {"left": "0.1", "operator": "+", "right": "0.2"}

    def assert_error(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code)
        self.assertTrue(response.is_json)
        self.assert_security_headers(response)
        payload = response.get_json()
        self.assertEqual(set(payload), {"error", "message"})
        self.assertEqual(payload["error"], code)
        self.assertIsInstance(payload["message"], str)
        self.assertTrue(payload["message"])
        self.assertNotIn("Traceback", payload["message"])

    def assert_security_headers(self, response):
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        policy = response.headers["Content-Security-Policy"]
        for directive in (
            "default-src 'none'", "script-src 'self'", "style-src 'self'",
            "connect-src 'self'", "object-src 'none'", "base-uri 'none'",
            "form-action 'none'", "frame-ancestors 'none'",
        ):
            self.assertIn(directive, policy.split("; "))
        self.assertNotIn("unsafe-", policy)
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        self.assertNotIn("Set-Cookie", response.headers)

    def test_homepage(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/html")
        self.assertIn(b'<output id="result"', response.data)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assert_security_headers(response)

    def test_trusted_hosts(self):
        for host in ("localhost", "localhost:5050", "127.0.0.1:12345"):
            with self.subTest(host=host):
                self.assertEqual(self.client.get("/", headers={"Host": host}).status_code, 200)
        for host in ("attacker.example", "localhost.attacker.example", "sub.localhost"):
            with self.subTest(host=host):
                self.assert_error(self.client.get("/", headers={"Host": host}), 400, "INVALID_REQUEST")

    def test_static_assets(self):
        for path, mimetype in (
            ("/static/calculator.css", "text/css"),
            ("/static/calculator.js", "text/javascript"),
            ("/static/icons/calculator.svg", "image/svg+xml"),
            ("/static/icons/delete.svg", "image/svg+xml"),
        ):
            with self.subTest(path=path):
                with self.client.get(path) as response:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.mimetype, mimetype)
                    self.assertTrue(response.data)
                    self.assert_security_headers(response)

    def test_json_content_type_parameters(self):
        for content_type in ("application/json; charset=utf-8", "application/vnd.calculator+json"):
            with self.subTest(content_type=content_type):
                response = self.client.post("/api/calculate", data=json.dumps(self.payload), content_type=content_type)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), {"result": "0.3"})

    def test_private_files_not_served(self):
        for path in ("/.env", "/app.py", "/requirements.txt", "/.venv/pyvenv.cfg", "/static/../app.py"):
            with self.subTest(path=path):
                self.assert_error(self.client.get(path), 404, "NOT_FOUND")

    def test_success(self):
        response = self.client.post("/api/calculate", json=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assert_security_headers(response)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.get_json(), {"result": "0.3"})

    def test_all_operations(self):
        for operator, expected in (("+", "10"), ("-", "6"), ("*", "16"), ("/", "4")):
            with self.subTest(operator=operator):
                response = self.client.post(
                    "/api/calculate", json={"left": "8", "operator": operator, "right": "2"}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), {"result": expected})

    def test_malformed_json_and_utf8(self):
        for body in (b"", b"{", b'{"left":}', b'{"left":"\xff"}'):
            with self.subTest(body=body):
                response = self.client.post(
                    "/api/calculate", data=body, content_type="application/json"
                )
                self.assert_error(response, 400, "INVALID_REQUEST")

    def test_invalid_payload_shapes(self):
        for payload in (None, [], True, 2, "hello", {}, {"left": "1"}):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/calculate", data=json.dumps(payload), content_type="application/json"
                )
                self.assert_error(response, 400, "INVALID_REQUEST")

    def test_missing_fields(self):
        for field in self.payload:
            payload = {key: value for key, value in self.payload.items() if key != field}
            with self.subTest(field=field):
                response = self.client.post("/api/calculate", json=payload)
                self.assert_error(response, 400, "INVALID_REQUEST")

    def test_extra_fields(self):
        response = self.client.post("/api/calculate", json={**self.payload, "precision": 100000})
        self.assert_error(response, 400, "INVALID_REQUEST")

    def test_invalid_operands_on_either_side(self):
        for field in ("left", "right"):
            for value in (None, True, 1, 0.1, [], {}, "", "NaN", "Infinity", "1e999999", "1+2", "1" * 101):
                with self.subTest(field=field, value=value):
                    response = self.client.post(
                        "/api/calculate", json={**self.payload, field: value}
                    )
                    self.assert_error(response, 400, "INVALID_INPUT")

    def test_invalid_operators(self):
        for operator in ("%", "**", "", None, True, [], {}):
            with self.subTest(operator=operator):
                response = self.client.post(
                    "/api/calculate", json={**self.payload, "operator": operator}
                )
                self.assert_error(response, 400, "INVALID_OPERATOR")

    def test_division_by_zero(self):
        for left, right in (("5", "0"), ("0", "0"), ("5", "-0"), ("5", "0.00")):
            with self.subTest(left=left, right=right):
                response = self.client.post(
                    "/api/calculate", json={"left": left, "operator": "/", "right": right}
                )
                self.assert_error(response, 422, "DIVISION_BY_ZERO")

    def test_result_out_of_range(self):
        response = self.client.post(
            "/api/calculate", json={"left": "1" + "0" * 99, "operator": "*", "right": "10"}
        )
        self.assert_error(response, 422, "RESULT_OUT_OF_RANGE")

    def test_wrong_content_type(self):
        for content_type in (None, "text/plain", "application/x-www-form-urlencoded"):
            with self.subTest(content_type=content_type):
                response = self.client.post(
                    "/api/calculate", data=json.dumps(self.payload), content_type=content_type
                )
                self.assert_error(response, 415, "UNSUPPORTED_MEDIA_TYPE")

    def test_request_size_boundary(self):
        body = json.dumps(self.payload).encode("utf-8").ljust(4096, b" ")
        response = self.client.post("/api/calculate", data=body, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"result": "0.3"})
        response = self.client.post(
            "/api/calculate", data=body + b" ", content_type="application/json"
        )
        self.assert_error(response, 413, "REQUEST_TOO_LARGE")

    def test_wrong_method_preserves_allow_header(self):
        response = self.client.get("/api/calculate")
        self.assert_error(response, 405, "METHOD_NOT_ALLOWED")
        self.assertIn("POST", response.headers["Allow"])

    def test_unknown_endpoint(self):
        response = self.client.get("/missing")
        self.assert_error(response, 404, "NOT_FOUND")

    def test_unexpected_failure_is_generic(self):
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        with patch("app.calculate", side_effect=RuntimeError("private diagnostic detail")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.client.post("/api/calculate", json=self.payload)
        self.assert_error(response, 500, "INTERNAL_ERROR")
        self.assertNotIn("private diagnostic detail", response.get_data(as_text=True))
        response = self.client.post("/api/calculate", json=self.payload)
        self.assertEqual(response.status_code, 200)

    def test_requests_do_not_share_calculation_state(self):
        response = self.client.post("/api/calculate", json=self.payload)
        previous_result = response.get_json()["result"]
        response = self.client.post(
            "/api/calculate", json={"left": previous_result, "operator": "+", "right": "0.1"}
        )
        self.assertEqual(response.get_json(), {"result": "0.4"})
        response = self.client.post("/api/calculate", json=self.payload)
        self.assertEqual(response.get_json(), {"result": "0.3"})


if __name__ == "__main__":
    unittest.main()