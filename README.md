# Calculator Interview

A calculator web app with a plain HTML/CSS/JavaScript frontend and a Python/Flask
backend. The backend does the arithmetic with Python's `decimal.Decimal`, so
`0.1 + 0.2` gives `0.3`. There is no database or stored history.

The interview answers (Part 1 code review and Part 2 follow-up questions) are in
[Engineering_Intern_Interview_Questions.md](Engineering_Intern_Interview_Questions.md).

## Run locally

Tested on macOS with Python 3.14 and Flask 3.1.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m flask --app app run --host 127.0.0.1 --port 5051
```

Open **http://127.0.0.1:5051/**. This is Flask's development server for a local
demo, not a production deployment.

## Run tests

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium webkit
.venv/bin/python -m unittest discover -v
```

`test_calculator.py` covers the arithmetic and API. `test_browser.py` starts the
real app and drives it in Chromium and WebKit with Playwright. Run just the
backend tests with `-m unittest -v test_calculator` (no Playwright needed).

## How it works

- Keypad or keyboard: digits, `.`, `+ - * /`, `Enter`/`=` to calculate, `Escape`
  to clear, `Backspace` to edit, `F9` to change sign.
- Each operation is sent to `POST /api/calculate` as
  `{"left":"0.1","operator":"+","right":"0.2"}` and returns `{"result":"0.3"}`.
  Numbers are sent as strings so JavaScript never rounds them.
- Operations run immediately, left to right: `2 + 3 * 4 =` gives `20`, not `14`.
- Errors such as division by zero return a JSON error (`422`) and the calculator
  shows a message and recovers. Invalid requests return `400`; oversized bodies `413`.
- Operands are limited to 100 characters, and results use 28 significant digits,
  so results like `1 / 3` are rounded.
- No `eval` or expression parsing is used.

## Code layout

- [calculator.py](calculator.py): input validation, decimal arithmetic, formatting.
- [app.py](app.py): Flask app, API endpoint, JSON errors, security headers.
- [templates/index.html](templates/index.html), [static/](static/): the frontend.
- [test_calculator.py](test_calculator.py), [test_browser.py](test_browser.py): tests.

The icons come from [Lucide](https://github.com/lucide-icons/lucide); their license
is in [static/icons/LICENSE](static/icons/LICENSE).

## Security notes

This is a local demo, not a hardened production service. It validates all input
on the server, limits request size, accepts only `localhost`/`127.0.0.1` Host
headers, and sends a strict Content Security Policy and related headers. A public
deployment would also need HTTPS, a production WSGI server, and rate limiting.

## Not done or not tested

- Operator precedence, parentheses, history, and scientific functions.
- Deployment, Firefox, real phones, and screen readers.
