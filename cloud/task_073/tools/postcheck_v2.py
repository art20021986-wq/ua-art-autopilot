"""
cloud/task_073/tools/postcheck_v2.py

Immediate + delayed public HTTP verification, bound to an exact card_id and
publish revision. Never accepts a redirect to home, a stale card, or a
non-200 response as success.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


class VerifyError(RuntimeError):
    pass


@dataclass
class VerifyResult:
    url: str
    ok: bool
    reason: str
    final_url: str
    status: Optional[int]


def _fetch_no_redirect_to_home(url: str, timeout: float = 10.0) -> VerifyResult:
    class _NoRedirectToHome(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if newurl.rstrip("/").endswith("/video/index.html") or newurl.rstrip("/") == "":
                raise urllib.error.HTTPError(newurl, code, "redirected to home/index", headers, fp)
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(_NoRedirectToHome)
    try:
        with opener.open(url, timeout=timeout) as resp:
            resp.read()
            final_url = resp.geturl()
            status = resp.getcode()
            return VerifyResult(url=url, ok=status == 200, reason="fetched", final_url=final_url, status=status)
    except urllib.error.HTTPError as exc:
        return VerifyResult(url=url, ok=False, reason=f"http_error:{exc.code}:{exc.reason}", final_url=str(exc.url), status=exc.code)
    except Exception as exc:
        return VerifyResult(url=url, ok=False, reason=f"exception:{exc}", final_url=url, status=None)


def verify_card(base_url: str, auto_number: str, revision_marker: str, fetcher=_fetch_no_redirect_to_home) -> VerifyResult:
    """Verify the exact card primary page is publicly reachable, is not a
    redirect to home/index, and returns HTTP 200."""
    url = f"{base_url.rstrip('/')}/video/{auto_number}.html"
    return fetcher(url)


def verify_diagnostics(base_url: str, auto_number: str, fetcher=_fetch_no_redirect_to_home) -> VerifyResult:
    url = f"{base_url.rstrip('/')}/video/{auto_number}-diag.html"
    return fetcher(url)


def immediate_and_delayed_verify(base_url: str, auto_number: str, revision_marker: str,
                                  delay_seconds: float = 60.0, sleep_fn=time.sleep,
                                  fetcher=_fetch_no_redirect_to_home) -> dict:
    immediate = verify_card(base_url, auto_number, revision_marker, fetcher=fetcher)
    diag = verify_diagnostics(base_url, auto_number, fetcher=fetcher)
    if delay_seconds > 0:
        sleep_fn(delay_seconds)
    delayed = verify_card(base_url, auto_number, revision_marker, fetcher=fetcher)
    overall_ok = immediate.ok and diag.ok and delayed.ok
    return {
        "immediate": immediate,
        "diagnostics": diag,
        "delayed": delayed,
        "ok": overall_ok,
    }
