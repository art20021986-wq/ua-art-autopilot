"""
ua0009_publication_check.py

Fail-closed publication check for UA-0009. A missing canonical URL
configuration produces BLOCKED, not SKIPPED -- no environment-variable
omission may silently pass. PRAGMA quick_check must equal exactly 'ok';
a transient lock produces BLOCKED without any mutation.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.error
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
class PublicationCheckResult:
    ok: bool
    reason: str
    url: Optional[str] = None
    http_status: Optional[int] = None
    quick_check: Optional[str] = None


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


def probe_no_redirect(url: str, timeout: float = 5.0) -> int:
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, method="GET")
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError:
        return -1


def sqlite_quick_check(db_path: str, timeout: float = 2.0) -> str:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout)
    try:
        conn.execute("PRAGMA query_only=1")
        cur = conn.execute("PRAGMA quick_check")
        row = cur.fetchone()
        cur.close()
        return row[0] if row else "unknown"
    except sqlite3.OperationalError as exc:
        return f"error:{exc}"
    finally:
        conn.close()


def check_ua0009_not_public(db_path: str) -> PublicationCheckResult:
    url = resolve_canonical_url()
    if not url:
        return PublicationCheckResult(
            ok=False,
            reason="BLOCKED: no configured UA0009 canonical URL "
                   f"(set {CONFIG_ENV_VAR} or {CONFIG_FILE_CANDIDATE})",
        )
    status = probe_no_redirect(url)
    not_served = status in (404, 410) or status == -1
    try:
        quick_check = sqlite_quick_check(db_path)
        quick_ok = (quick_check == "ok")
    except Exception as exc:  # pragma: no cover - defensive
        quick_check = f"error:{exc}"
        quick_ok = False

    ok = bool(not_served and quick_ok)
    reason = "ok" if ok else f"BLOCKED: status={status} quick_check={quick_check!r}"
    return PublicationCheckResult(
        ok=ok, reason=reason, url=url, http_status=status, quick_check=quick_check,
    )
