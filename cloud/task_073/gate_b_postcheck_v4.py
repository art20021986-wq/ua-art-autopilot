"""TASK 073 ROUND 5 - gate_b_postcheck_v4.py

Read-only public HTTP verification for UA-0011 after Gate B install.
Exact URL, no redirect, HTTP 200, body/href checks. Called immediately
and again after >=60 seconds by the controller. Never claims success
from status code alone.
"""

import json
import sys
import time

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

DEFAULT_BASE = "https://carix.pythonanywhere.com"


def _get_no_redirect(session, url, timeout=20):
    return session.get(url, timeout=timeout, allow_redirects=False)


def verify_primary(session, base_url, auto_number="UA-0011"):
    url = "%s/video/%s.html" % (base_url, auto_number)
    resp = _get_no_redirect(session, url)
    ok = resp.status_code == 200 and auto_number in resp.text
    return {"url": url, "status_code": resp.status_code, "ok": ok}


def verify_diag(session, base_url, auto_number="UA-0011"):
    url = "%s/video/%s-diag.html" % (base_url, auto_number)
    resp = _get_no_redirect(session, url)
    marker_ok = (auto_number in resp.text) or ("Материалы диагностики пока не добавлены" in resp.text)
    ok = resp.status_code == 200 and marker_ok
    return {"url": url, "status_code": resp.status_code, "ok": ok}


def verify_catalog(session, base_url, auto_number="UA-0011"):
    url = "%s/video/katalog.html" % base_url
    resp = _get_no_redirect(session, url)
    href = 'href="%s.html"' % auto_number
    count = resp.text.count(href) if resp.status_code == 200 else 0
    ok = resp.status_code == 200 and count == 1
    return {"url": url, "status_code": resp.status_code, "href_count": count, "ok": ok}


def run_full_check(base_url=DEFAULT_BASE, auto_number="UA-0011", session=None):
    if session is None:
        if requests is None:
            return {"status": "BLOCKED_NO_REQUESTS_LIB"}
        session = requests.Session()
    primary = verify_primary(session, base_url, auto_number)
    diag = verify_diag(session, base_url, auto_number)
    catalog = verify_catalog(session, base_url, auto_number)
    overall_ok = primary["ok"] and diag["ok"] and catalog["ok"]
    return {
        "auto_number": auto_number,
        "primary": primary,
        "diag": diag,
        "catalog": catalog,
        "status": "PASS" if overall_ok else "FAIL",
    }


def run_immediate_and_delayed(base_url=DEFAULT_BASE, auto_number="UA-0011", delay_seconds=60,
                               session=None, sleep_fn=time.sleep):
    immediate = run_full_check(base_url, auto_number, session)
    sleep_fn(delay_seconds)
    delayed = run_full_check(base_url, auto_number, session)
    overall = "PASS" if immediate["status"] == "PASS" and delayed["status"] == "PASS" else "FAIL"
    return {"immediate": immediate, "delayed": delayed, "status": overall}


def main():
    result = run_immediate_and_delayed()
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        sys.exit(1)


if __name__ == "__main__":
    main()
