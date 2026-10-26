import json
import unittest
from pathlib import Path
from threading import Thread

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import WSGIRequestHandler, make_server

from app import create_app


ARTIFACTS = Path(__file__).parent / "test-artifacts"


class QuietHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        pass


class BrowserTests(unittest.TestCase):
    engine = "chromium"

    @classmethod
    def setUpClass(cls):
        cls.server = make_server("127.0.0.1", 0, create_app(), threaded=True, request_handler=QuietHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.stop_server)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = getattr(cls.playwright, cls.engine).launch()
        cls.addClassCleanup(cls.browser.close)
        ARTIFACTS.mkdir(exist_ok=True)

    @classmethod
    def stop_server(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        mobile = self._testMethodName == "test_touch_and_accessible_controls"
        self.context = self.browser.new_context(
            viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900},
            is_mobile=mobile, has_touch=mobile,
            reduced_motion="reduce",
        )
        self.addCleanup(self.context.close)
        self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
        self.context.add_init_script("""
            window.cspViolations = [];
            document.addEventListener('securitypolicyviolation', event => {
                window.cspViolations.push(event.effectiveDirective);
            });
        """)
        self.page = self.context.new_page()
        self.page.set_default_timeout(5000)
        self.addCleanup(self.capture)
        self.errors = []
        self.console_errors = []
        self.requests = []
        self.expected_csp = False
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("console", lambda message: self.console_errors.append(message.text) if message.type == "error" else None)
        def record_request(request):
            self.requests.append(request)

        self.page.on("request", record_request)
        self.page.goto(self.base_url)
        self.result = self.page.get_by_label("Result", exact=True)
        self.status = self.page.locator("#status")

    def capture(self):
        name = f"{self.engine}-{self._testMethodName}"
        if not self.page.is_closed():
            self.page.screenshot(path=str(ARTIFACTS / f"{name}.png"), full_page=True, caret="initial")
        self.context.tracing.stop(path=str(ARTIFACTS / f"{name}.zip"))

    def tearDown(self):
        self.assertEqual(self.errors, [])
        if not self.expected_csp:
            self.assertEqual(self.page.evaluate("window.cspViolations"), [])
        self.assertTrue(all(request.url.startswith(self.base_url + "/") for request in self.requests))

    def press(self, keys):
        for key in keys:
            self.page.keyboard.press(key)

    def screenshot_layout(self, suffix):
        self.assertEqual(self.page.evaluate("window.cspViolations"), [])
        self.page.screenshot(path=str(ARTIFACTS / f"{self.engine}-{suffix}.png"), full_page=True, caret="initial")
        expected = ["style-src-elem"] if self.engine == "webkit" else []
        self.assertEqual(self.page.evaluate("window.cspViolations"), expected)
        self.page.evaluate("window.cspViolations = []")

    def mock_response(self, status, content_type, body):
        self.page.route("**/api/calculate", lambda route: route.fulfill(
            status=status, content_type=content_type, body=body,
        ))

    def test_decimal_and_error_recovery(self):
        self.press("0.1+0.2=")
        expect(self.result).to_have_text("0.3")
        self.press("5/0=")
        expect(self.page.locator("#status")).to_have_text("Cannot divide by zero.")
        self.press("8*2=")
        expect(self.result).to_have_text("16")

    def test_assets_and_document(self):
        expect(self.page.get_by_role("heading", name="Calculator")).to_be_visible()
        self.assertEqual(self.console_errors, [])
        self.assertTrue(self.page.locator("img").evaluate_all("images => images.every(image => image.complete && image.naturalWidth > 0)"))
        self.assertEqual(self.page.locator("button").count(), 19)
        self.assertEqual(self.page.locator(".keypad").evaluate("element => getComputedStyle(element).display"), "grid")
        self.assertEqual(self.context.cookies(), [])
        self.assertEqual(self.page.evaluate("localStorage.length + sessionStorage.length"), 0)

    def test_keypad_operations_and_string_payloads(self):
        for name, expected in (("Add", "10"), ("Subtract", "6"), ("Multiply", "16"), ("Divide", "4")):
            with self.subTest(operator=name):
                self.page.get_by_role("button", name="Clear all", exact=True).click()
                self.page.get_by_role("button", name="8", exact=True).click()
                self.page.get_by_role("button", name=name, exact=True).click()
                self.page.get_by_role("button", name="2", exact=True).click()
                with self.page.expect_request("**/api/calculate") as sent:
                    self.page.get_by_role("button", name="Equals", exact=True).click()
                expect(self.result).to_have_text(expected)
                self.assertEqual(sent.value.method, "POST")
                self.assertEqual(sent.value.post_data_json["left"], "8")
                self.assertEqual(sent.value.post_data_json["right"], "2")
        self.assertEqual(self.console_errors, [])

    def test_precision_and_chaining(self):
        self.press("9007199254740993+1=")
        expect(self.result).to_have_text("9007199254740994")
        self.press("1/3=")
        expect(self.result).to_have_text("0." + "3" * 28)
        self.press("2+3*")
        expect(self.result).to_have_text("5")
        expect(self.page.get_by_role("button", name="4", exact=True)).to_be_enabled()
        self.press("4=")
        expect(self.result).to_have_text("20")
        self.press("0.1+0.2=")
        expect(self.result).to_have_text("0.3")
        self.press("+0.1=")
        expect(self.result).to_have_text("0.4")

    def test_keyboard_editing_and_operator_policy(self):
        self.press("5+=")
        self.assertFalse(any(request.method == "POST" for request in self.requests))
        self.press("-2=")
        expect(self.result).to_have_text("3")
        self.press("===")
        self.assertEqual(sum(request.method == "POST" for request in self.requests), 1)
        self.page.keyboard.press("Backspace")
        expect(self.result).to_have_text("3")
        self.press("7")
        self.page.keyboard.press("F9")
        expect(self.result).to_have_text("-7")
        self.page.keyboard.press("Backspace")
        expect(self.result).to_have_text("0")
        self.press("..25")
        expect(self.result).to_have_text("0.25")
        self.page.keyboard.press("Backspace")
        expect(self.result).to_have_text("0.2")
        self.page.keyboard.press("Escape")
        self.press("5+")
        self.page.keyboard.press("F9")
        self.press("2=")
        expect(self.result).to_have_text("3")
        self.page.get_by_role("button", name="Change sign").click()
        expect(self.result).to_have_text("-3")
        self.press("*2=")
        expect(self.result).to_have_text("-6")

    def test_pending_clear_and_stale_response(self):
        self.page.evaluate("""() => {
            const originalFetch = window.fetch.bind(window);
            window.fetchCount = 0;
            window.fetch = (...args) => {
                window.fetchCount += 1;
                if (window.fetchCount === 1) {
                    return new Promise(resolve => {
                        window.releaseResponse = () => resolve(new Response(
                            JSON.stringify({result: '999'}),
                            {headers: {'Content-Type': 'application/json'}}
                        ));
                    });
                }
                return originalFetch(...args);
            };
        }""")
        self.press("1+2=")
        expect(self.status).to_have_text("Calculating...")
        expect(self.page.get_by_role("button", name="Equals", exact=True)).to_be_disabled()
        self.press("===987")
        self.assertEqual(self.page.evaluate("window.fetchCount"), 1)
        self.page.get_by_role("button", name="Clear all", exact=True).click()
        expect(self.result).to_have_text("0")
        self.press("2+2=")
        expect(self.result).to_have_text("4")
        self.page.evaluate("async () => { window.releaseResponse(); await new Promise(resolve => setTimeout(resolve, 0)); }")
        expect(self.result).to_have_text("4")
        expect(self.page.get_by_role("button", name="Equals", exact=True)).to_be_enabled()

    def test_timeout_and_network_recovery(self):
        held = []

        def hold_request(route):
            held.append(route)

        self.page.clock.install()
        self.page.route("**/api/calculate", hold_request)
        self.press("1+2=")
        expect(self.status).to_have_text("Calculating...")
        self.page.clock.fast_forward(10001)
        expect(self.status).to_have_text("Request timed out. Try again.")
        for route in held:
            route.abort()
        self.page.unroute("**/api/calculate")
        self.page.route("**/api/calculate", lambda route: route.abort("failed"))
        self.press("3+4=")
        expect(self.status).to_have_text("Unable to calculate. Try again.")
        self.page.unroute("**/api/calculate")
        self.press("4+5=")
        expect(self.result).to_have_text("9")

    def test_untrusted_responses_are_rejected(self):
        cases = [
            (200, "text/html", "<html>Unexpected page</html>"),
            (200, "application/json", "{"),
            (200, "application/json", "null"),
            (200, "application/json", "[]"),
            (500, "application/json", json.dumps({"error": "UNKNOWN", "message": "private detail"})),
        ]
        for result in (None, True, 2, [], {}, "", "NaN", "Infinity", "1e2", "1\n", "1" * 101, '<img id="injected" src=x onerror="window.injected=true">'):
            cases.append((200, "application/json", json.dumps({"result": result})))
        cases.append((200, "application/json", json.dumps({"result": "3", "extra": True})))
        for status, content_type, body in cases:
            with self.subTest(status=status, body=body):
                self.mock_response(status, content_type, body)
                self.press("1+2=")
                expect(self.status).to_have_text("Unable to calculate. Try again.")
                expect(self.result).to_have_text("0")
                self.assertEqual(self.page.locator("#injected").count(), 0)
                self.assertIsNone(self.page.evaluate("window.injected"))
                self.page.unroute("**/api/calculate")
        self.page.route("**/api/calculate", lambda route: route.fulfill(
            status=422, json={"error": "DIVISION_BY_ZERO", "message": "<script>private detail</script>"},
        ))
        self.press("1/0=")
        expect(self.status).to_have_text("Cannot divide by zero.")
        self.assertNotIn("private detail", self.page.locator("body").inner_text())
        self.page.unroute("**/api/calculate")
        self.press("2+3=")
        expect(self.result).to_have_text("5")

    def test_responsive_long_number_layout(self):
        for width, height in ((1440, 900), (390, 844), (320, 568), (844, 390)):
            with self.subTest(viewport=(width, height)):
                self.page.set_viewport_size({"width": width, "height": height})
                self.page.keyboard.press("Escape")
                self.screenshot_layout(f"{width}-initial")
                keypad_top = self.page.locator("#keypad").bounding_box()["y"]
                number = "1" + "0" * 99
                self.press(number)
                expect(self.result).to_have_text(number)
                self.press("1")
                expect(self.result).to_have_text(number)
                expect(self.status).to_have_text("Maximum 100 characters.")
                self.press("*1=")
                expect(self.status).to_contain_text("Result:")
                expect(self.result).to_have_text(number)
                self.assertAlmostEqual(self.page.locator("#keypad").bounding_box()["y"], keypad_top, delta=1)
                self.assert_layout()
                self.screenshot_layout(f"{width}-long")
                self.press("5/0=")
                expect(self.status).to_have_text("Cannot divide by zero.")
                self.assert_layout()
                self.screenshot_layout(f"{width}-error")

    def assert_layout(self):
        geometry = self.page.evaluate("""() => {
            const bounds = element => {
                const rect = element.getBoundingClientRect();
                return {left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height};
            };
            return {
                width: innerWidth, pageWidth: document.documentElement.scrollWidth,
                display: bounds(document.querySelector('.display')),
                result: bounds(document.querySelector('#result')),
                status: bounds(document.querySelector('#status')),
                keypad: bounds(document.querySelector('#keypad')),
                buttons: [...document.querySelectorAll('button')].map(bounds),
            };
        }""")
        self.assertLessEqual(geometry["pageWidth"], geometry["width"])
        self.assertLessEqual(geometry["result"]["bottom"], geometry["display"]["bottom"])
        self.assertGreaterEqual(geometry["result"]["top"], geometry["display"]["top"] + 48)
        self.assertLessEqual(geometry["status"]["bottom"], geometry["keypad"]["top"])
        for button in geometry["buttons"]:
            self.assertGreaterEqual(button["width"], 44)
            self.assertGreaterEqual(button["height"], 44)
            self.assertGreaterEqual(button["left"], 0)
            self.assertLessEqual(button["right"], geometry["width"])

    def test_touch_and_accessible_controls(self):
        self.page.emulate_media(reduced_motion="reduce")
        self.assertEqual(self.page.locator(".workspace").evaluate("element => getComputedStyle(element).animationName"), "none")
        self.page.keyboard.press("Alt+Tab" if self.engine == "webkit" else "Tab")
        clear = self.page.get_by_role("button", name="Clear all", exact=True)
        expect(clear).to_be_focused()
        self.assertEqual(clear.evaluate("element => getComputedStyle(element).outlineStyle"), "solid")
        for name in ("8", "Divide", "2", "Equals"):
            self.page.get_by_role("button", name=name, exact=True).tap()
        expect(self.result).to_have_text("4")
        self.assertEqual(self.status.get_attribute("aria-live"), "polite")
        clear.focus()
        self.page.keyboard.press("Space")
        expect(self.result).to_have_text("0")
        self.assert_layout()

    def test_csp_blocks_inline_script(self):
        self.expected_csp = True
        self.page.evaluate("""() => {
            const script = document.createElement('script');
            script.textContent = 'window.inlineExecuted = true';
            document.body.append(script);
        }""")
        self.page.wait_for_function("window.cspViolations.length > 0")
        self.assertIsNone(self.page.evaluate("window.inlineExecuted"))
        self.assertTrue(any("script-src" in directive for directive in self.page.evaluate("window.cspViolations")))
        self.press("1+2=")
        expect(self.result).to_have_text("3")

    def test_frame_embedding_is_blocked(self):
        self.expected_csp = True
        self.page.route("**/frame-probe", lambda route: route.fulfill(
            content_type="text/html", body='<iframe src="/"></iframe>',
        ))
        with self.page.expect_console_message(predicate=lambda message: "frame" in message.text.lower()):
            self.page.goto(self.base_url + "/frame-probe")
        self.assertEqual(self.page.frame_locator("iframe").get_by_role("button").count(), 0)


class WebKitTests(BrowserTests):
    engine = "webkit"


if __name__ == "__main__":
    unittest.main()