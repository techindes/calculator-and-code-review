# Calculator Interview

A responsive calculator with a vanilla HTML/CSS/JavaScript frontend and a
stateless Python/Flask API. Python's standard-library `decimal.Decimal` performs
addition, subtraction, multiplication, and division. There is no database,
authentication, or stored calculation history.

## Run locally

Tested on macOS with Python 3.14.0 and Flask 3.1.3. From this project directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest -v test_calculator
.venv/bin/python -m flask --app app run --host 127.0.0.1 --port 5051 --no-debugger --no-reload
```

Open **http://127.0.0.1:5051/**. If the port is occupied, choose
another port and update the examples below. Stop the server with Ctrl+C.

This is a local development server, not a production deployment. Keep it bound
to localhost. A public deployment would need a production WSGI server, HTTPS,
appropriate resource/rate limits, and a separate deployment review.

In VS Code, open this project folder and select its `.venv/bin/python` using
**Python: Select Interpreter**. Import warnings from another interpreter or an
unattached workspace do not reflect the isolated environment used by the tests.

Flask is the only direct runtime dependency. The requirements file also pins its
six resolved dependencies for reproducibility. The frontend needs no build step,
CDN, npm packages, or network access beyond the local Flask server.

## Controls and behavior

- Use the keypad or keyboard digits, decimal point, and `+`, `-`, `*`, `/`.
- `Enter` or `=` calculates, `Escape` clears, `Backspace` edits, and `F9` changes
  sign. Tab navigates controls; Space activates the focused button. Safari's
  default macOS keyboard setting may require Option-Tab to focus buttons.
- Calculations execute immediately from left to right: `2 + 3 * 4 =` gives
  `20`, not `14`. Wait for each intermediate request to finish before continuing.
- A new operator replaces an operator that has no right operand yet:
  `5 + - 2 =` gives `3`. Use Change sign/F9 for a negative right operand.
- Equals with an incomplete pair, repeated equals after a result, and backspace
  after a result do nothing. New digits after a result begin a new calculation.
- While calculating, only Clear remains available. Clear aborts the browser
  request and invalidates late responses; it does not guarantee server cancellation.
- Requests time out after 10 seconds. Errors remain until a new entry or Clear;
  a failed calculation resets the result display to zero. Exceeding the input
  length limit rejects the extra character without discarding the existing entry.
- Long results wrap; long expressions scroll within the expression area. Short
  viewports scroll vertically. Results are announced to assistive technology
  without duplicating a long number in the visible status area.

## Run tests

Backend-only tests need just the runtime requirements. For the complete suite:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium webkit
.venv/bin/python -m unittest discover -v
```

Run a narrower slice with `-m unittest -v test_calculator` or
`-m unittest -v test_browser`. The browser suite starts and stops its own real
Flask application on a dynamically allocated loopback port. It does not depend
on the interactive demo server. Missing browser dependencies fail the run.

Screenshots and traces are written to the ignored `test-artifacts/` directory
for passing and failing tests. Inspect a trace with:

```sh
.venv/bin/python -m playwright show-trace test-artifacts/chromium-test_decimal_and_error_recovery.zip
```

Playwright and its resolved dependencies are development-only pins. They are not
needed to run the calculator. Keep generated browser artifacts out of Git.

## API

`POST /api/calculate` with `Content-Type: application/json`:

```sh
curl -i http://127.0.0.1:5051/api/calculate \
  -H 'Content-Type: application/json' \
  --data '{"left":"0.1","operator":"+","right":"0.2"}'
```

Successful response, HTTP `200`:

```json
{"result":"0.3"}
```

The JSON object must contain exactly `left`, `operator`, and `right`. Operators
are `+`, `-`, `*`, or `/`. Both operands and the result are **strings**, not JSON
numbers. Preserve these strings on the frontend instead of converting them with
JavaScript `Number` or `parseFloat`; the backend converts directly to `Decimal`,
never through Python `float`.

Example error request:

```sh
curl -i http://127.0.0.1:5051/api/calculate \
  -H 'Content-Type: application/json' \
  --data '{"left":"5","operator":"/","right":"0"}'
```

Response, HTTP `422`:

```json
{"error":"DIVISION_BY_ZERO","message":"Cannot divide by zero."}
```

| HTTP status | Error code | Condition |
|---|---|---|
| 400 | `INVALID_REQUEST` | Malformed JSON, non-object body, missing or extra fields |
| 400 | `INVALID_INPUT` | Invalid operand type, syntax, or length |
| 400 | `INVALID_OPERATOR` | Unsupported or incorrectly typed operator |
| 404 | `NOT_FOUND` | Unknown endpoint |
| 405 | `METHOD_NOT_ALLOWED` | Wrong HTTP method; the `Allow` header is preserved |
| 413 | `REQUEST_TOO_LARGE` | Body exceeds 4096 bytes |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Missing or unsupported JSON content type |
| 422 | `DIVISION_BY_ZERO` | Division by any representation of zero, including `0 / 0` |
| 422 | `RESULT_OUT_OF_RANGE` | Result cannot be returned within the numerical limits |
| 500 | `INTERNAL_ERROR` | Unexpected server error; response contains no internal details |

