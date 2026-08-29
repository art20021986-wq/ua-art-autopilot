import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import postcheck_v3 as pc  # noqa: E402


def _make_response(status_code, text, url):
    response = types.SimpleNamespace()
    response.status_code = status_code
    response.text = text
    response.url = url
    return response


class TestPostcheckPrimary(unittest.TestCase):
    def test_pass_when_marker_and_cta_present(self):
        url = "https://example.test/video/UA-0011.html"
        body = '<html><a href="UA-0011-diag.html">diag</a>UA-0011</html>'
        with mock.patch.object(pc, "_fetch", return_value=_make_response(200, body, url)):
            result = pc.verify_primary(url, "UA-0011", "UA-0011-diag.html")
        self.assertTrue(result.ok)

    def test_fail_on_redirect(self):
        url = "https://example.test/video/UA-0011.html"
        body = "UA-0011"
        with mock.patch.object(
            pc, "_fetch", return_value=_make_response(200, body, "https://example.test/video/index.html")
        ):
            result = pc.verify_primary(url, "UA-0011", "UA-0011-diag.html")
        self.assertFalse(result.ok)

    def test_fail_on_non_200(self):
        url = "https://example.test/video/UA-0011.html"
        with mock.patch.object(pc, "_fetch", return_value=_make_response(404, "", url)):
            result = pc.verify_primary(url, "UA-0011", "UA-0011-diag.html")
        self.assertFalse(result.ok)


class TestPostcheckDiagnostics(unittest.TestCase):
    def test_pass_with_placeholder(self):
        url = "https://example.test/video/UA-0011-diag.html"
        body = "UA-0011 Материалы диагностики пока не добавлены."
        with mock.patch.object(pc, "_fetch", return_value=_make_response(200, body, url)):
            result = pc.verify_diagnostics(url, "UA-0011", "Материалы диагностики пока не добавлены.")
        self.assertTrue(result.ok)


class TestPostcheckCatalog(unittest.TestCase):
    def test_pass_exact_one_href(self):
        url = "https://example.test/video/katalog.html"
        body = '<li><a href="UA-0011.html">UA-0011</a></li>'
        with mock.patch.object(pc, "_fetch", return_value=_make_response(200, body, url)):
            result = pc.verify_catalog(url, "UA-0011.html")
        self.assertTrue(result.ok)

    def test_fail_on_duplicate_href(self):
        url = "https://example.test/video/katalog.html"
        body = '<a href="UA-0011.html">a</a><a href="UA-0011.html">b</a>'
        with mock.patch.object(pc, "_fetch", return_value=_make_response(200, body, url)):
            result = pc.verify_catalog(url, "UA-0011.html")
        self.assertFalse(result.ok)


class TestImmediateAndDelayed(unittest.TestCase):
    def test_immediate_and_delayed_pass_with_fake_sleep(self):
        primary_url = "https://example.test/video/UA-0011.html"
        diag_url = "https://example.test/video/UA-0011-diag.html"
        catalog_url = "https://example.test/video/katalog.html"

        def fake_fetch(url, timeout=15):
            if url == primary_url:
                return _make_response(200, 'UA-0011<a href="UA-0011-diag.html">d</a>', primary_url)
            if url == diag_url:
                return _make_response(200, "UA-0011 Материалы диагностики пока не добавлены.", diag_url)
            return _make_response(200, '<a href="UA-0011.html">c</a>', catalog_url)

        sleeps = []
        with mock.patch.object(pc, "_fetch", side_effect=fake_fetch):
            ok = pc.verify_immediate_and_delayed(
                primary_url,
                diag_url,
                catalog_url,
                "UA-0011",
                "Материалы диагностики пока не добавлены.",
                delay_seconds=60,
                sleep_fn=sleeps.append,
            )
        self.assertTrue(ok)
        self.assertEqual(sleeps, [60])


if __name__ == "__main__":
    unittest.main()
