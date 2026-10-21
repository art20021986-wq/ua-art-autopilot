"""Minimal Google Search Console REST client using Python stdlib only.

Authentication uses an OAuth refresh token stored in GitHub Secrets.
No credentials are committed to the repository.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


TOKEN_URL = "https://oauth2.googleapis.com/token"
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"


class GSCConfigError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise GSCConfigError(f"Missing required environment variable: {name}")
    return value


def access_token() -> str:
    payload = urllib.parse.urlencode({
        "client_id": _required("GSC_CLIENT_ID"),
        "client_secret": _required("GSC_CLIENT_SECRET"),
        "refresh_token": _required("GSC_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.load(response)
    token = data.get("access_token")
    if not token:
        raise RuntimeError("Google OAuth response did not contain access_token")
    return token


def inspect_url(inspection_url: str, site_url: str, language_code: str = "en-US") -> dict:
    body = json.dumps({
        "inspectionUrl": inspection_url,
        "siteUrl": site_url,
        "languageCode": language_code,
    }).encode()
    req = urllib.request.Request(
        INSPECT_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)
