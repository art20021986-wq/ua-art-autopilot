#!/usr/bin/env python3
"""Gate B: collect a small read-only SEO snapshot from Google Search Console.

No third-party dependencies. No site/CRM writes. No OAuth material is printed.
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://oauth2.googleapis.com/token"
SITES_URL = "https://www.googleapis.com/webmasters/v3/sites"
SEARCH_URL = "https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required secret: {name}")
    return value


def json_request(url, *, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8", "replace"))
            error = body.get("error")
            detail = error.get("message") if isinstance(error, dict) else body.get("error_description") or error
        except Exception:
            detail = f"HTTP {exc.code}"
        raise RuntimeError(f"Google API request failed: HTTP {exc.code}: {detail}") from None


def access_token():
    payload = urllib.parse.urlencode({
        "client_id": required("GSC_CLIENT_ID"),
        "client_secret": required("GSC_CLIENT_SECRET"),
        "refresh_token": required("GSC_REFRESH_TOKEN"),
        "grant_type": "refresh_token",
    }).encode()
    _, body = json_request(TOKEN_URL, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    token = body.get("access_token")
    if not token:
        raise RuntimeError("token exchange returned no access token")
    return token


def main():
    token = access_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    _, sites = json_request(SITES_URL, headers=headers)
    entries = sites.get("siteEntry", [])
    if not entries:
        raise RuntimeError("no Search Console properties are visible to this OAuth account")

    preferred = os.environ.get("GSC_SITE_URL", "").strip()
    site = preferred or next((x.get("siteUrl") for x in entries if "uaart.com.ua" in x.get("siteUrl", "")), entries[0].get("siteUrl"))
    if not site:
        raise RuntimeError("could not select a Search Console property")

    end = dt.date.today() - dt.timedelta(days=2)
    start = end - dt.timedelta(days=27)
    query = json.dumps({
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["query"],
        "rowLimit": 10,
        "type": "web",
    }).encode()
    url = SEARCH_URL.format(site=urllib.parse.quote(site, safe=""))
    _, report = json_request(url, data=query, headers={**headers, "Content-Type": "application/json"})

    rows = report.get("rows", [])
    clicks = sum(float(r.get("clicks", 0)) for r in rows)
    impressions = sum(float(r.get("impressions", 0)) for r in rows)
    print(f"GATE_B_GSC_PASS site={site} window={start}..{end} top_queries={len(rows)}")
    print(f"top10_clicks={clicks:g} top10_impressions={impressions:g}")
    for r in rows:
        key = (r.get("keys") or ["<unknown>"])[0]
        print(f"- {key}: clicks={r.get('clicks',0):g} impressions={r.get('impressions',0):g} ctr={r.get('ctr',0):.4f} position={r.get('position',0):.2f}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"GATE_B_GSC_FAIL {exc}", file=sys.stderr)
        raise SystemExit(1)
