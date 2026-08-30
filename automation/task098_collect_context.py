#!/usr/bin/env python3
"""Collect bounded, read-only QA evidence for TASK 098.

This helper has a fixed public URL allowlist. It performs GET requests only and writes
point-in-time evidence to /tmp. It never writes to UA ART, CRM, catalog, or production.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

SITE_URLS = [
    "https://www.uaart.com.ua/",
    "https://uaart.com.ua/",
    "https://www.uaart.com.ua/video/index.html",
    "https://www.uaart.com.ua/video/podbor.html",
    "https://www.uaart.com.ua/robots.txt",
    "https://www.uaart.com.ua/sitemap.xml",
]

REDIRECT_URLS = [
    "https://www.motie.go.kr/",
    "https://www.motir.go.kr/",
    "https://english.motir.go.kr/",
    "https://koreajoongangdaily.joins.com/",
    "https://www.koreajoongangdaily.com/",
    "https://europe.autonews.com/",
    "https://www.autonews.com/europe/",
    "https://www.hyundaimotorgroup.com/news/",
    "https://www.hyundaimotorgroup.com/en/news/",
]

HEADERS = {
    "User-Agent": "UA-ART-Editorial-QA/1.1 (+https://www.uaart.com.ua/; read-only)",
    "Accept": "text/html,application/xhtml+xml,application/xml,text/plain;q=0.9,*/*;q=0.5",
}
CONTEXT = ssl.create_default_context()


class RedirectRecorder(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.chain: list[dict[str, Any]] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        self.chain.append({"status": int(code), "from": req.full_url, "to": newurl})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, limit: int) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"URL outside fixed HTTPS policy: {url}")
    recorder = RedirectRecorder()
    opener = urllib.request.build_opener(recorder, urllib.request.HTTPSHandler(context=CONTEXT))
    request = urllib.request.Request(url, headers=HEADERS, method="GET")
    try:
        with opener.open(request, timeout=15) as response:
            raw = response.read(limit)
            charset = response.headers.get_content_charset() or "utf-8"
            return {
                "requested_url": url,
                "status": int(getattr(response, "status", 200)),
                "final_url": response.geturl(),
                "redirect_chain": recorder.chain,
                "headers": {k.lower(): v for k, v in response.headers.items()},
                "body": raw.decode(charset, "replace"),
                "body_bytes_captured": len(raw),
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(limit)
            charset = exc.headers.get_content_charset() if exc.headers else None
            body = raw.decode(charset or "utf-8", "replace")
        except Exception:
            raw, body = b"", ""
        return {
            "requested_url": url,
            "status": int(exc.code),
            "final_url": exc.geturl() or url,
            "redirect_chain": recorder.chain,
            "headers": {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {},
            "body": body,
            "body_bytes_captured": len(raw),
            "error": f"HTTPError:{exc.code}",
        }
    except Exception as exc:  # bounded evidence: failures are data, not a retry loop
        return {
            "requested_url": url,
            "status": "ERROR",
            "final_url": url,
            "redirect_chain": recorder.chain,
            "headers": {},
            "body": "",
            "body_bytes_captured": 0,
            "error": f"{type(exc).__name__}:{str(exc)[:240]}",
        }


def first(pattern: str, text: str) -> str:
    match = re.search(pattern, text, re.I | re.S)
    if not match:
        return ""
    return html.unescape(re.sub(r"\s+", " ", match.group(1)).strip())[:1000]


def link_tags(text: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for tag in re.findall(r"<link\b[^>]*>", text, re.I):
        rel = first(r"\brel=[\"']([^\"']+)", tag).lower().split()
        if "alternate" not in rel:
            continue
        result.append(
            {
                "href": first(r"\bhref=[\"']([^\"']+)", tag),
                "hreflang": first(r"\bhreflang=[\"']([^\"']+)", tag),
            }
        )
    return result


def html_facts(row: dict[str, Any], body: str) -> dict[str, Any]:
    headers = row.pop("headers")
    parsed = urllib.parse.urlparse(str(row["final_url"]))
    canonical = first(
        r"<link[^>]+rel=[\"'][^\"']*canonical[^\"']*[\"'][^>]+href=[\"']([^\"']+)",
        body,
    ) or first(
        r"<link[^>]+href=[\"']([^\"']+)[\"'][^>]+rel=[\"'][^\"']*canonical",
        body,
    )
    robots = first(
        r"<meta[^>]+name=[\"']robots[\"'][^>]+content=[\"']([^\"']+)", body
    ) or first(
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+name=[\"']robots", body
    )
    return {
        **row,
        "final_host": parsed.hostname or "",
        "content_type": headers.get("content-type", ""),
        "x_robots_tag": headers.get("x-robots-tag", ""),
        "cache_control": headers.get("cache-control", ""),
        "server": headers.get("server", ""),
        "title": first(r"<title[^>]*>(.*?)</title>", body),
        "canonical": canonical,
        "meta_robots": robots,
        "hreflang_links": link_tags(body),
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def main() -> None:
    qa_started = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    Path("/tmp/task098_qa_started_at.txt").write_text(
        qa_started.isoformat().replace("+00:00", "Z") + "\n", encoding="utf-8"
    )

    bodies: dict[str, str] = {}
    site_rows: list[dict[str, Any]] = []
    for url in SITE_URLS:
        row = fetch(url, 524_288)
        body = str(row.pop("body"))
        bodies[url] = body
        site_rows.append(html_facts(row, body))
    Path("/tmp/task098_live_site_probe.json").write_text(
        json.dumps(site_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path("/tmp/task098_robots_live.txt").write_text(
        bodies.get("https://www.uaart.com.ua/robots.txt", ""), encoding="utf-8"
    )
    Path("/tmp/task098_sitemap_live_excerpt.xml").write_text(
        bodies.get("https://www.uaart.com.ua/sitemap.xml", "")[:524_288], encoding="utf-8"
    )

    redirect_rows: list[dict[str, Any]] = []
    for url in REDIRECT_URLS:
        row = fetch(url, 196_608)
        body = str(row.pop("body"))
        facts = html_facts(row, body)
        # Hreflang/body hash are not needed in this focused redirect evidence.
        facts.pop("hreflang_links", None)
        facts.pop("body_sha256", None)
        redirect_rows.append(facts)
    Path("/tmp/task098_redirect_probe.json").write_text(
        json.dumps(redirect_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    probe_path = Path("cloud/task_097_editorial_atlas_news/live_source_probe.tsv")
    with probe_path.open(encoding="utf-8", newline="") as handle:
        probe_rows = list(csv.DictReader(handle, delimiter="\t"))
    with Path("cloud/task_097_editorial_atlas_news/source_registry.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        registry_rows = list(csv.DictReader(handle))
    if len(probe_rows) != 70 or len(registry_rows) != 70:
        raise SystemExit(f"Expected 70 rows, got probe={len(probe_rows)} registry={len(registry_rows)}")

    normal: list[dict[str, str]] = []
    non_normal: list[dict[str, str]] = []
    for row in probe_rows:
        try:
            is_normal = int(row.get("http_status", "")) < 400
        except (TypeError, ValueError):
            is_normal = False
        (normal if is_normal else non_normal).append(row)

    machine = {
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "rows": len(probe_rows),
        "geo_counts": dict(Counter(row["geo"] for row in probe_rows)),
        "normal_lt_400_count": len(normal),
        "non_normal_count": len(non_normal),
        "non_normal_source_ids": [row["source_id"] for row in non_normal],
        "http_status_counts": dict(Counter(row.get("http_status", "") for row in probe_rows)),
        "decision_counts": dict(Counter(row.get("decision", "") for row in registry_rows)),
        "mvp_source_ids": [row["source_id"] for row in registry_rows if row.get("decision") == "APPROVE_MVP"],
    }
    if len(non_normal) != 24 or len(machine["mvp_source_ids"]) != 15:
        raise SystemExit(f"Invariant mismatch: non_normal={len(non_normal)} mvp={len(machine['mvp_source_ids'])}")
    Path("/tmp/task098_source_probe_qa_machine.json").write_text(
        json.dumps(machine, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"site_rows": len(site_rows), "redirect_rows": len(redirect_rows), "non_normal": len(non_normal)}))


if __name__ == "__main__":
    main()
