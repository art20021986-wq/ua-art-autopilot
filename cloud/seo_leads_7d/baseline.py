#!/usr/bin/env python3
"""Read-only public baseline collector for SEO-LEADS-KYIV-7D-001.

Only HTTP GET requests are issued. The script never authenticates, submits a form or writes to
UA ART. Public response bodies can optionally be retained in the local output directory so the
candidate can be rebuilt from one immutable input.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


HERE = Path(__file__).resolve().parent


class HeadFacts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.h1 = ""
        self.robots = ""
        self.description = ""
        self.canonical = ""
        self._capture = ""
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {str(k).lower(): (v or "") for k, v in attrs}
        if tag.lower() == "meta":
            name = data.get("name", "").lower()
            if name == "robots":
                self.robots = data.get("content", "").strip()
            elif name == "description":
                self.description = data.get("content", "").strip()
        elif tag.lower() == "link" and "canonical" in data.get("rel", "").lower().split():
            self.canonical = data.get("href", "").strip()
        elif tag.lower() in {"title", "h1"} and not self._capture:
            self._capture = tag.lower()
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == self._capture:
            value = re.sub(r"\s+", " ", " ".join(self._parts)).strip()
            if self._capture == "title" and not self.title:
                self.title = value
            elif self._capture == "h1" and not self.h1:
                self.h1 = value
            self._capture = ""
            self._parts = []


def safe_name(path: str, content_type: str) -> str:
    if path == "/":
        stem = "__root__"
    else:
        stem = path.strip("/").replace("/", "__")
    suffix = ".html" if "html" in content_type.lower() else ".txt"
    return stem + suffix


def decode_body(body: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w.-]+)", content_type, re.I)
    encoding = match.group(1) if match else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def inspect(base_url: str, path: str, timeout: int) -> dict:
    url = base_url.rstrip("/") + path
    started = time.monotonic()
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "UA-ART-SEO-Baseline/1.0 (read-only; no forms)",
            "Accept": "text/html,application/xhtml+xml,application/xml,text/plain;q=0.9,*/*;q=0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = int(response.status)
            final_url = response.geturl()
            headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = int(exc.code)
        final_url = exc.geturl()
        headers = {k.lower(): v for k, v in exc.headers.items()}
    except Exception as exc:  # recorded as evidence; no retry-side effects
        return {
            "path": path,
            "url": url,
            "status": 0,
            "final_url": "",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "content_type": "",
            "x_robots_tag": "",
            "sha256": "",
            "bytes": 0,
            "snapshot_file": "",
            "title": "",
            "description": "",
            "h1": "",
            "robots": "",
            "canonical": "",
            "diagnostics_count": 0,
            "cta_500_count": 0,
            "vehicle_ids": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    content_type = headers.get("content-type", "")
    text = decode_body(body, content_type)
    facts = HeadFacts()
    if "html" in content_type.lower() or "<html" in text[:1000].lower():
        try:
            facts.feed(text)
        except Exception:
            pass
    diagnostics = re.findall(r"комплексн\w*\s+(?:діагностик|диагностик)", text, re.I)
    cta_500 = re.findall(
        r"(?:задаток|депозит|заброн\w*)[^<]{0,60}(?:\$\s*500|500\s*\$)|"
        r"(?:\$\s*500|500\s*\$)[^<]{0,60}(?:задаток|депозит|заброн\w*)",
        text,
        re.I,
    )
    return {
        "path": path,
        "url": url,
        "status": status,
        "final_url": final_url,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "content_type": content_type,
        "x_robots_tag": headers.get("x-robots-tag", ""),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "snapshot_file": safe_name(path, content_type),
        "title": facts.title,
        "description": facts.description,
        "h1": facts.h1,
        "robots": facts.robots,
        "canonical": facts.canonical,
        "diagnostics_count": len(diagnostics),
        "cta_500_count": len(cta_500),
        "vehicle_ids": sorted(set(re.findall(r"UA-\d{4}", text))),
        "error": "",
        "_body": body,
    }


def render_html(report: dict) -> str:
    rows = []
    for item in report["pages"] + report.get("diagnostic_pages", []):
        rows.append(
            "<tr>"
            f"<td>{html.escape(item['path'])}</td>"
            f"<td>{item['status'] or 'ERR'}</td>"
            f"<td>{item['elapsed_ms']}</td>"
            f"<td>{html.escape(item['robots'] or '—')}</td>"
            f"<td>{html.escape(item['canonical'] or '—')}</td>"
            f"<td>{item['diagnostics_count']}</td>"
            f"<td>{item['cta_500_count']}</td>"
            f"<td><code>{html.escape(item['sha256'][:12])}</code></td>"
            "</tr>"
        )
    return """<!doctype html><html lang=\"ru\"><meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>BASELINE-SEO-001</title><style>
body{font:14px system-ui;margin:24px;color:#172033}table{border-collapse:collapse;width:100%}
th,td{padding:8px;border:1px solid #ccd5e1;text-align:left;vertical-align:top}
th{background:#edf2f8}code{font-size:12px}.ok{color:#08783e}.bad{color:#bd1e2d}
</style><h1>BASELINE-SEO-001</h1>""" + (
        f"<p>Read-only snapshot: {html.escape(report['captured_at'])}; "
        f"Core URLs: {len(report['pages'])}; diagnostic URLs: {len(report.get('diagnostic_pages', []))}; "
        f"catalog IDs: {len(report['catalog_vehicle_ids'])}</p>"
        "<table><thead><tr><th>Path</th><th>HTTP</th><th>ms</th><th>robots</th>"
        "<th>canonical</th><th>diag</th><th>CTA 500</th><th>SHA-256</th></tr></thead><tbody>"
        + "".join(rows) + "</tbody></table></html>"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--save-raw", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output / "raw"
    if args.save_raw:
        raw_dir.mkdir(exist_ok=True)

    requested_paths = config["inventory_paths"] + config.get("diagnostic_paths", [])
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        all_pages = list(pool.map(lambda p: inspect(config["base_url"], p, args.timeout), requested_paths))

    for item in all_pages:
        body = item.pop("_body", b"")
        if args.save_raw and body:
            (raw_dir / item["snapshot_file"]).write_bytes(body)
    pages = [item for item in all_pages if item["path"] in config["inventory_paths"]]
    diagnostic_pages = [item for item in all_pages if item["path"] in config.get("diagnostic_paths", [])]
    catalog = next((x for x in pages if x["path"] == "/video/katalog.html"), {})
    report = {
        "spec_id": "SEO-LEADS-KYIV-7D-001",
        "mode": "read-only",
        "production_write": False,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": config["base_url"],
        "catalog_vehicle_ids": catalog.get("vehicle_ids", []),
        "pages": pages,
        "diagnostic_pages": diagnostic_pages,
    }
    json_path = args.output / "BASELINE-SEO-001.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "BASELINE-SEO-001.html").write_text(render_html(report), encoding="utf-8")
    manifest = "\n".join(f"{x['sha256']}  {x['path']}" for x in all_pages) + "\n"
    (args.output / "sha256-manifest.txt").write_text(manifest, encoding="utf-8")
    failed = [x for x in all_pages if not (0 < x["status"] < 500)]
    print(json.dumps({"core_urls": len(pages), "diagnostic_urls": len(diagnostic_pages), "failed": len(failed), "output": str(args.output)}, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
