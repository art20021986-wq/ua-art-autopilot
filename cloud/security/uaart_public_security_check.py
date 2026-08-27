#!/usr/bin/env python3
"""
uaart_public_security_check.py — TASK 012 Phase C

READ-ONLY external HTTPS security verifier for the public UA ART site.
Stdlib-only (Python 3.10+, urllib/http.client/ssl only). No third-party
dependencies. No CLI argument can change the target host allowlist.

This script never enables HSTS, never enforces CSP, never mutates any
server-side configuration — it only reads response headers/status codes
over plain HTTPS/HTTP GET requests and reports findings.
"""
from __future__ import annotations

import http.client
import json
import socket
import ssl
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# --------------------------------------------------------------------------
# Hardcoded, non-overridable allowlist. This cannot be changed by CLI args,
# environment variables, or any free-form input.
# --------------------------------------------------------------------------
ALLOWLISTED_HOSTS = ("uaart.com.ua", "www.uaart.com.ua")
ALLOWLISTED_PATHS = ("/",)  # only the homepage is checked; deeper site
                             # structure was not confirmed for this task and
                             # is intentionally left NOT_PROVEN rather than
                             # guessed.

TIMEOUT_SECONDS = 10
USER_AGENT = "UAART-SecurityCheck/1.0 (+read-only-verifier)"

SECURITY_HEADERS_EXPECTED = [
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "Content-Security-Policy-Report-Only",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "X-Frame-Options",
    "Permissions-Policy",
]

SERVER_DISCLOSURE_HEADERS = ["Server", "X-Powered-By"]

findings = []


def record(category, target, status, detail):
    findings.append({"category": category, "target": target, "status": status, "detail": detail})


def fetch(url: str, method: str = "GET", allow_redirects: bool = False):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context()  # standard library default validation
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    if not allow_redirects:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                return None
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), NoRedirect())
    try:
        resp = opener.open(req, timeout=TIMEOUT_SECONDS)
        return resp.status, dict(resp.headers), None
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), None
    except Exception as exc:
        return None, {}, exc


def check_https_and_headers(host: str, path: str):
    url = f"https://{host}{path}"
    status, headers, err = fetch(url)
    if err is not None:
        record("https_reachability", url, "FAIL", f"{type(err).__name__}: {err}")
        return
    if status is None:
        record("https_reachability", url, "NOT_PROVEN", "no status returned")
        return
    if 200 <= status < 400:
        record("https_reachability", url, "PASS", f"status={status}")
    else:
        record("https_reachability", url, "FAIL", f"unexpected status={status}")

    for hname in SECURITY_HEADERS_EXPECTED:
        val = headers.get(hname)
        if val:
            record("security_header", f"{url} :: {hname}", "PASS", f"present")
        else:
            record("security_header", f"{url} :: {hname}", "NOT_PROVEN", "header not observed (may be absent)")

    frame_protected = bool(headers.get("X-Frame-Options")) or "frame-ancestors" in (headers.get("Content-Security-Policy", "") + headers.get("Content-Security-Policy-Report-Only", ""))
    record("clickjacking_protection", url, "PASS" if frame_protected else "NOT_PROVEN",
           "frame-ancestors or X-Frame-Options observed" if frame_protected else "no clickjacking header observed")

    for hname in SERVER_DISCLOSURE_HEADERS:
        val = headers.get(hname)
        if val:
            record("server_disclosure", f"{url} :: {hname}", "FAIL", f"value_len={len(val)} (value not reproduced)")

    set_cookie = headers.get("Set-Cookie")
    if set_cookie:
        secure = "secure" in set_cookie.lower()
        httponly = "httponly" in set_cookie.lower()
        samesite = "samesite" in set_cookie.lower()
        record("cookie_attributes", url, "PASS" if (secure and httponly) else "FAIL",
               f"secure={secure} httponly={httponly} samesite_present={samesite}")
    else:
        record("cookie_attributes", url, "NOT_PROVEN", "no Set-Cookie observed on this request")


def check_http_redirect(host: str, path: str):
    conn = None
    try:
        conn = http.client.HTTPConnection(host, 80, timeout=TIMEOUT_SECONDS)
        conn.request("GET", path, headers={"User-Agent": USER_AGENT, "Host": host})
        resp = conn.getresponse()
        status = resp.status
        location = resp.getheader("Location")
        if status in (301, 302, 307, 308) and location and location.startswith("https://"):
            record("http_to_https_redirect", f"http://{host}{path}", "PASS", f"status={status} -> {location}")
        elif status in (301, 302, 307, 308) and not location:
            record("http_to_https_redirect", f"http://{host}{path}", "FAIL", f"redirect status={status} but empty Location")
        else:
            record("http_to_https_redirect", f"http://{host}{path}", "NOT_PROVEN", f"status={status} (no https redirect observed)")
    except Exception as exc:
        record("http_to_https_redirect", f"http://{host}{path}", "NOT_PROVEN", f"{type(exc).__name__}: {exc}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def check_certificate(host: str):
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, 443), timeout=TIMEOUT_SECONDS) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                if cert:
                    record("certificate_validation", host, "PASS", "hostname/chain validated by stdlib ssl defaults")
                else:
                    record("certificate_validation", host, "NOT_PROVEN", "no certificate info returned")
    except ssl.SSLCertVerificationError as exc:
        record("certificate_validation", host, "FAIL", f"verification failed: {exc}")
    except Exception as exc:
        record("certificate_validation", host, "NOT_PROVEN", f"{type(exc).__name__}: {exc}")


def main():
    for host in ALLOWLISTED_HOSTS:
        check_certificate(host)
        for path in ALLOWLISTED_PATHS:
            check_https_and_headers(host, path)
            check_http_redirect(host, path)

    summary = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "allowlisted_hosts": list(ALLOWLISTED_HOSTS),
        "allowlisted_paths": list(ALLOWLISTED_PATHS),
        "total_findings": len(findings),
        "findings": findings,
        "note": "READ-ONLY external check. HSTS/CSP are never enabled by this tool. "
                "Recommendations only; enforcement requires separate Gate B decision.",
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
