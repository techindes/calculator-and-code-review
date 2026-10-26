import re
from decimal import Context, Decimal, DecimalException, ROUND_HALF_EVEN, localcontext


MAX_NUMBER_LENGTH = 100
PRECISION = 28
NUMBER_PATTERN = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
OPERATORS = ("+", "-", "*", "/")


class CalculatorError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_operand(value: object) -> Decimal:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= MAX_NUMBER_LENGTH
        or NUMBER_PATTERN.fullmatch(value) is None
    ):
        raise CalculatorError(
            "INVALID_INPUT",
            "Each operand must be a decimal string of 1 to 100 characters, "
            "without spaces or exponent notation.",
        )
    number = Decimal(value)
    if not number.is_finite():
        raise CalculatorError("INVALID_INPUT", "Operands must be finite numbers.")
    return number


def format_result(result: Decimal) -> str:
    if not result.is_finite():
        raise CalculatorError("RESULT_OUT_OF_RANGE", "Result is out of range.")
    if result.is_zero():
        return "0"
    text = format(result, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if len(text) > MAX_NUMBER_LENGTH:
        raise CalculatorError("RESULT_OUT_OF_RANGE", "Result exceeds 100 characters.")
    return text


def calculate(left: object, operator: object, right: object) -> str:
    if not isinstance(operator, str) or operator not in OPERATORS:
        raise CalculatorError("INVALID_OPERATOR", "Operator must be +, -, *, or /.")
    left_number = parse_operand(left)
    right_number = parse_operand(right)
    if operator == "/" and right_number.is_zero():
        raise CalculatorError("DIVISION_BY_ZERO", "Cannot divide by zero.")

    try:
        with localcontext(Context(prec=PRECISION, rounding=ROUND_HALF_EVEN)):
            if operator == "+":
                result = left_number + right_number
            elif operator == "-":
                result = left_number - right_number
            elif operator == "*":
                result = left_number * right_number
            else:
                result = left_number / right_number
            return format_result(result)
    except DecimalException as error:
        raise CalculatorError("RESULT_OUT_OF_RANGE", "Result is out of range.") from error