The base URL serves the calculator. Visiting the calculation endpoint with a
browser's ordinary GET request returns `405`. Untrusted Host headers return
`400`; this demo accepts only `localhost` and `127.0.0.1`, with any port.

## Numerical rules

- One operation on two operands per request; no full expressions or parentheses.
- Each operand has 1 to 100 characters: ASCII digits, an optional leading sign,
  and at most one decimal point, with at least one digit.
- Integers, negative values, `.5`, `5.`, and `+2` are accepted. Whitespace,
  commas, underscores, scientific notation, `NaN`, and infinity are rejected.
- Arithmetic uses an isolated context with 28 **significant digits**, rounding
  to nearest with ties to even. This is not 28 decimal places or unlimited
  precision. Results exceeding this precision are rounded; repeating divisions
  and chains of rounded results are not guaranteed to be exact.
- Results use fixed-point decimal notation. Redundant fractional zeros are
  removed, integer zeros are preserved, and signed zero becomes `"0"`.
- A formatted result longer than 100 characters is rejected, not truncated or
  silently replaced with zero. Every successful result can be reused as an operand.
- Neither `eval` nor executable expression parsing is used. Python's `math`
  module is unnecessary for these four operations.

## Code layout

- [calculator.py](calculator.py): decimal validation, arithmetic, formatting, and domain errors.
- [app.py](app.py): Flask application factory, request validation, endpoint, and JSON error handling.
- [test_calculator.py](test_calculator.py): arithmetic and API tests, including failure paths.
- [templates/index.html](templates/index.html): accessible keypad and display.
- [static/calculator.css](static/calculator.css): responsive layout and visual states.
- [static/calculator.js](static/calculator.js): string-based input state, rendering, and API calls.
- [test_browser.py](test_browser.py): real-browser workflows and isolated fault/security probes.
- [requirements-dev.txt](requirements-dev.txt): pinned browser-testing dependencies.

