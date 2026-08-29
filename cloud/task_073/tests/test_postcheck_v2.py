"""Offline unit tests for cloud/task_073/tools/postcheck_v2.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import postcheck_v2 as postcheck  # noqa: E402


def _fake_fetcher_factory(status_by_url):
    def _fetch(url, timeout=10.0):
        status, final_url = status_by_url.get(url, (404, url))
        return postcheck.VerifyResult(url=url, ok=(status == 200), reason=f"status:{status}",
                                       final_url=final_url, status=status)
    return _fetch


class TestPostcheck(unittest.TestCase):
    def test_verify_card_success(self):
        fetcher = _fake_fetcher_factory({
            "https://uaartlogistics.com/video/UA-0011.html": (200, "https://uaartlogistics.com/video/UA-0011.html"),
        })
        result = postcheck.verify_card("https://uaartlogistics.com", "UA-0011", "rev1", fetcher=fetcher)
        self.assertTrue(result.ok)

    def test_verify_card_redirect_to_home_is_failure(self):
        def fetcher(url, timeout=10.0):
            return postcheck.VerifyResult(url=url, ok=False, reason="http_error:302:redirected to home/index",
                                           final_url="https://uaartlogistics.com/video/index.html", status=302)
        result = postcheck.verify_card("https://uaartlogistics.com", "UA-0011", "rev1", fetcher=fetcher)
        self.assertFalse(result.ok)

    def test_immediate_and_delayed_verify_uses_delay(self):
        calls = []

        def fake_sleep(seconds):
            calls.append(seconds)

        fetcher = _fake_fetcher_factory({
            "https://uaartlogistics.com/video/UA-0011.html": (200, "https://uaartlogistics.com/video/UA-0011.html"),
            "https://uaartlogistics.com/video/UA-0011-diag.html": (200, "https://uaartlogistics.com/video/UA-0011-diag.html"),
        })
        result = postcheck.immediate_and_delayed_verify(
            "https://uaartlogistics.com", "UA-0011", "rev1",
            delay_seconds=60.0, sleep_fn=fake_sleep, fetcher=fetcher,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(calls, [60.0])


if __name__ == "__main__":
    unittest.main()
