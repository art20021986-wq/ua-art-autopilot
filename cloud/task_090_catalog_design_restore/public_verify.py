#!/usr/bin/env python3
"""Independent immediate/delayed public verifier for TASK 090."""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


CONTRACT_ID = "CATALOG-DESIGN-STAGE-RESTORE-090-V1.0"
ORIGIN = "https://www.uaart.com.ua"
EXPECTED_IDS = tuple("UA-%04d" % value for value in range(1, 14))
EXPECTED_COUNTS = {"all": 13, "kiev": 3, "georgia": 1, "sea": 7, "korea": 2}
MAX_BYTES = 12_000_000


class PublicVerifyError(RuntimeError):
    pass


def get_catalog() -> dict[str, Any]:
    path = "/video/katalog.html"
    url = ORIGIN + path + "?task090=%d" % int(time.time() * 1000)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ua-art-task090-public-verify/1", "Cache-Control": "no-cache"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=50) as response:
            body = response.read(MAX_BYTES + 1)
            status = int(response.status)
            effective = response.geturl()
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_BYTES + 1)
        status = int(exc.code)
        effective = exc.geturl()
    if len(body) > MAX_BYTES:
        raise PublicVerifyError("PUBLIC_RESPONSE_TOO_LARGE")
    return {
        "status_code": status,
        "effective_path": urllib.parse.urlsplit(effective).path,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "source": body.decode("utf-8", "replace"),
    }


def verify_round(label: str) -> dict[str, Any]:
    page = get_catalog()
    source = page.pop("source")
    errors: list[str] = []
    articles = re.findall(
        r'<article\b(?=[^>]*class\s*=\s*["\'][^"\']*\bcatalog-card\b)'
        r'[^>]*>.*?</article\s*>',
        source,
        re.I | re.S,
    )
    identifiers = []
    stage_counts = {"all": len(articles), "kiev": 0, "georgia": 0, "sea": 0, "korea": 0}
    for block in articles:
        found = re.search(r'data-ua-card\s*=\s*["\'](UA-[0-9]{4,})["\']', block, re.I)
        stage = re.search(r'data-stage\s*=\s*["\'](kiev|georgia|sea|korea)["\']', block, re.I)
        if not found:
            errors.append("CARD_ID_MISSING")
            continue
        identifier = found.group(1).upper()
        identifiers.append(identifier)
        if not stage:
            errors.append("CARD_STAGE_MISSING:" + identifier)
        else:
            stage_counts[stage.group(1).casefold()] += 1
        hrefs = re.findall(
            r'href\s*=\s*["\'](?:[^"\']*/)?' + re.escape(identifier)
            + r'\.html(?:\?[^"\']*)?["\']',
            block,
            re.I,
        )
        if len(hrefs) != 2:
            errors.append("CARD_LINK_COUNT:" + identifier)
    filters = {
        key: len(re.findall(r'data-f\s*=\s*["\']' + key + r'["\']', source, re.I))
        for key in EXPECTED_COUNTS
    }
    checks = {
        "http_200": page["status_code"] == 200,
        "canonical_path": page["effective_path"] == "/video/katalog.html",
        "nav": bool(re.search(r"<nav\b", source, re.I)),
        "article_cards_13": len(articles) == 13,
        "unique_ids_13": tuple(sorted(identifiers)) == EXPECTED_IDS,
        "stage_counts": stage_counts == EXPECTED_COUNTS,
        "filters_once": filters == {key: 1 for key in EXPECTED_COUNTS},
        "catalog_result": bool(re.search(r"catalog-result", source, re.I)),
        "ru_ua": bool(re.search(r"(?:data-lang|setLang)", source, re.I)),
        "whatsapp": bool(re.search(r"(?:wa\.me|whatsapp)", source, re.I)),
        "footer": bool(re.search(r"<footer\b", source, re.I)),
        "ua0012_once": identifiers.count("UA-0012") == 1,
        "ua0013_once": identifiers.count("UA-0013") == 1,
    }
    for name, passed in checks.items():
        if not passed:
            errors.append("CHECK_FAILED:" + name)
    page.update({
        "label": label,
        "checks": checks,
        "article_cards": len(articles),
        "identifiers": identifiers,
        "stage_counts": stage_counts,
        "filters": filters,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    })
    return page


def verify(rounds: int = 2, delay_seconds: int = 20) -> dict[str, Any]:
    result: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "production_write": False,
        "http_methods": ["GET"],
        "rounds": [],
        "errors": [],
    }
    for index in range(rounds):
        value = verify_round("immediate" if index == 0 else "delayed-%d" % index)
        result["rounds"].append(value)
        if value["status"] != "PASS":
            result["errors"].extend(value["errors"])
        if index + 1 < rounds:
            time.sleep(delay_seconds)
    result["status"] = "PASS" if not result["errors"] else "FAIL"
    return result


if __name__ == "__main__":
    value = verify()
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if value["status"] == "PASS" else 1)

