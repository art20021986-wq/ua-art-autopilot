#!/usr/bin/env python3
"""Fail-closed release gates for the isolated SEO candidate."""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


HERE = Path(__file__).resolve().parent


class Facts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonicals: list[str] = []
        self.robots: list[str] = []
        self.descriptions: list[str] = []
        self.title = ""
        self.h1 = ""
        self._capture = ""
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {str(k).lower(): (v or "") for k, v in attrs}
        if tag.lower() == "link" and "canonical" in data.get("rel", "").lower().split():
            self.canonicals.append(data.get("href", ""))
        elif tag.lower() == "meta" and data.get("name", "").lower() == "robots":
            self.robots.append(data.get("content", ""))
        elif tag.lower() == "meta" and data.get("name", "").lower() == "description":
            self.descriptions.append(data.get("content", ""))
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
            if self._capture == "h1" and not self.h1:
                self.h1 = value
            self._capture = ""


def check(name: str, passed: bool, detail) -> dict:
    return {"gate": name, "pass": bool(passed), "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    baseline = json.loads((args.baseline_dir / "BASELINE-SEO-001.json").read_text(encoding="utf-8"))
    site = args.candidate_dir / "site"
    results = []
    pages = {}

    results.append(check("G0_BASELINE_17", len(baseline["pages"]) == 17, len(baseline["pages"])))
    diagnostic_pages = baseline.get("diagnostic_pages", [])
    results.append(check("G0_DIAGNOSTIC_PAGES_10", len(diagnostic_pages) == 10 and all(x.get("status") == 200 for x in diagnostic_pages), diagnostic_pages))
    expected_ids = [f"UA-{number:04d}" for number in range(1, 11)]
    results.append(check("G0_CATALOG_10", baseline.get("catalog_vehicle_ids") == expected_ids, baseline.get("catalog_vehicle_ids")))

    titles, descriptions = [], []
    for path in config["index_paths"]:
        file_path = site / path.lstrip("/")
        if not file_path.exists():
            pages[path] = {"pass": False, "error": "missing candidate file"}
            continue
        source = file_path.read_text(encoding="utf-8")
        facts = Facts()
        facts.feed(source)
        canonical = config["base_url"].rstrip("/") + path
        noindex = any("noindex" in value.lower() for value in facts.robots)
        diagnostics = len(re.findall(r"комплексн\w*\s+(?:діагностик|диагностик)", source, re.I))
        cta = len(re.findall(r"(?:задаток|депозит|заброн\w*)[^<]{0,60}(?:\$\s*500|500\s*\$)|(?:\$\s*500|500\s*\$)[^<]{0,60}(?:задаток|депозит|заброн\w*)", source, re.I))
        pages[path] = {
            "pass": len(facts.canonicals) == 1 and facts.canonicals[0] == canonical and not noindex and len(facts.descriptions) == 1,
            "canonical": facts.canonicals,
            "noindex": noindex,
            "description_count": len(facts.descriptions),
            "diagnostics_count": diagnostics,
            "cta_500_count": cta,
            "title": facts.title,
            "h1": facts.h1,
        }
        titles.append(facts.title)
        descriptions.extend(facts.descriptions)

    results.append(check("G1_INDEXABILITY_14", len(pages) == 14 and all(x["pass"] for x in pages.values()), pages))
    results.append(check("G2_UNIQUE_TITLES", len(titles) == 14 and len(set(titles)) == 14 and all(titles), titles))
    results.append(check("G2_UNIQUE_DESCRIPTIONS", len(descriptions) == 14 and len(set(descriptions)) == 14 and all(descriptions), descriptions))
    cards = {p: x for p, x in pages.items() if re.search(r"UA-\d{4}", p)}
    results.append(check("G3_DIAGNOSTICS_10", len(cards) == 10 and all(x["diagnostics_count"] >= 1 for x in cards.values()), cards))
    results.append(check("G3_CTA_500_10", len(cards) == 10 and all(x["cta_500_count"] >= 1 for x in cards.values()), cards))

    protected = json.loads((args.candidate_dir / "PROTECTED-DIFF.json").read_text(encoding="utf-8"))
    results.append(check("G3_PROTECTED_DIFF", all(x["protected_body_equal_after_allowlist"] for x in protected), protected))
    for vehicle in ("UA-0009", "UA-0010"):
        page = cards.get(f"/video/{vehicle}.html", {})
        ready = bool(page.get("pass") and page.get("diagnostics_count", 0) >= 1 and page.get("cta_500_count", 0) >= 1)
        results.append(check(f"G4_{vehicle.replace('-', '')}_PUBLIC_READY", ready, page))

    expected_robots = "User-agent: *\nAllow: /\nDisallow: /video/preview/\nSitemap: https://www.uaart.com.ua/sitemap.xml\n"
    results.append(check("G5_ROBOTS", (site / "robots.txt").read_text(encoding="utf-8") == expected_robots, expected_robots))
    root = ET.parse(site / "sitemap.xml").getroot()
    actual_urls = [node.text for node in root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    expected_urls = [config["base_url"].rstrip("/") + p for p in config["index_paths"]]
    results.append(check("G5_SITEMAP_14", actual_urls == expected_urls, actual_urls))
    rollback = json.loads((args.candidate_dir / "rollback/ROLLBACK-TEST.json").read_text(encoding="utf-8"))
    results.append(check("G7_SANDBOX_ROLLBACK", rollback.get("source_manifest_matches") is True, rollback))

    passed = all(item["pass"] for item in results)
    report = {
        "spec_id": "SEO-LEADS-KYIV-7D-001",
        "mode": "sandbox-github-preview",
        "production_write": False,
        "status": "PASS_READY_FOR_OWNER_VISUAL_GATE" if passed else "BLOCKED_FOR_PRODUCTION",
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "passed": sum(x["pass"] for x in results), "total": len(results)}, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
