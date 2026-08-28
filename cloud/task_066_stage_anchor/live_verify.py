#!/usr/bin/env python3
"""Verify the public /video cards after the task066 production install."""
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
BASE = "https://www.uaart.com.ua/video/"
MAX_BYTES = 5_000_000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> tuple[int, bytes]:
    last_error = None
    for attempt in range(1, 6):
        separator = "&" if "?" in url else "?"
        request = urllib.request.Request(
            url + separator + "task066_live=%d-%d" % (int(time.time()), attempt),
            headers={
                "User-Agent": "ua-art-task066-live-verifier/1",
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


def validate_card(source: str, identifier: str, expected_stage: int) -> None:
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


def main() -> int:
    deploy = json.loads(DEPLOY.read_text(encoding="utf-8"))
    if deploy.get("status") != "PASS":
        raise SystemExit("TASK066_DEPLOY_NOT_PASS")
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
            validate_card(source, identifier, stage)
            expected_sha = receipt_by_id[identifier]["roots"]["video"]["sha256"]
            if sha(card_data) != expected_sha:
                raise RuntimeError("PUBLIC_CARD_SHA_MISMATCH:" + identifier)

            diag_status, diag_data = fetch(BASE + urllib.parse.quote(identifier) + "-diag.html")
            if diag_status != 200:
                raise RuntimeError("DIAGNOSTICS_HTTP_INVALID:" + identifier)
            diag = diag_data.decode("utf-8")
            if (identifier not in diag or "</html>" not in diag.lower()
                    or ("диагност" not in diag.lower() and "diagnostic" not in diag.lower())):
                raise RuntimeError("DIAGNOSTICS_PAGE_INVALID:" + identifier)
            result["cards"].append({
                "id": identifier,
                "stage": stage,
                "card_http": status,
                "card_sha256": sha(card_data),
                "diagnostics_http": diag_status,
                "diagnostics_sha256": sha(diag_data),
                "stage_anchor_count": 1,
                "stage_nodes": 4,
                "current_nodes": 1,
                "diagnostics_links": 1,
            })
        result["card_count"] = len(result["cards"])
        result["page_count"] = len(result["cards"]) * 2
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
    print("TASK066_LIVE_%s cards=%d pages=%d" % (
        result["status"], result["card_count"], result["page_count"]
    ))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