The two local icons come from [Lucide 0.468.0](https://github.com/lucide-icons/lucide/tree/0.468.0).
Their upstream license is preserved in [static/icons/LICENSE](static/icons/LICENSE).

## Security scope

This is a hardened **local interview demo**, not a production security certification.

- Numeric strings are validated on the server, with request, operand, and result
  bounds. There is no executable expression evaluation or filesystem access from
  calculation input. Malformed requests and unexpected failures receive safe errors.
- A strict Content Security Policy allows only local scripts, styles, images,
  fonts, and connections. Inline scripts/styles, objects, forms, base URL changes,
  and embedding are prohibited. `nosniff`, `DENY`, and `no-referrer` headers cover
  successful and failed responses. HTML/API responses use `Cache-Control: no-store`.
- Flask validates Host headers. The run command binds only to loopback and keeps
  the debugger/reloader disabled. No broad CORS policy or proxy-header trust is enabled.
- The frontend uses text-only DOM updates, validates response shape and decimal
  strings, and maps known errors to fixed messages. It never renders server-supplied
  error text as HTML. Request generations prevent stale UI updates after Clear.
- The app creates no cookies, authentication state, local storage, or persistent
  mutations. Authentication/CSRF infrastructure is not added to this stateless tool.
  CORS and a browser timeout are not authentication or server denial-of-service controls.
- Production hosting would require HTTPS, a production WSGI server, explicit
  deployment host configuration, timeouts/concurrency/rate controls, monitoring,
  and a separate security review. Request limits alone are not comprehensive DoS protection.

## Verification

On October 26, 2026, GitHub Copilot verified:

- **56 tests passed, zero failures/skips, exit code 0**: 32 arithmetic/API tests
  and 24 browser tests (12 each in Chromium and WebKit). The original 27 backend
  tests were preserved and passed before frontend implementation.
- Real full-stack workflows: all operations, `0.1 + 0.2 = 0.3`, integers beyond
  JavaScript's safe-integer limit, repeating division, immediate chaining, keyboard
  editing, operator replacement, touch controls, and recovery after division by zero.
- Isolated fault injection: delayed/stale responses, duplicate input, timeout,
  network failure, non-JSON/malformed/untrusted response data, and safe recovery.
  These probes are distinct from the normal, unmocked backend E2E flows.
- Security regressions: input/request bounds, malformed JSON/UTF-8, safe 500 errors,
  invalid Host, unavailable private files, security headers, inline-script blocking,
  iframe blocking, and absence of unexpected external requests or page errors.
- Layout checks in both engines at 1440x900, 390x844, 320x568, and 844x390:
  100-character results, stable keypad position, minimum touch targets, no horizontal
  page overflow, and initial/error/long-result screenshots. Representative desktop
  and mobile screenshots were visually inspected.
- `pip check`: no broken requirements. `pip-audit`: no known vulnerabilities in
  either the seven-package runtime set or the eleven-package development set.
  The available app-modernization advisory tool does not support Python; the
  Python advisory scan was used instead. Results are point-in-time, not a guarantee.
- The final live demo returned HTML `200` with security headers, and its real
  calculation endpoint returned `{"result":"0.3"}`. The integrated browser opened
  the completed interface at http://127.0.0.1:5051/.

WebKit screenshots inject an inline `body {}` stylesheet inside Playwright 1.64.1.
The CSP correctly blocks it. Screenshot tests assert and isolate exactly that
one tooling-induced violation; other violations fail. The application policy
was not relaxed. WebKit keyboard tests use Option-Tab under its default setting.

Not verified: physical mobile devices, Firefox, native 200% browser zoom,
manual screen-reader operation, production deployment, or exhaustive penetration/
load testing. Editor Python import diagnostics remain unresolved while this chat
lacks the matching workspace/interpreter; runtime tests use the project venv.
See [runtime-validation-report.md](runtime-validation-report.md) for the verdict.

The optional dependency check can be repeated in a separate environment:

```sh
python3 -m venv .audit-venv
.audit-venv/bin/python -m pip install pip-audit
.audit-venv/bin/python -m pip_audit --disable-pip --no-deps -r requirements.txt
.audit-venv/bin/python -m pip_audit --disable-pip --no-deps -r requirements-dev.txt
```

The audit command assumes the requirements list includes the complete resolved
dependency set (the dev file includes the runtime file). Update and audit the
pins when dependencies change. Hash-locked requirements would further improve
installation integrity; these files currently pin versions without hashes.
Neither virtual environment should be committed.

## Interview answers

The interview answers are in
[Engineering_Intern_Interview_Questions.md](Engineering_Intern_Interview_Questions.md)
(Part 1 code review and Part 2 follow-up answers).

Potential later features include expression parsing with a vetted, restricted
parser, calculation history, copy-result controls, and scientific functions.
These are future ideas, not implemented features.

## Part 2 AI assistance record

This records the user prompts from this Part 2 conversation. AI outputs below
are summaries, not a verbatim transcript, and are not the candidate's personal
reflections. Part 1 is outside this project's scope.

### Prompt 1: Planning

> lets focus on part 2 of the intervuiiew - make a plan for the intyerview , please make a plan for the backend first , is it more wise tonsue the bmath linbrqayr or whast teh best way to get the calultor to work perfectly

The AI compared calculation approaches, asked clarifying questions, consulted
the official Python Decimal and Flask documentation, and proposed a
backend-first Flask/Decimal implementation with tests and explicit limits.
A read-only research subagent was used during planning.

The user selected **Python + Flask**, **Basic calculator: +, -, *, /**, and
clarified that the library question meant **Python math**. The final plan chose
`Decimal`, decimal strings at the API boundary, a stateless endpoint, controlled
errors, and a roughly 25-minute backend target. This was a target, not a claim
about actual elapsed time. A session-memory save failed because no workspace
was open; no implementation files were created during planning.

### Prompt 2: Implementation

> Start implementation

The AI created the calculation module and its tests first, ran the focused
tests, then added the Flask API and HTTP tests. It installed dependencies in a
local virtual environment, checked dependency compatibility and advisories,
started a localhost server, verified real responses, and wrote this document.
The candidate did not need to supply another corrective prompt during this step.

Observed limitations: the first server launch failed because the terminal tool
removed a directory change; the AI retried successfully with absolute paths.
An attempt to add the project to VS Code did not give this chat an attached
Pylance workspace, so editor import warnings could not be cleared here. Runtime
tests passed in the project's virtual environment. At that stage, frontend
implementation, public repository delivery, and the candidate's own assessment
of what the AI did well or poorly remained outstanding.

### Prompt 3: Frontend and security planning

> Im0plement the forntend and once we are done with th9is do end to end testing and make sure it is cyber secure

The user selected **Local interview demo** when asked about security/deployment
scope. The AI reviewed the backend and prepared the frontend, E2E, and security
plan using read-only research. It remained in Plan mode and did not implement
the frontend in that turn. Session-plan persistence failed without a workspace.

### Prompt 4: Frontend implementation

> Start implementation

The AI added the same-origin frontend, explicit calculator state machine,
centralized response headers and local Host validation, browser tests, dependency
pins, and documentation. It ran the real Flask API in Chromium and WebKit,
audited runtime/dev packages, inspected screenshots, and started the local demo.
No subagents were used for this implementation turn.

Observed challenges: long result announcements initially moved the keypad; the
AI changed them to accessible nonvisual announcements with a fixed status area.
WebKit screenshots triggered a tooling-induced CSP violation, which was verified
against installed Playwright source and isolated without weakening the policy.
A lint-driven callback simplification broke Playwright's wrapper for built-in
methods; ordinary Python functions fixed it, followed by another passing full run.
The final result and remaining gaps are recorded above, not a claim of perfect
arithmetic or absolute cybersecurity. Later prompts completed the interview
answers and published this repository.