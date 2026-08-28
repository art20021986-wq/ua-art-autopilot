#!/usr/bin/env python3
"""Verify the public cards, diagnostics and catalog after task068."""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request


HERE = pathlib.Path(__file__).resolve().parent
DEPLOY = HERE / "evidence" / "deploy.json"
OUT = HERE / "evidence" / "live.json"
START = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->"
END = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:END -->"
DIAG = "<!--ua-art-diagnostics-permanent-v1-->"
VIN_START = "<!-- UA-ART-VIN-GUARD-LITE-V1:START -->"
VIN_END = "<!-- UA-ART-VIN-GUARD-LITE-V1:END -->"
CAT_START = "<!-- UA-ART-CATALOG-VIN-V1:START -->"
CAT_END = "<!-- UA-ART-CATALOG-VIN-V1:END -->"
BASE = "https://www.uaart.com.ua/video/"
MAX_BYTES = 5_000_000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> tuple[int, bytes]:
    last_error = None
    for attempt in range(1, 6):
        separator = "&" if "?" in url else "?"
        request = urllib.request.Request(
            url + separator + "task068_live=%d-%d" % (int(time.time()), attempt),
            headers={
                "User-Agent": "ua-art-task068-live-verifier/1",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise RuntimeError("PAGE_TOO_LARGE")
                return response.status, data
        except Exception as exc:
            last_error = exc
            if attempt < 5:
                time.sleep(attempt * 2)
    raise RuntimeError("PUBLIC_FETCH_FAILED:" + type(last_error).__name__)


def forbidden_sea_count(source: str) -> int:
    patterns = (
        r"(?i)(?<![А-Яа-яЁёІіЇїЄє])в\s+море(?![А-Яа-яЁёІіЇїЄє])",
        r"(?i)(?<![А-Яа-яЁёІіЇїЄє])на\s+море(?![А-Яа-яЁёІіЇїЄє])",
        r"(?i)(?<![А-Яа-яЁёІіЇїЄє])у\s+мор[іi](?![А-Яа-яЁёІіЇїЄє])",
        r"(?i)(?<![А-Яа-яЁёІіЇїЄє])в\s+мор[іi](?![А-Яа-яЁёІіЇїЄє])",
        r"(?i)(?<![А-Яа-яЁёІіЇїЄє])мор(?:е|ем|ской|ская|ское|ские)(?![А-Яа-яЁёІіЇїЄє])",
    )
    return sum(len(re.findall(pattern, source)) for pattern in patterns)


def validate_card(source: str, identifier: str, expected_stage: int,
                  vin: str, engine_cc: int, video_count: int) -> None:
    if source.count(START) != 1 or source.count(END) != 1:
        raise RuntimeError("ANCHOR_COUNT_INVALID:" + identifier)
    region = source[source.index(START):source.index(END) + len(END)]
    if re.findall(r'data-ua-stage="([1-4])"', region) != ["1", "2", "3", "4"]:
        raise RuntimeError("NODE_ORDER_INVALID:" + identifier)
    if region.count('data-ua-state="current"') != 1 or region.count("СЕЙЧАС") != 1:
        raise RuntimeError("CURRENT_STATE_INVALID:" + identifier)
    match = re.search(r'data-ua-stage-current="([1-4])"', region)
    if not match or int(match.group(1)) != expected_stage:
        raise RuntimeError("CURRENT_STAGE_INVALID:" + identifier)
    for label in ("Корея", "Паром", "Грузия", "Киев"):
        if region.count('data-ua-stage-label="%s"' % label) != 1:
            raise RuntimeError("LABEL_INVALID:%s:%s" % (identifier, label))
    if source.count(DIAG) != 1:
        raise RuntimeError("DIAGNOSTICS_MARKER_INVALID:" + identifier)
    links = re.findall(
        r'href=["\']' + re.escape(identifier) + r'-diag\.html(?:\?[^"\']*)?["\']',
        source,
        flags=re.IGNORECASE,
    )
    if len(links) != 1:
        raise RuntimeError("DIAGNOSTICS_LINK_INVALID:" + identifier)
    if source.count(VIN_START) != 1 or source.count(VIN_END) != 1:
        raise RuntimeError("VIN_GUARD_COUNT_INVALID:" + identifier)
    if len(re.findall(r'class=["\'][^"\']*\bua-vin-v1-button\b', source, re.I)) != 1:
        raise RuntimeError("VIN_BUTTON_COUNT_INVALID:" + identifier)
    if vin not in source or "VIN ПРОВЕРЕН" not in source:
        raise RuntimeError("VIN_CONTENT_INVALID:" + identifier)
    normalized = re.sub(r"\s", "", source)
    if "%dсм³" % engine_cc not in normalized:
        raise RuntimeError("ENGINE_CONTENT_INVALID:" + identifier)
    if 'data-ua-video-count="%d"' % video_count not in source:
        raise RuntimeError("VIDEO_COUNT_INVALID:" + identifier)
    if forbidden_sea_count(source):
        raise RuntimeError("FORBIDDEN_SEA_WORDING_REMAINS:" + identifier)
    if re.search(r'class=["\'][^"\']*\b(?:mcf-etap|mcf-track|mcf-diag-off)\b', source, re.IGNORECASE):
        raise RuntimeError("LEGACY_DUPLICATE_REMAINS:" + identifier)
    if 'name="ua-art-contract" content="UA-CARDS-FERRY-VIN-001-V1.1"' not in source:
        raise RuntimeError("CACHE_CONTRACT_META_MISSING:" + identifier)


def validate_catalog(source: str, cards: list[dict]) -> None:
    if source.count(CAT_START) != len(cards) or source.count(CAT_END) != len(cards):
        raise RuntimeError("CATALOG_VIN_BLOCK_COUNT_INVALID")
    if forbidden_sea_count(source):
        raise RuntimeError("CATALOG_FORBIDDEN_SEA_WORDING_REMAINS")
    for card in cards:
        identifier = card["id"]
        root = card["roots"]["video"]
        marker = 'data-ua-card="%s"' % identifier
        if source.count(marker) != 1 or root["vin"] not in source:
            raise RuntimeError("CATALOG_VIN_INVALID:" + identifier)
        position = source.index(marker)
        start = source.rfind(CAT_START, 0, position)
        end = source.find(CAT_END, position)
        block = source[start:end + len(CAT_END)]
        if "%dсм³" % root["engine_cc"] not in re.sub(r"\s", "", block):
            raise RuntimeError("CATALOG_ENGINE_INVALID:" + identifier)
        if 'data-ua-video-count="%d"' % root["video_count"] not in block:
            raise RuntimeError("CATALOG_VIDEO_COUNT_INVALID:" + identifier)


def main() -> int:
    deploy = json.loads(DEPLOY.read_text(encoding="utf-8"))
    if deploy.get("status") != "PASS":
        raise SystemExit("TASK068_DEPLOY_NOT_PASS")
    install = deploy["install"]
    post = deploy["postcheck"]
    cards_by_id = {card["id"]: card for card in post["cards"]}
    receipt_by_id = {card["id"]: card for card in install["cards"]}
    result = {
        "contract_id": deploy["contract_id"],
        "status": "FAIL",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "card_count": 0,
        "page_count": 0,
        "ua0009_safe": False,
        "cards": [],
        "errors": [],
        "llm_tokens": 0,
    }
    try:
        for identifier in install["card_ids"]:
            stage = int(cards_by_id[identifier]["stage"])
            status, card_data = fetch(BASE + urllib.parse.quote(identifier) + ".html")
            if status != 200:
                raise RuntimeError("CARD_HTTP_INVALID:" + identifier)
            source = card_data.decode("utf-8")
            root_contract = receipt_by_id[identifier]["roots"]["video"]
            validate_card(source, identifier, stage, root_contract["vin"],
                          int(root_contract["engine_cc"]), int(root_contract["video_count"]))
            expected_sha = receipt_by_id[identifier]["roots"]["video"]["sha256"]
            matches_install_sha = sha(card_data) == expected_sha

            diag_status, diag_data = fetch(BASE + urllib.parse.quote(identifier) + "-diag.html")
            if diag_status != 200:
                raise RuntimeError("DIAGNOSTICS_HTTP_INVALID:" + identifier)
            diag_source = diag_data.decode("utf-8", "replace")
            if "<html" not in diag_source.lower() or "</html>" not in diag_source.lower():
                raise RuntimeError("DIAGNOSTICS_PAGE_INVALID:" + identifier)
            result["cards"].append({
                "id": identifier,
                "stage": stage,
                "card_http": status,
                "card_sha256": sha(card_data),
                "matches_install_sha": matches_install_sha,
                "diagnostics_http": diag_status,
                "diagnostics_sha256": sha(diag_data),
                "diagnostics_bytes": len(diag_data),
                "diagnostics_content_required": False,
                "stage_anchor_count": 1,
                "stage_nodes": 4,
                "current_nodes": 1,
                "diagnostics_links": 1,
                "vin_guard_count": 1,
                "vin_button_count": 1,
                "vin": root_contract["vin"],
                "engine_cc": root_contract["engine_cc"],
                "video_count": root_contract["video_count"],
                "forbidden_sea_terms": 0,
            })
        catalog_status, catalog_data = fetch(BASE + "katalog.html")
        if catalog_status != 200:
            raise RuntimeError("CATALOG_HTTP_INVALID")
        validate_catalog(catalog_data.decode("utf-8"), install["cards"])
        result["card_count"] = len(result["cards"])
        result["page_count"] = len(result["cards"]) * 2 + 1
        result["catalog_http"] = catalog_status
        result["catalog_sha256"] = sha(catalog_data)
        result["ua0009_safe"] = any(
            card["id"] == "UA-0009" and card["stage"] == 2
            for card in result["cards"]
        )
        if result["card_count"] != 10 or not result["ua0009_safe"]:
            raise RuntimeError("PUBLIC_CARD_SET_INVALID")
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TASK068_LIVE_%s cards=%d pages=%d" % (
        result["status"], result["card_count"], result["page_count"]
    ))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
