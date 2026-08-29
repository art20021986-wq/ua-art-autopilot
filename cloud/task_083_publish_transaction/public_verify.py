#!/usr/bin/env python3
"""Immediate and delayed public verification for TASK 083."""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


CONTRACT_ID = "UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0"
ORIGIN = "https://www.uaart.com.ua"
TARGETS = ("UA-0012", "UA-0013")
MAX_BYTES = 12_000_000


class PublicError(RuntimeError):
    pass


def _get(path: str) -> dict[str, Any]:
    separator = "&" if "?" in path else "?"
    url = ORIGIN + path + separator + "task083=%d" % int(time.time() * 1000)
    request = urllib.request.Request(
        url, headers={"User-Agent": "ua-art-task083-public-verify/1"}, method="GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read(MAX_BYTES + 1)
            status = int(response.status)
            effective = response.geturl()
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_BYTES + 1)
        status = int(exc.code)
        effective = exc.geturl()
    if len(body) > MAX_BYTES:
        raise PublicError("PUBLIC_RESPONSE_TOO_LARGE:" + path)
    text = body.decode("utf-8", "replace")
    return {
        "status": status,
        "effective_path": urllib.parse.urlsplit(effective).path,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "text": text,
    }


def _href_count(source: str, code: str) -> int:
    return len(re.findall(
        r"href\s*=\s*['\"](?:https?://[^'\"]+)?(?:[^'\"]*/)?"
        + re.escape(code) + r"\.html(?:\?[^'\"]*)?['\"]",
        source,
        re.I,
    ))


def _stage_window(source: str, code: str) -> str:
    match = re.search(
        r"href\s*=\s*['\"][^'\"]*" + re.escape(code) + r"\.html(?:\?[^'\"]*)?['\"]",
        source,
        re.I,
    )
    if not match:
        return ""
    return source[max(0, match.start() - 1200):min(len(source), match.end() + 14000)]


def verify_round(label: str) -> dict[str, Any]:
    result: dict[str, Any] = {"label": label, "status": "FAIL", "errors": [], "pages": {}}
    for code in TARGETS:
        primary_path = "/video/%s.html" % code
        diag_path = "/video/%s-diag.html" % code
        primary = _get(primary_path)
        diag = _get(diag_path)
        primary_text = primary.pop("text")
        diag_text = diag.pop("text")
        links = len(re.findall(
            r"href\s*=\s*['\"](?:[^'\"]*/)?" + re.escape(code)
            + r"-diag\.html(?:\?[^'\"]*)?['\"]",
            primary_text,
            re.I,
        ))
        stage_ok = any(token in primary_text for token in (
            'data-ua-stage-current="2"', "data-ua-stage-current='2'",
            'data-ua-stage="2"', "data-ua-stage='2'",
        ))
        primary_ok = (
            primary["status"] == 200 and primary["effective_path"] == primary_path
            and code in primary_text and links == 1 and stage_ok
        )
        diag_ok = (
            diag["status"] == 200 and diag["effective_path"] == diag_path
            and code in diag_text and "</html>" in diag_text.lower()
        )
        primary.update({"diag_links": links, "stage": 2, "pass": primary_ok})
        diag.update({"pass": diag_ok})
        result["pages"][code] = {"primary": primary, "diagnostic": diag}
        if not primary_ok:
            result["errors"].append("PRIMARY_PUBLIC_FAIL:" + code)
        if not diag_ok:
            result["errors"].append("DIAGNOSTIC_PUBLIC_FAIL:" + code)

    catalog = _get("/video/katalog.html")
    catalog_text = catalog.pop("text")
    cards = {}
    for code in TARGETS:
        count = _href_count(catalog_text, code)
        window = _stage_window(catalog_text, code)
        stage_ok = any(token in window for token in (
            'data-ua-stage="2"', "data-ua-stage='2'",
            'data-ua-stage-tile="2"', "data-ua-stage-tile='2'",
            'data-stage="2"', "data-stage='2'",
        ))
        category_ok = any(token in window for token in (
            'data-ua-card-stage="more"', "data-ua-card-stage='more'",
            'data-etap="more"', "data-etap='more'",
        ))
        ferry_copy = "На пароме" in window or "На поромі" in window
        cards[code] = {
            "href_count": count, "stage": 2, "category": "more",
            "stage_token": stage_ok, "category_token": category_ok,
            "ferry_copy": ferry_copy,
            "pass": count == 1 and stage_ok and category_ok and ferry_copy,
        }
        if not cards[code]["pass"]:
            result["errors"].append("CATALOG_PUBLIC_FAIL:" + code)
    catalog_ok = (
        catalog["status"] == 200
        and catalog["effective_path"] == "/video/katalog.html"
        and all(item["pass"] for item in cards.values())
    )
    catalog.update({"cards": cards, "pass": catalog_ok})
    result["catalog"] = catalog
    result["status"] = "PASS" if not result["errors"] else "FAIL"
    return result


def verify(rounds: int = 2, delay_seconds: int = 20) -> dict[str, Any]:
    evidence = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "production_write": False,
        "http_methods": ["GET"],
        "rounds": [],
        "errors": [],
    }
    for index in range(rounds):
        if index:
            time.sleep(delay_seconds)
        value = verify_round("immediate" if index == 0 else "delayed-%d" % index)
        evidence["rounds"].append(value)
        evidence["errors"].extend(value["errors"])
    evidence["status"] = "PASS" if not evidence["errors"] else "FAIL"
    return evidence


def main() -> int:
    value = verify()
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
