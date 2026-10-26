# Engineering Intern Interview Questions

## Introduction

Thank you for your interest in the Nucleus Security Engineering
internship program! This document contains 2 primary interview
challenges for you. The first is a code review question, and the second
is a coding challenge.

For both, we absolutely encourage the use of AI. If you do use AI, we
would like for you to share your prompts and then answer the follow-up
questions about how you thought through your prompts.

We know this time of the year is crazy for college students and that
your time is very valuable. Please try not to spend more than about 1
total hour collectively on this.

------------------------------------------------------------------------

## Contents

-   Introduction
-   Code Review (10 minutes)
    -   Task
    -   PHP
    -   Python
    -   Code comments
    -   Follow-up Questions
-   Coding Challenge (\~50 minutes)
    -   Exercise
    -   Follow-up questions
-   Delivery

------------------------------------------------------------------------

# Code Review (10 minutes)

You are welcome and encouraged to use AI for this section. If you do,
please provide your prompts and answer the questions in the follow-up
section.

## Task

Your colleague or team member was given the following task:

1.  Add a `/webhook` endpoint to receive vendor events about users who
    are vendors.

2.  Input data will look like:

    ``` json
    {"email":"a@b.com","role":"admin","metadata":{"source":"vendor"}}
    ```

3.  Verify signature header `X-Signature`.

4.  Parse JSON and upsert the user data.

5.  Store the raw payload for audit/debug.

They have opened a PR with the code below. Review the code and comment
on any issues you find.

**Note:** Both the PHP and Python do the same thing. You can choose to
review whichever one you want. It is not intended for you to review
both.

------------------------------------------------------------------------

## PHP

``` php
<?php
// webhook.php
require_once "db.php"; // provides $pdo (PDO instance)

// Config (dev defaults)
$WEBHOOK_SECRET = getenv("WEBHOOK_SECRET") ?: "dev-secret";
$DB_AUDIT_ENABLED = getenv("AUDIT_ENABLED") ?: "true";

function verify_signature($sig, $body, $secret) {
    // Vendor docs: SHA256(secret + body)
    $expected = hash("sha256", $secret . $body);
    return $expected == $sig; // simple compare
}

$method = $_SERVER["REQUEST_METHOD"] ?? "GET";
$path = parse_url($_SERVER["REQUEST_URI"], PHP_URL_PATH);

// Basic routing
if ($method !== "POST" || $path !== "/webhook") {
    http_response_code(404);
    echo "not found";
    exit;
}

$raw = file_get_contents("php://input"); // raw body string
$sig = $_SERVER["HTTP_X_SIGNATURE"] ?? "";

if (!verify_signature($sig, $raw, $WEBHOOK_SECRET)) {
    http_response_code(401);
    echo "bad sig";
    exit;
}

// Decode JSON
$payload = json_decode($raw, true);
$email = $payload["email"] ?? "";
$role = $payload["role"] ?? "user";

// Store raw payload for auditing / debugging
if ($DB_AUDIT_ENABLED) {
    $pdo->exec("INSERT INTO webhook_audit(email, raw_json) VALUES ('$email', '$raw')");
}

// Upsert user (simple)
$pdo->exec("INSERT INTO users(email, role) VALUES('$email', '$role')");

echo "ok";
```

------------------------------------------------------------------------

## Python

