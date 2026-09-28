"""Exercise both real installers with a fake network; never contact production."""
import contextlib
import io
import json
import os
from pathlib import Path
import textwrap
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse


ROOT = Path(__file__).resolve().parents[2]
GSC = ROOT / "cloud/gsc_root_route_20260928/controller.py"
SITEMAP = ROOT / ".github/workflows/seo_sitemap_route_audit.yml"


def installers():
    embedded = SITEMAP.read_text().split("python3 - <<'PY'\n", 1)[1]
    embedded = textwrap.dedent(embedded).rsplit("\nPY", 1)[0]
    return (
        ("gsc", GSC.read_text(), "/google609494476a22f741.html",
         "google-site-verification: google609494476a22f741.html"),
        ("sitemap", embedded, "/sitemap.xml", '<urlset xmlns="test"></urlset>'),
    )


class Response:
    def __init__(self, body, status=200):
        self.body, self.status = body, status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class RouteReloadTests(unittest.TestCase):
    def run_installer(self, case, mappings, *, public_body=None,
                      create_error=False, reload_timeout=False):
        name, source, route, expected = case
        calls, clock, output = [], [0], io.StringIO()

        def urlopen(request, timeout):
            url, method = request.full_url, request.get_method()
            calls.append((method, url, request.data))
            parsed = urllib.parse.urlsplit(url)
            if parsed.netloc == "www.pythonanywhere.com":
                if parsed.path.endswith("/static_files/") and method == "GET":
                    return Response(json.dumps(mappings).encode())
                if parsed.path.endswith("/static_files/") and method == "POST":
                    if create_error:
                        raise urllib.error.HTTPError(url, 500, "test", {}, io.BytesIO(b"test"))
                    return Response(b"{}", 201)
                if parsed.path.endswith("/reload/") and method == "POST":
                    if reload_timeout:
                        raise TimeoutError("test reload response timeout")
                    return Response(b"{}")
            if parsed.netloc == "www.uaart.com.ua" and parsed.path == route and method == "GET":
                body = expected if public_body is None else public_body
                return Response(body.encode())
            raise AssertionError("Unexpected request: " + method + " " + url)

        def sleep(seconds):
            clock[0] += seconds

        with patch.dict(os.environ, {"PA_TOKEN": "test", "PYTHONANYWHERE_API_TOKEN": "test"}, clear=True), \
                patch("urllib.request.urlopen", side_effect=urlopen), \
                patch("time.time", side_effect=lambda: clock[0]), \
                patch("time.sleep", side_effect=sleep), \
                contextlib.redirect_stdout(output):
            try:
                exec(compile(source, name, "exec"), {"__name__": "__main__"})
            except (SystemExit, urllib.error.HTTPError) as stopped:
                code = stopped.code
            else:
                self.fail("Installer did not report a result")
        return code, calls, output.getvalue()

    def test_existing_mapping_only_reads_and_still_verifies(self):
        for case in installers():
            route = case[2]
            path = "/home/Carix/video" + route
            for mappings in ([{"url": route, "path": path}], {route: path}):
                with self.subTest(installer=case[0], shape=type(mappings).__name__):
                    code, calls, output = self.run_installer(case, mappings)
                    self.assertEqual(code, 0)
                    self.assertEqual([call[0] for call in calls], ["GET", "GET"])
                    self.assertEqual(urllib.parse.urlsplit(calls[-1][1]).path, route)
                    self.assertIn("UNCHANGED_RELOAD_SKIPPED", output)

    def test_new_mapping_is_installed_and_reloaded_once(self):
        for case in installers():
            with self.subTest(installer=case[0]):
                code, calls, _ = self.run_installer(case, [])
                self.assertEqual(code, 0)
                self.assertEqual([call[0] for call in calls], ["GET", "POST", "POST", "GET"])
                self.assertEqual(urllib.parse.parse_qs(calls[1][2].decode()),
                                 {"url": [case[2]], "path": ["/home/Carix/video" + case[2]]})
                self.assertTrue(calls[2][1].endswith("/reload/"))

    def test_conflicting_mapping_fails_without_writes(self):
        for case in installers():
            with self.subTest(installer=case[0]):
                code, calls, _ = self.run_installer(case, [{"url": case[2], "path": "/wrong"}])
                self.assertIn("CONFLICT", str(code))
                self.assertEqual([call[0] for call in calls], ["GET"])

    def test_malformed_mapping_response_fails_without_writes(self):
        for case in installers():
            for mappings in (None, 42, [{}], {case[2]: None}):
                with self.subTest(installer=case[0], mappings=mappings):
                    code, calls, _ = self.run_installer(case, mappings)
                    self.assertEqual(code, "STATIC_ROUTES_INVALID_RESPONSE")
                    self.assertEqual([call[0] for call in calls], ["GET"])

    def test_failed_public_verification_does_not_reload_existing_mapping(self):
        for case in installers():
            with self.subTest(installer=case[0]):
                mappings = {case[2]: "/home/Carix/video" + case[2]}
                code, calls, _ = self.run_installer(case, mappings, public_body="unavailable")
                self.assertIn("VERIFY_TIMEOUT", str(code))
                self.assertTrue(all(call[0] == "GET" for call in calls))
                self.assertGreater(len(calls), 2)

    def test_failed_creation_never_reloads(self):
        for case in installers():
            with self.subTest(installer=case[0]):
                code, calls, _ = self.run_installer(case, [], create_error=True)
                self.assertNotEqual(code, 0)
                self.assertEqual([call[0] for call in calls], ["GET", "POST"])
                self.assertFalse(any(call[1].endswith("/reload/") for call in calls))

    def test_reload_timeout_checks_public_result_without_retrying_reload(self):
        for case in installers():
            with self.subTest(installer=case[0]):
                code, calls, _ = self.run_installer(case, [], reload_timeout=True)
                self.assertEqual(code, 0)
                self.assertEqual(sum(call[1].endswith("/reload/") for call in calls), 1)
                self.assertEqual(calls[-1][0], "GET")


if __name__ == "__main__":
    unittest.main()
