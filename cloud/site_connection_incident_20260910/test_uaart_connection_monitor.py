"""Functional regression tests. All network operations are stubbed."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

import uaart_connection_monitor as monitor


GOOD_HTML = b"<!doctype html><html><head><title>UA ART</title></head><body>" + b"a" * 600 + b"</body></html>"


class FakeResponse:
    def __init__(self, url, status=200, body=GOOD_HTML, content_type="text/html; charset=utf-8"):
        self.status, self.body, self.url = status, body, url
        self.headers = {"Content-Type": content_type}
        self.read_limit = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, limit):
        self.read_limit = limit
        return self.body[:limit]


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.requests = response, error, []

    def open(self, request, timeout):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.response


def stub_result(endpoint, ok, category=None):
    return {"endpoint": endpoint.name, "requested_url": endpoint.url,
            "ok": ok, "category": category or ("healthy" if ok else "connection_error")}


class ProbeTests(unittest.TestCase):
    def test_root_reaching_wrong_path_fails_despite_http_200(self):
        endpoint = monitor.ENDPOINTS[0]
        result = monitor.probe_once(endpoint, opener=FakeOpener(FakeResponse("https://www.uaart.com.ua/")))
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "unexpected_destination")
        self.assertEqual(result["http_status"], 200)

    def test_correct_path_on_wrong_host_fails(self):
        endpoint = monitor.ENDPOINTS[0]
        result = monitor.probe_once(endpoint, opener=FakeOpener(FakeResponse("https://uaart.com.ua/video/index.html")))
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "unexpected_destination")

    def test_certificate_error_is_visible_without_an_http_response(self):
        error = URLError(ssl.SSLCertVerificationError(1, "certificate verify failed: hostname mismatch"))
        result = monitor.probe_once(monitor.ENDPOINTS[1], opener=FakeOpener(error=error))
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "tls_error")
        self.assertIn("hostname mismatch", result["error"])
        self.assertIn("finished_at", result)

    def test_each_valid_probe_has_unique_cache_buster(self):
        endpoint = monitor.ENDPOINTS[2]
        opener = FakeOpener(FakeResponse(endpoint.expected_final_url))
        self.assertTrue(monitor.probe_once(endpoint, opener=opener)["ok"])
        self.assertTrue(monitor.probe_once(endpoint, opener=opener)["ok"])
        nonces = [parse_qs(urlsplit(request.full_url).query)["uaart_probe"][0] for request in opener.requests]
        self.assertNotEqual(nonces[0], nonces[1])
        self.assertIn("no-cache", opener.requests[0].get_header("Cache-control"))

    def test_oversized_response_fails_with_bounded_read(self):
        endpoint = monitor.ENDPOINTS[2]
        response = FakeResponse(endpoint.expected_final_url, body=GOOD_HTML + b"a" * monitor.MAX_HTML_BYTES)
        result = monitor.probe_once(endpoint, opener=FakeOpener(response))
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "invalid_body_size")
        self.assertEqual(response.read_limit, monitor.MAX_HTML_BYTES + 1)

    def test_non_html_200_is_not_healthy(self):
        endpoint = monitor.ENDPOINTS[3]
        result = monitor.probe_once(endpoint, opener=FakeOpener(FakeResponse(endpoint.expected_final_url, content_type="application/json")))
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "unexpected_content_type")

    def test_bogus_html_200_is_not_healthy(self):
        endpoint = monitor.ENDPOINTS[2]
        placeholder = GOOD_HTML.replace(b"<title>UA ART</title>", b"<title>Maintenance</title>")
        result = monitor.probe_once(endpoint, opener=FakeOpener(FakeResponse(endpoint.expected_final_url, body=placeholder)))
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "unexpected_page")

    def test_http_downgrade_is_blocked_before_following_redirect(self):
        handler = monitor.SafeRedirectHandler()
        request = monitor.Request(monitor.ENDPOINTS[0].url)
        with self.assertRaises(monitor.RedirectPolicyError):
            handler.redirect_request(request, None, 301, "", {}, "http://www.uaart.com.ua/video/index.html")
        self.assertEqual(len(handler.history), 1)

    def test_hard_timeout_is_returned_as_evidence(self):
        with patch.object(monitor.subprocess, "run", side_effect=subprocess.TimeoutExpired("probe", 20)):
            result = monitor.isolated_probe(monitor.ENDPOINTS[0], 20)
        self.assertFalse(result["ok"])
        self.assertEqual(result["category"], "timeout")
        self.assertIn("wall-clock", result["error"])


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "artifacts" / "result.json"

    def tearDown(self):
        self.temp.cleanup()

    def saved(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_persistent_failure_keeps_three_complete_rounds(self):
        delays = []

        def probe(endpoint, timeout):
            return stub_result(endpoint, endpoint.name != "apex_root")

        report = monitor.run_monitor(self.path, probe=probe, sleep=delays.append)
        self.assertEqual(report["status"], "persistent_failure")
        self.assertEqual(report["exit_code"], 2)
        self.assertEqual(delays, [15, 15])
        self.assertEqual(len(report["rounds"]), 3)
        self.assertTrue(all(len(r["results"]) == 4 for r in report["rounds"]))
        self.assertEqual(self.saved(), report)

    def test_transient_recovery_preserves_first_failure_and_stops(self):
        count = {}
        lock = threading.Lock()
        delays = []

        def probe(endpoint, timeout):
            with lock:
                count[endpoint.name] = count.get(endpoint.name, 0) + 1
                current = count[endpoint.name]
            return stub_result(endpoint, current > 1 or endpoint.name != "www_root")

        report = monitor.run_monitor(self.path, probe=probe, sleep=delays.append)
        self.assertEqual(report["status"], "recovered_transient")
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(delays, [15])
        self.assertEqual([r["ok"] for r in report["rounds"]], [False, True])
        self.assertEqual(set(count.values()), {2})
        self.assertEqual(self.saved(), report)

    def test_healthy_pass_has_no_retries(self):
        delays = []
        report = monitor.run_monitor(self.path, probe=lambda endpoint, timeout: stub_result(endpoint, True), sleep=delays.append)
        self.assertEqual(report["status"], "healthy")
        self.assertEqual(len(report["rounds"]), 1)
        self.assertEqual(delays, [])
        self.assertEqual(self.saved(), report)

    def test_probe_exception_is_recorded_and_other_pages_are_checked(self):
        def probe(endpoint, timeout):
            if endpoint.name == "catalog":
                raise RuntimeError("broken probe worker")
            return stub_result(endpoint, True)

        report = monitor.run_monitor(self.path, attempts=1, probe=probe)
        self.assertEqual(report["status"], "persistent_failure")
        self.assertEqual(len(report["rounds"][0]["results"]), 4)
        self.assertEqual(report["rounds"][0]["results"][3]["category"], "probe_error")
        self.assertEqual(self.saved(), report)

    def test_evidence_exists_before_retry_wait(self):
        observed = []

        def sleep(delay):
            observed.append(self.saved())
            raise RuntimeError("scheduler interrupted")

        report = monitor.run_monitor(self.path, probe=lambda endpoint, timeout: stub_result(endpoint, False), sleep=sleep)
        self.assertEqual(len(observed), 1)
        self.assertEqual(len(observed[0]["rounds"]), 1)
        self.assertEqual(report["status"], "monitor_error")
        self.assertEqual(self.saved(), report)

    def test_probes_run_in_parallel(self):
        rendezvous = threading.Barrier(len(monitor.ENDPOINTS))

        def probe(endpoint, timeout):
            rendezvous.wait(timeout=2)
            return stub_result(endpoint, True)

        report = monitor.run_monitor(self.path, attempts=1, probe=probe)
        self.assertEqual(report["status"], "healthy")

    def test_duplicate_watch_lock_is_rejected_then_released(self):
        with monitor.monitor_lock(self.path):
            with self.assertRaises(monitor.MonitorAlreadyRunning):
                with monitor.monitor_lock(self.path):
                    self.fail("Duplicate monitor acquired lock")
        with monitor.monitor_lock(self.path):
            pass

    def test_watch_preserves_latest_incident_after_healthy_cycle(self):
        reports = [
            {"status": "persistent_failure", "exit_code": 2, "check_id": "first"},
            {"status": "recovered_transient", "exit_code": 0, "check_id": "second"},
            {"status": "healthy", "exit_code": 0, "check_id": "third"},
        ]
        calls, delays, lines = [], [], []

        def run(path):
            result = reports[len(calls)]
            calls.append(path)
            monitor.write_evidence(path, result)
            return result

        result = monitor.run_watch(self.path, monitor=run, sleep=delays.append, emit=lines.append, max_cycles=3)
        self.assertEqual(result, 0)
        self.assertEqual(delays, [300, 300])
        self.assertEqual(self.saved(), reports[2])
        incident = json.loads((self.path.parent / "last_incident.json").read_text())
        self.assertEqual(incident, reports[1])
        self.assertEqual(len(lines), 3)
        self.assertEqual(len(list(self.path.parent.glob("*.json"))), 2)

    def test_watch_single_stubbed_iteration_has_no_wait(self):
        delays, lines = [], []
        result = monitor.run_watch(
            self.path, max_cycles=1, sleep=delays.append, emit=lines.append,
            probe=lambda endpoint, timeout: stub_result(endpoint, True),
        )
        self.assertEqual(result, 0)
        self.assertEqual(self.saved()["status"], "healthy")
        self.assertEqual(delays, [])
        self.assertEqual(len(lines), 1)
        self.assertFalse((self.path.parent / "last_incident.json").exists())


if __name__ == "__main__":
    unittest.main()
