"""
ua0009_publication_check.py (TASK 034)

Canonical no-redirect publication probe for UA-0009. Only an actual
HTTP 404 or 410 response counts as "not published"; every other
outcome (2xx, 3xx, other 4xx, 5xx, DNS/TLS/timeout/refused/proxy/
network failure represented as status -1, malformed response, or any
exception) is treated as BLOCKED. Redirects are never followed. HTTPS
is required and URLs with embedded credentials are rejected. Tests
inject an opener; this module never performs real network access from
its own tests.

Existing public names (PublicationCheckResult, resolve_canonical_url,
probe_no_redirect, sqlite_quick_check, check_ua0009_not_public,
CONFIG_ENV_VAR, CONFIG_FILE_CANDIDATE, _NoRedirect) remain importable
as thin adapters over the new canonical_probe_ua0009 logic -- no logic
is duplicated.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CONFIG_ENV_VAR = "UA0009_CANONICAL_URL"
CONFIG_FILE_CANDIDATE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "config", "ua0009_endpoint.json"
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class PublicationProbeResult:
    status: str  # "PASS" or "BLOCKED"
    reason: str
    url: Optional[str] = None
    status_code: Optional[int] = None


@dataclass
class PublicationCheckResult:
    ok: bool
    reason: str
    url: Optional[str] = None
    http_status: Optional[int] = None
    quick_check: Optional[str] = None


def _sanitize(exc: BaseException) -> str:
    return type(exc).__name__


def _validate_https_url(url):
    if not isinstance(url, str) or not url:
        return False, "malformed_url"
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False, "malformed_url"
    if parsed.scheme != "https":
        return False, "non_https_url"
    if not parsed.netloc:
        return False, "malformed_url"
    if "@" in parsed.netloc:
        return False, "embedded_credentials"
    try:
        if parsed.username or parsed.password:
            return False, "embedded_credentials"
    except ValueError:
        return False, "embedded_credentials"
    return True, "ok"


def canonical_probe_ua0009(url: str, opener=None, timeout: float = 5.0) -> PublicationProbeResult:
    """The single canonical no-redirect publication probe. Requires a
    valid HTTPS URL with no embedded credentials. Only HTTP 404/410
    PASS; every other outcome BLOCKS with a bounded structured reason."""
    ok, reason = _validate_https_url(url)
    if not ok:
        return PublicationProbeResult(status="BLOCKED", reason=reason, url=url)

    active_opener = opener if opener is not None else urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, method="GET")

    try:
        response = active_opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        if status_code in (404, 410):
            return PublicationProbeResult(status="PASS", reason="not_found", url=url, status_code=status_code)
        return PublicationProbeResult(
            status="BLOCKED", reason=f"unexpected_status:{status_code}", url=url, status_code=status_code
        )
    except urllib.error.URLError:
        return PublicationProbeResult(status="BLOCKED", reason="network_error", url=url, status_code=-1)
    except (TimeoutError, OSError):
        return PublicationProbeResult(status="BLOCKED", reason="network_error", url=url, status_code=-1)
    except Exception as exc:  # pragma: no cover - defensive, fail closed
        return PublicationProbeResult(status="BLOCKED", reason=f"exception:{_sanitize(exc)}", url=url)

    try:
        if hasattr(response, "__enter__"):
            with response as resp:
                status_code = resp.getcode()
        else:
            status_code = response.getcode()
    except Exception as exc:  # pragma: no cover - defensive, fail closed
        return PublicationProbeResult(status="BLOCKED", reason=f"malformed_response:{_sanitize(exc)}", url=url)

    if status_code in (404, 410):
        return PublicationProbeResult(status="PASS", reason="not_found", url=url, status_code=status_code)
    return PublicationProbeResult(
        status="BLOCKED", reason=f"unexpected_status:{status_code}", url=url, status_code=status_code
    )


def resolve_canonical_url() -> Optional[str]:
    env_val = os.environ.get(CONFIG_ENV_VAR)
    if env_val:
        return env_val.strip()
    if os.path.isfile(CONFIG_FILE_CANDIDATE) and not os.path.islink(CONFIG_FILE_CANDIDATE):
        try:
            with open(CONFIG_FILE_CANDIDATE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            url = data.get("ua0009_canonical_url")
            if isinstance(url, str) and url.strip():
                return url.strip()
        except (OSError, json.JSONDecodeError):
            return None
    return None


def probe_no_redirect(url: str, timeout: float = 5.0, opener=None) -> int:
    """Compatibility adapter over canonical_probe_ua0009. Preserves the
    historical int-returning interface: returns a raw HTTP status code,
    or -1 for network failure / non-HTTP-status BLOCKED outcomes."""
    result = canonical_probe_ua0009(url, opener=opener, timeout=timeout)
    if result.status_code is not None:
        return result.status_code
    return -1


def sqlite_quick_check(db_path: str, timeout: float = 2.0) -> str:
    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    except sqlite3.Error as exc:
        return f"error:{_sanitize(exc)}"
    try:
        conn.execute("PRAGMA query_only=1")
        cur = conn.execute("PRAGMA quick_check")
        row = cur.fetchone()
        cur.close()
        return row[0] if row else "unknown"
    except sqlite3.Error as exc:
        return f"error:{_sanitize(exc)}"
    finally:
        conn.close()


def check_ua0009_not_public(db_path: str, url: Optional[str] = None, opener=None) -> PublicationCheckResult:
    """Compatibility adapter combining the canonical no-redirect probe
    with a read-only SQLite quick_check. Fail-closed: a missing
    configured URL BLOCKS -- it is never silently skipped."""
    active_url = url if url is not None else resolve_canonical_url()
    if not active_url:
        return PublicationCheckResult(
            ok=False,
            reason="BLOCKED: no configured UA0009 canonical URL "
                   f"(set {CONFIG_ENV_VAR} or {CONFIG_FILE_CANDIDATE})",
        )

    probe = canonical_probe_ua0009(active_url, opener=opener)
    quick_check = sqlite_quick_check(db_path)
    quick_ok = (quick_check == "ok")
    ok = bool(probe.status == "PASS" and quick_ok)
    reason = "ok" if ok else f"BLOCKED: probe={probe.status}:{probe.reason} quick_check={quick_check!r}"
    return PublicationCheckResult(
        ok=ok, reason=reason, url=active_url, http_status=probe.status_code, quick_check=quick_check,
    )
