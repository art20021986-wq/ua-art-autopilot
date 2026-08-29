import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import public_verifier as pv


class FakeResponse:
    def __init__(self, status_code=200, body="", redirected_to_home=False, revision_header=""):
        self.status_code = status_code
        self.body = body
        self.redirected_to_home = redirected_to_home
        self.revision_header = revision_header


class TestPublicVerifier(unittest.TestCase):
    def test_verify_pass(self):
        def fetch(url):
            return FakeResponse(200, "UA-0011 content", False, "rev123")

        outcome = pv.verify_public_page(fetch, "http://example/UA-0011.html", "UA-0011", "rev123")
        self.assertTrue(outcome.ok)

    def test_verify_fail_on_redirect(self):
        def fetch(url):
            return FakeResponse(200, "home content", True, "rev123")

        outcome = pv.verify_public_page(fetch, "http://example/UA-0011.html", "UA-0011", "rev123")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.reason, "redirected_to_home")

    def test_verify_fail_on_stale_revision(self):
        def fetch(url):
            return FakeResponse(200, "UA-0011 content", False, "old_rev")

        outcome = pv.verify_public_page(fetch, "http://example/UA-0011.html", "UA-0011", "rev123")
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.reason, "stale_revision")

    def test_verify_fail_on_non_200(self):
        def fetch(url):
            return FakeResponse(404, "", False, "rev123")

        outcome = pv.verify_public_page(fetch, "http://example/UA-0011.html", "UA-0011", "rev123")
        self.assertFalse(outcome.ok)

    def test_immediate_and_delayed_pass(self):
        calls = {"count": 0}

        def fetch(url):
            calls["count"] += 1
            return FakeResponse(200, "UA-0011 content", False, "rev123")

        def fake_sleep(seconds):
            pass

        outcome = pv.immediate_and_delayed_verify(
            fetch, "http://example/UA-0011.html", "UA-0011", "rev123", sleep_fn=fake_sleep, delay_seconds=60
        )
        self.assertTrue(outcome.ok)
        self.assertEqual(calls["count"], 2)

    def test_delayed_verify_failure_no_false_success(self):
        calls = {"count": 0}

        def fetch(url):
            calls["count"] += 1
            if calls["count"] == 1:
                return FakeResponse(200, "UA-0011 content", False, "rev123")
            return FakeResponse(200, "UA-0011 content", False, "stale_rev")

        def fake_sleep(seconds):
            pass

        outcome = pv.immediate_and_delayed_verify(
            fetch, "http://example/UA-0011.html", "UA-0011", "rev123", sleep_fn=fake_sleep, delay_seconds=60
        )
        self.assertFalse(outcome.ok)


if __name__ == "__main__":
    unittest.main()
