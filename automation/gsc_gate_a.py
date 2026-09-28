#!/usr/bin/env python3
"""Gate A: read-only Google Search Console connectivity check.

Uses only Python's standard library. It never prints OAuth secrets or access tokens.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error

TOKEN_URL = "https://oauth2.googleapis.com/token"
SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required secret: {name}")
    return value


def request_json(url, *, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        # Keep diagnostics, but never echo request credentials/tokens.
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
            detail = body.get("error_description") or body.get("error", {}).get("message") or body.get("error")
        except Exception:
            detail = f"HTTP {exc.code}"
        raise RuntimeError(f"Google API request failed: HTTP {exc.code}: {detail}") from None


def main():
    payload = urllib.parse.urlencode({
        "client_id": required("GSC_CLIENT_ID"),
        "client_secret": required("GSC_CLIENT_SECRET"),
        "refresh_token": required("GSC_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    }).encode()

    status, token = request_json(
        TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    access_token = token.get("access_token")
    if status != 200 or not access_token:
        raise RuntimeError("token exchange succeeded without an access token")

    status, sites = request_json(
        SITES_URL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    if status != 200:
        raise RuntimeError(f"Search Console sites.list returned HTTP {status}")

    entries = sites.get("siteEntry", [])
    print(f"GATE_A_GSC_PASS sites_visible={len(entries)}")
    for entry in entries:
        print(f"- {entry.get('siteUrl', '<unknown>')} [{entry.get('permissionLevel', 'unknown')}]")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"GATE_A_GSC_FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
