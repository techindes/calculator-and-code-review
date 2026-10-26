# Runtime Validation Report

Date: 2026-10-26. Target: local Flask calculator interview demo.

## Verdict

| Check | Verdict | Exit Code | Evidence |
|---|---|---|---|
| Startup | PASS | n/a (server running) | Loopback server on port 5051, debug off, HTML HTTP 200 |
| Arithmetic/API | PASS | 0 (combined suite) | 32 tests, including original 27 and new route/security checks |
| Browser | PASS | 0 (combined suite) | 24 tests across Chromium/WebKit, including real E2E and isolated fault probes |
| Full suite | PASS | 0 | 56 passed, 0 failed, 0 skipped; final run 16.454 seconds |
| Dependency compatibility | PASS | 0 | pip check: no broken requirements |
| Runtime advisory scan | PASS | 0 | Seven pinned packages; no known vulnerabilities found |
| Development advisory scan | PASS | 0 | Eleven pinned packages including runtime; no known vulnerabilities found |

Overall: PASS for the implemented local-demo automated acceptance suite.
This is not certification of public deployment security or exhaustive testing.

## Environment and Replay

- macOS, Python 3.14.0, Flask 3.1.3, Werkzeug 3.1.9.
- Python Playwright 1.64.1; Chromium 156.0.8078.4 and WebKit 27.2 installed.
- Primary browser stack used: Python Playwright with unittest; no HTTP-only fallback.
- No separate Node project, database, Docker, or authentication tier applies.
- Browser tests own an ephemeral loopback Flask server and fresh browser contexts.
- Existing tests were reused/extended; one browser test module shares lifecycle
  helpers instead of introducing redundant files or inapplicable auth/persistence tests.

```sh
.venv/bin/python -m unittest discover -v
.venv/bin/python -m pip check
.audit-venv/bin/python -m pip_audit --disable-pip --no-deps -r requirements.txt
.audit-venv/bin/python -m pip_audit --disable-pip --no-deps -r requirements-dev.txt
```

## Coverage and Artifacts

Real browser flows cover string-preserving arithmetic, precision, chaining,
operator replacement, keyboard/touch input, error recovery, and long-number layout.
Separate injected-fault tests cover timeout, network loss, stale responses and
untrusted response bodies. Security probes verify inline-script and frame blocking.

Both engines check 1440x900, 390x844, 320x568, and 844x390 viewports. The ignored
`test-artifacts/` directory contains per-test screenshots/traces and viewport
initial/long-result/error screenshots. Representative images were visually inspected.
The README provides installation and trace-viewer commands.

The initial expanded run found a long-announcement layout shift, a WebKit keyboard
navigation assumption and screenshot-injected CSP events. These were corrected.
One later callback cleanup introduced a Playwright built-in-method wrapper failure;
ordinary function callbacks repaired it. The final full run passed.

Playwright's WebKit screenshot helper inserts inline `body {}`. Tests assert the
single expected screenshot CSP event and reject additional events. Normal flows
retain strict CSP; inline-script/frame probes intentionally cause security blocking.

## Limits

No physical-device, Firefox, native 200% zoom, manual screen-reader, exhaustive
penetration/load, or production deployment testing was performed. Screenshots are
visual evidence, not a complete accessibility audit. Editor Python import warnings
remain a workspace/interpreter issue separate from passing venv runtime checks.
Dependency scans are point-in-time and cannot establish that no vulnerabilities exist.
The validation scope excludes the interview answers document.