``` python
# app.py
import os
import json
import sqlite3
import hashlib
from flask import Flask, request

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "/tmp/app.db")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "dev-secret")  # default for dev

def get_db():
    return sqlite3.connect(DB_PATH)

def verify(sig, body: bytes) -> bool:
    # Vendor docs: SHA256(secret + body)
    expected = hashlib.sha256(
        (WEBHOOK_SECRET + body.decode("utf-8")).encode("utf-8")
    ).hexdigest()
    return expected == sig  # simple compare

@app.post("/webhook")
def webhook():
    raw = request.data  # bytes
    sig = request.headers.get("X-Signature", "")

    if not verify(sig, raw):
        return ("bad sig", 401)

    payload = json.loads(raw.decode("utf-8"))

    # Example payload:
    # {"email":"a@b.com","role":"admin","metadata":{"source":"vendor"}}
    email = payload.get("email", "")
    role = payload.get("role", "user")

    db = get_db()
    cur = db.cursor()

    # Store raw payload for auditing / debugging
    cur.execute(
        f"INSERT INTO webhook_audit(email, raw_json) VALUES ('{email}', '{raw.decode('utf-8')}')"
    )

    # Upsert user
    cur.execute(
        f"INSERT INTO users(email, role) VALUES('{email}', '{role}')"
    )

    db.commit()

    return ("ok", 200)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

------------------------------------------------------------------------

## Code comments

**Scope:** Python implementation only. Line numbers below refer to the
Python snippet in this Markdown document, counting from the beginning of
the document.

**Recommendation: Request changes.** The main blockers are unsafe SQL
construction, a predictable fallback secret, missing upsert behavior, a
missing vendor check, and incomplete validation and error handling. The
vendor's signing scheme is also weak and should be raised with them.

### 1. SQL injection in both database inserts

**Lines 168 and 173 - High priority**

Both queries insert request-controlled values directly into SQL using
f-strings. This allows data to change the meaning of a database command.
Even a legitimate apostrophe in metadata, such as `"vendor's update"`,
breaks the audit insert. Signature verification does not make the
message's contents safe to use as SQL.

Use parameter binding for both statements, not manual escaping:

```python
cur.execute(
    "INSERT INTO webhook_audit(email, raw_json) VALUES (?, ?)",
    (email, raw.decode("utf-8")),
)
cur.execute(
    "INSERT INTO users(email, role) VALUES (?, ?)",
    (email, role),
)
```

These examples fix SQL construction only; the user statement still needs
the upsert behavior described below. Reaching these queries requires an
accepted signature, but an attacker could influence signed vendor data
or obtain the secret. SQLite's rejection of multiple stacked statements
does not prevent injection within a single statement.

### 2. Fail startup when the webhook secret is missing

**Line 136 - High priority**

The application silently uses `"dev-secret"` when `WEBHOOK_SECRET` is
unset. If a reachable deployment uses that fallback, anyone who knows
the default can generate accepted signatures. An explicitly empty
environment variable is also accepted.

Require an explicitly configured, non-empty secret and stop startup with
a clear configuration error if it is absent. Supply it through protected
configuration or a secret manager, and never log it. The production
configuration is not supplied, so actual use of the fallback is a
conditional risk rather than an established deployment fact.

### 3. Implement the required upsert

**Lines 171 and 173 - Correctness blocker**

The comment says "Upsert user", but the statement only inserts. An
existing email will either cause a uniqueness error or allow duplicate
records, depending on the unseen schema; it will not update the user.

Confirm the unique user identifier. If it is email, enforce its uniqueness
and use a parameterized SQLite `INSERT ... ON CONFLICT(email) DO UPDATE`
statement. Test both a new user and an existing user whose role changes.

### 4. Validate the payload and the vendor's permissions

**Lines 156, 160 and 161**

Parsing JSON is not sufficient validation. Malformed JSON raises an
exception, and valid JSON such as `[]` or `null` is not an object on which
the handler can call `.get()`. Missing email silently becomes an empty
string, and field types are not checked.

Require a JSON object, a non-empty email string satisfying the agreed
validation rules, and a role permitted by the integration contract.
Define required fields and defaults explicitly. If metadata is provided,
validate its agreed shape as well.

The task says these events are about users who are vendors, but the
handler never reads `metadata`, so `metadata.source` is never checked.
Any signed event creates or changes a user, whatever its source. Confirm
the intended rule with the vendor contract; if only vendor users may be
managed, reject events whose `metadata.source` is not `"vendor"` before
any write.

Authentication establishes who sent a message; authorization determines
what that sender may change. Confirm which users and roles this vendor
may manage. The example explicitly includes `"admin"`, so accepting that
role is not automatically a bug; enforce the agreed policy rather than
inventing a restriction.

### 5. Verify signatures using raw bytes and a safe comparison

**Lines 144 and 146**

Decoding the body during signature verification can raise
`UnicodeDecodeError` before an invalid request is rejected. Calculate the
digest from the original bytes according to the vendor protocol, then
decode and parse the body after authentication:

```python
expected = hashlib.sha256(
    WEBHOOK_SECRET.encode("utf-8") + raw
).hexdigest()
```

Validate the supplied signature's documented format and use
`hmac.compare_digest` instead of `==` for timing-resistant comparison.
This is security hardening; a practical remote timing exploit has not
been demonstrated here.

Using `compare_digest` does not change the signing algorithm to HMAC.
The vendor specifies `SHA256(secret + body)`, which is a weak
construction: SHA-256 is vulnerable to length extension, so anyone who
sees one valid body and signature can compute a valid signature for that
body with extra bytes appended, without knowing the secret. In this
handler the forged body would contain SHA-256 padding bytes, which are
not valid UTF-8 and leave trailing data after the JSON object, so the
request would fail rather than be processed; a more lenient decoder or
parser could change that. Raise this with the vendor and recommend
HMAC-SHA256, which is designed to prevent it.
A move to HMAC requires agreement with the vendor; do not silently
change the protocol.

### 6. Guarantee transaction rollback and connection cleanup

**Lines 163, 167, 172 and 176**

Handle failures when opening the database, executing statements, and
committing. Roll back an active transaction on failure and always close
the connection, using a reliable context manager or `finally` block.
A SQLite connection's transaction context manager commits or rolls back
but does not itself close the connection.

The current two inserts already share an implicit transaction under the
normal connection defaults, followed by a single commit. Preserve that
all-or-nothing behavior; do not introduce a separate commit after the
audit insert. If auditing failed attempts must survive a user-write
failure, clarify that requirement and design it explicitly.

### 7. Return controlled errors and log failures safely

**Lines 150, 153, 156, 163, 176 and 178**

Use narrow exception handling and explicit validation rather than
catching everything and returning `"ok"`. Recommended responses are:

| Condition | Response |
|---|---|
| Missing, malformed or incorrect signature | `401`, without revealing the expected signature. |
| Authenticated body with invalid UTF-8, malformed JSON or invalid fields | `400`, with a safe validation message. |
| Unsupported content type, if JSON content type is required by the contract | `415`. |
| Request exceeding the configured size limit | `413`. |
| Unexpected database or processing failure | Generic `500`; use `503` only for a recognized transient failure when appropriate. |
| Processing successfully committed | `200`. |

Catch decoding and JSON errors explicitly. Handle database exceptions
with rollback and cleanup, and let unexpected failures reach a controlled
server-error handler. Log a correlation ID and useful, sanitized
diagnostic information, not the secret, signature, raw payload, or
unfiltered SQL containing user data.

The current success response correctly follows `commit()`; preserve
that ordering. Unhandled exceptions normally produce Flask's generic
`500`; this snippet does not establish that stack traces are exposed to
clients.

### 8. Define retry, duplicate-event and replay behavior

**Lines 149, 153 and 176**

A valid signature does not prove an event is new. Vendors may resend an
event after a lost response, and a captured signed request may be
submitted again. The handler shows no event-identity or freshness check.

Confirm the vendor's delivery contract. Where supported, use a vendor
event ID to recognize duplicate processing and record it atomically with
the user update. Validate signed timestamps if the protocol provides
them. Consider event ordering so an older update cannot overwrite newer
state. Do not invent required headers or fields without vendor agreement;
the example contains neither an event ID nor a timestamp.

### 9. Protect the required audit records

**Line 168**

Keeping the original payload is an explicit requirement, not itself a
defect. However, email and metadata may contain sensitive information.
Define restricted access, appropriate storage protection, retention and
deletion policies. Avoid copying the payload into ordinary application
logs.

Preserve the received content rather than reserializing the parsed JSON.
If byte-exact evidence is required, store the original bytes in a
compatible database column. Clarify that requirement before changing or
redacting the stored audit record.

### 10. Confirm resource limits and production deployment

**Lines 134, 135, 150 and 181**

No request-size limit is shown before the body is read into memory.
Configure an agreed maximum in Flask or the serving infrastructure,
reject oversized bodies, and verify appropriate rate limits to protect
processing capacity and audit storage. These controls could exist
outside this snippet and should be checked rather than assumed absent.

`app.run()` starts Flask's development server; use a production WSGI
server for deployment and verify HTTPS at the serving boundary.
Binding to `0.0.0.0` is not, by itself, a vulnerability, and debug mode
is not enabled in the shown code.

For persistent production records, configure a durable, access-controlled
database location rather than relying on `/tmp/app.db`. Confirm that
schema initialization creates the required tables and unique constraint;
opening a SQLite connection does not create those tables.

### Verification and recommended tests

Isolated Python and in-memory SQLite checks confirmed that an apostrophe
in metadata breaks the original audit query, malformed input raises the
described exceptions, and a duplicate insert with a unique email fails
instead of updating the role. Parameter binding preserved the quoted
payload correctly. The complete Flask endpoint was not run; its actual
database schema and deployment configuration were not supplied.

Before approval, add endpoint tests for valid and invalid signatures;
missing secret configuration; quoted input; malformed UTF-8 and JSON;
non-object payloads; missing or incorrectly typed fields; agreed role
restrictions; new and existing users; duplicate events; oversized bodies;
and database failures during connection, writing and commit. Verify the
response codes, absence of unintended writes, rollback and connection
cleanup, and that errors do not expose sensitive data.


------------------------------------------------------------------------

## Follow-up Questions

1.  Share your prompts and the AI outputs.
2.  For each prompt:
    -   Tell us what you were hoping for the AI to accomplish.
    -   Tell us what it actually did.
    -   Did you have to re-prompt it based on its output?
    -   If you had to change your approach, why?

### My approach

I set the direction of the review and made the key decisions about what
it should cover. The AI did the line-by-line analysis, ran isolated
checks, and drafted the comments under that direction. I worked in two
stages: first understanding the request flow and the database layer,
then evaluating correctness, security, and failure handling.

The decisions I made:

- **Python over PHP.** I chose to review the Python version.
- **Understand the system before judging it.** Flask was new to me, so
  before asking for findings I worked through routing, the request
  lifecycle, and the database API: connections, cursors, `execute()`,
  parameterized queries, commits, and rollbacks. That groundwork is what
  let me evaluate the SQL injection and upsert findings rather than
  repeat them.
- **Security and failure handling first.** I directed the review to
  prioritize cybersecurity and error handling over style, because this
  endpoint accepts external input and writes to the user table.
- **No finding without a concrete consequence.** I required each issue
  to be explained with a real example, such as an apostrophe breaking
  the SQL or a repeated insert failing instead of updating, before it
  went into the review.
- **Review comments, not a rewrite.** When a rewrite was offered, I chose
  review comments, because the task is a code review.
- **A second check against the requirements.** Before submitting, I had
  the review checked against the task again. That added two points: the
  code never checks that users are vendors, and the vendor's signing
  scheme is vulnerable to length extension.

### Prompts, AI outputs, and follow-up decisions

The substantive prompts below are paraphrased for readability. The AI
outputs are summaries, not a verbatim transcript. Editor-configuration
questions are omitted because they did not change the technical review.

**1. "Focus only on Part 1 and explain the Python code first. I do not
know how this framework works."**

- **What I wanted:** A clear explanation of the application's purpose
  and how the request moves through it.
- **What AI did:** Explained Flask, webhooks, signature checking, JSON
  parsing, and the SQLite writes, then walked through the code.
- **Follow-up and why:** The explanation covered many concepts at once.
  I narrowed my next questions to the framework and routing basics.

**2. "So this is just the Flask framework, right?"**

- **What I wanted:** Distinguish Flask functionality from other Python
  functionality.
- **What AI did:** Explained that Flask handles web requests and routing,
  while JSON parsing, hashing, and SQLite access use Python's standard
  library.
- **Follow-up and why:** I then asked specifically about `/webhook`,
  because I was still separating the framework from application code.

**3. "Is `/webhook` also Flask? Explain the basics needed to understand
Part 1."**

- **What I wanted:** Understand endpoints, HTTP requests, and the role
  of the route decorator.
- **What AI did:** Explained that `/webhook` is a developer-chosen URL
  path, Flask connects a matching request to a function, and a webhook
  is a communication pattern rather than a Flask-specific feature.
- **Follow-up and why:** I asked about server startup to complete my
  understanding of when the handler runs.

**4. "What does the ending with `app.run()` do?"**

- **What I wanted:** Understand how the application begins receiving
  requests.
- **What AI did:** Explained the main guard, host address, port, and
  development server. It clarified that starting the server does not
  immediately execute the webhook handler.
- **Follow-up and why:** I did not need another explanation of startup,
  so I moved on to the code review.

**5. "Review Part 1, find potential issues, and suggest code comments."**

- **What I wanted:** Identify concrete problems against the task's
  requirements, rather than focus on formatting or style.
- **What AI did:** Identified SQL injection, missing upsert behavior,
  the fallback secret, validation gaps, and database cleanup concerns.
  It supplied line references and ran isolated checks of malformed input
  and SQLite behavior.
- **Follow-up and why:** I asked for simpler explanations before using
  the findings. I wanted to understand their consequences, not just
  repeat security terminology.

**6. "Explain all the issues in simple terms first."**

- **What I wanted:** Understand why each finding mattered in practice.
- **What AI did:** Used examples such as an apostrophe breaking SQL, a
  repeated insert failing instead of updating a user, and a predictable
  default secret weakening authentication.
- **Follow-up and why:** The database findings exposed a gap in my
  understanding of the API, so I asked about the database commands next.

**7. "Explain the database commands, including cursors and `execute()`."**

- **What I wanted:** Connect the review findings to the actual Python
  operations.
- **What AI did:** Explained connections, cursors, SQL, parameterized
  queries, commits, rollbacks, and connection closure. It distinguished
  making an INSERT safe from implementing an upsert.
- **Follow-up and why:** I then requested a complete review with explicit
  attention to cybersecurity and error handling.

**8. "Give the complete Part 1 solution, including error handling, with
a major focus on cybersecurity."**

- **What I wanted:** Cover malicious input and failure paths, not only
  what happens when a valid request succeeds.
- **What AI did:** Performed a security-focused review and confirmed the
  unsafe SQL construction. It separated demonstrated issues from risks
  that depend on deployment or the vendor contract, including use of
  the fallback secret and permission to assign roles.
- **Follow-up and why:** When offered a rewrite or review comments, I
  chose comments to stay aligned with Part 1's requested deliverable.


### What I learned and would verify next

The main lesson was that authentication, validation, and authorization
solve different problems. A correctly signed message can still contain
data that must not be treated as SQL, invalid fields, or a change outside
the sender's agreed permissions. I also learned to check the actual
statement against the requirement: a comment saying "upsert" does not
make an INSERT update existing records.

The review also highlighted the importance of not overstating evidence.
The vendor's documented signing algorithm cannot simply be replaced
without coordination, and the example's `admin` role is not automatically
forbidden. Similarly, controls not visible in a short snippet might
exist elsewhere in the deployment.

AI ran isolated Python and in-memory SQLite checks; I did not
independently run those checks or start the full Flask application. The
actual database schema and deployment configuration were not supplied.
Before considering an implementation ready, I would verify the fixes
with endpoint tests for valid and invalid requests, existing users,
duplicate events, database failures, rollback, and safe error responses.

My prompting changed from a broad explanation to smaller questions and
then to a focused security review. That change was useful because a
long list of findings was not enough on its own: I needed to understand
the request and database flow to explain why the recommendations mattered.

------------------------------------------------------------------------

# Coding Challenge (\~50 minutes)

For the below coding exercise, there is no expectation that you will
have a fully working solution. For anything you feel you didn't
accomplish, please let us know in the follow-up section after the
exercise.

## Exercise

Build a calculator web application. It should include a frontend piece
and any backend logic needed to perform the calculations.

You can use any language of your choosing for both the frontend and
backend code.

------------------------------------------------------------------------

## Follow-up questions

1.  How far were you able to get with the exercise?
2.  What challenges did you encounter in the process?
3.  If you were given unlimited time, what additional functionality
    would you include?
4.  If you used AI, please include all of your prompts and answer the
    following questions:
    -   What did the AI do well?
    -   What did the AI do poorly?
    -   For the places it did poorly, how did you change your approach
        to your prompts to improve its output?

### My answers

**Repository:** https://github.com/techindes/calculator-and-code-review

**Time spent:** About 50 minutes. I spent that time steering the AI:
making the decisions, reviewing its output, and redirecting it, rather
than writing code by hand. That is how I work with AI in my current job,
and it is why the amount of code and tests is larger than 50 minutes of
hand-written work would produce.

#### 1. How far did I get?

I built a working calculator web application. The frontend is plain
HTML, CSS, and JavaScript. The backend is Python with Flask, and Flask
serves both the page and the calculation API. It supports addition,
subtraction, multiplication, and division, with a keypad, keyboard
input, decimals, negative numbers, clear, backspace, and a sign toggle.
Errors such as division by zero are shown and the calculator recovers.

The backend uses Python's `Decimal` rather than floating-point numbers,
so `0.1 + 0.2` returns `0.3`. Numbers stay as text from the browser,
through the API, and back, so JavaScript does not round them.

I also added automated tests: 56 passed in the final run, including 24
browser tests that exercise the real app in Chromium and WebKit. The
calculator runs locally; instructions are in the repository's README.

What I did not do or verify:

- It runs locally only. I did not deploy it or add HTTPS, a production
  web server, or rate limiting.
- I did not test on a real phone, in Firefox, or with a screen reader.
- Calculations are one operation at a time, executed left to right
  (`2 + 3 * 4 = 20`, not `14`). There is no operator precedence,
  parentheses, history, or scientific functions.
- Precision is 28 significant digits, so some results, such as `1 / 3`,
  are rounded. It is not unlimited precision.
- The security work is hardening and testing for a local demo. I do not
  claim the app is guaranteed secure.

#### 2. Challenges

- **Choosing the arithmetic approach.** I first asked whether Python's
  `math` library was the best way to make a calculator correct. I
  learned it is not the right tool for basic arithmetic, and that binary
  floating point causes errors like `0.1 + 0.2`. Using `Decimal` and
  text values fixed that, but it also required setting explicit limits
  (input length, precision, rounding) and documenting them.
- **Chaining and timing in the frontend.** Defining what happens when
  someone presses operators repeatedly, presses equals twice, or clicks
  Clear while a request is still running took careful decisions. A late
  response must not overwrite newer input, so each request is tracked
  and stale responses are ignored.
- **Layout with very long numbers.** A 100-digit result originally
  moved the keypad. The browser tests caught it and the layout was fixed
  to stay stable.
- **Security and testing details.** The Content Security Policy is
  strict, and one browser's screenshot tool injected a style that the
  policy correctly blocked. I kept the policy strict and handled the
  tool's one known exception in the test instead.
- **Scope.** The assignment says a fully working solution is not
  expected, but the work grew into a large test and security effort. I
  redirected the focus back to the assignment's questions at the end.
- **Setup.** My editor was not attached to the project's Python
  environment, so it showed import warnings even though the tests
  passed from the project's own environment.

#### 3. What I would add with unlimited time

- Full expressions with precedence and parentheses, using a vetted,
  restricted parser, never `eval`.
- Calculation history, copy result, percent, and memory functions, and
  possibly scientific functions.
- Deployment behind HTTPS with a production web server, rate limiting,
  and monitoring, followed by a proper security review.
- Continuous integration that runs the tests on every change, plus
  Firefox, real devices, and manual screen-reader testing.
- Hash-pinned dependencies and automatic vulnerability scanning.
- A clearer way to show precision limits and rounding to users.

#### 4. AI use

I made the architecture and engineering decisions; the AI wrote the
implementation to them, and I reviewed and redirected its output. The
decisions I made:

- **Backend first.** My first prompt asked for a backend plan before any
  frontend work, so the calculation logic and API were built and tested
  on their own before a UI depended on them.
- **Numerical correctness as a requirement.** I raised the arithmetic
  approach before any code was written, asking whether Python's `math`
  library was the best way to make the calculator correct. Evaluating
  that question led to `Decimal` with numbers kept as strings end to
  end, which is why `0.1 + 0.2` returns `0.3` and large integers are not
  rounded by JavaScript.
- **Stack and scope.** I chose Python and Flask for the backend and
  limited the calculator to the four basic operations.
- **End-to-end testing and security.** I required end-to-end testing and
  a security pass once the frontend was built, rather than stopping at
  "it works". That is why the app is tested in real browsers against the
  real backend, and those tests caught real bugs, such as long results
  shifting the keypad.
- **Threat model.** When security came up, I set the scope as a local
  demo rather than a public deployment, which decided which protections
  were in scope (input validation, request limits, Host checks, CSP) and
  which were not (HTTPS, rate limiting).
- **Reviewing the changes.** I had it list every file it changed so I
  could review the changes themselves rather than trust a summary.
- **Holding the scope.** When the testing and documentation grew beyond
  what the exercise needed, I pulled the work back to the assignment's
  deliverables, and later had the README cut down.

**All of my prompts, in order** (typos are mine and left as written):

1. > lets focus on part 2 of the intervuiiew - make a plan for the intyerview , please make a plan for the backend first , is it more wise tonsue the bmath linbrqayr or whast teh best way to get the calultor to work perfectly
2. Answers to the AI's clarifying questions: **Python + Flask**, **basic
   calculator (+, -, *, /)**, and that "bmath" meant **Python's `math`
   module**.
3. > Start implementation
4. > Im0plement the forntend and once we are done with th9is do end to end testing and make sure it is cyber secure
5. Answer to the AI's clarifying question: **Local interview demo**
   (not a public deployment).
6. > Start implementation
7. > which files did you change ?
8. > wiat this is for an inetrview and  i need to push ths so how do i do tihs and did you fill in teh inetrviuew quesi0tns
9. > io thinkm you made evrytong worke, the main port fo this exercisue was to copkeplte teh onerviuew questiosn we needed to focus on thst and it sghould just follow the instructions of teh assignment
10. > THis is a job interview quewstion and i want you to look at it and make sure evryhting is perfcet beifore i pouhs and make this rpoe adn giev the link
11. In a separate review session, I pasted the recruiter's email and asked
    the AI to check everything against the assignment and tell me which
    answers I needed to change.
12. > Yes, add the length-extension and vendor-check points to the code review, clean up the README and validation report, and show me the diff before pushing. I'll give you my real time spent.

The AI's outputs were long, so I am not pasting them verbatim. In summary:

- **Prompts 1-2:** compared approaches, recommended `Decimal` with string
  values over `math` or floats, and planned a backend-first Flask design.
- **Prompt 3:** built and tested the calculation module, then the API.
- **Prompts 4-6:** planned and built the frontend, browser tests and
  security headers, after I chose a local-demo scope.
- **Prompts 7-10:** listed the changed files, filled in these answers when
  I pointed out they were missing, reran the tests and published the repo.
- **Prompts 11-12:** added two missing code-review points (the vendor
  check and SHA-256 length extension), and cut the README down to what
  the assignment needs.

**What the AI did well**

- Compared approaches and recommended `Decimal` with text values instead
  of `math` or floats, and explained why.
- Built the backend, frontend, and tests quickly, and kept each piece
  small and readable.
- Tested the real app in real browsers, not only the API, including
  unusual cases such as slow, failed, and malformed responses.
- Found and fixed real problems through the tests, such as the layout
  shift with long numbers.
- Kept its claims honest in the documentation: it listed the limits, the
  untested areas, and said it could not guarantee security.

**What the AI did poorly**

- **It over-built.** I asked for a calculator and a security check; it
  produced a very large test suite, security documentation, and reports.
  That is more than a roughly 50-minute exercise calls for, and it was not the
  priority, which was answering the interview questions. It also did not
  fill in those questions until I pointed it out.
- **Tooling mistakes.** A server start failed because the terminal
  command lost its directory change; it worked around this with absolute
  paths. A lint-driven cleanup of the tests broke all the browser tests
  until it was reverted to a different form.
- **Unreliable helper output.** During planning, some research it gathered
  contained wrong claims, for example about how Flask handles
  non-JSON requests. They had to be checked against the code and tests
  and discarded.
- **Environment trouble.** It could not attach the editor to the right
  Python environment, which left false-looking warnings.

**How I changed my approach**

- I started broad ("make a plan") and then answered its questions to
  narrow the choices: language, operations, and the meaning of my
  "bmath" typo.
- When I asked for security, it asked whether this was local or public.
  Choosing **local demo** kept the scope reasonable.
- I asked it to list exactly which files it changed so I could review
  them instead of trusting a summary.
- At the end I redirected it to the assignment itself: complete the
  interview questions and follow the instructions, rather than keep
  improving the code.
- What I would do differently: state the time budget and deliverables in
  the first prompt, ask for the smallest working version first, and
  require each addition to be justified against the assignment.

#### Questions or thoughts about the exercise

The exercise was a good way to see how much correctness depends on small
decisions, like how numbers are stored and what happens when requests
overlap. I was unsure how much testing and security work was expected for
a roughly 50-minute exercise, and I would welcome feedback on that.

------------------------------------------------------------------------

# Delivery

Please reply to the email you received with:

1.  Answers to any follow-up above.
2.  Any questions or thoughts you had on the exercise.
3.  A link to a public GitHub repository including your answer to the
    coding challenge.
    -   If we can't get to the repository, we won't be able to consider
        your answer to the coding challenge.
