#!/usr/bin/env python3
"""Immediate and delayed public HTTP verification for TASK 082."""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.request

from cloud.task_075_stage_guard.stage_guard import card_spans


ROOT = pathlib.Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence/public.json"
BASE = "https://www.uaart.com.ua"
CONTRACT = "UA-0011-CATALOG-FERRY-REPAIR-001-V1.0"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch(variant: str, nonce: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        "%s/%s/katalog.html?task082=%s" % (BASE, variant, nonce),
        headers={"User-Agent": "ua-art-task082-public-verify/1", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.status, response.read(4_000_001)


def visible(block: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", block))).strip()


def inspect(variant: str, nonce: str) -> dict:
    status, body = fetch(variant, nonce)
    if status != 200 or len(body) > 4_000_000:
        raise RuntimeError("HTTP_INVALID:%s:%s" % (variant, status))
    source = body.decode("utf-8", "replace")
    spans = card_spans(source)
    ua11 = [span.block for span in spans if span.card_id == "UA-0011"]
    ua9 = [span.block for span in spans if span.card_id == "UA-0009"]
    if len(ua11) != 1 or len(ua9) != 1:
        raise RuntimeError("PROTECTED_CARD_COUNT:%s:%d:%d" % (variant, len(ua11), len(ua9)))
    block = ua11[0]
    text = visible(block)
    checks = {
        "full_template": bool(re.search(r'class=["\'][^"\']*\bua-stage-card-v2\b', block, re.I)),
        "stage_more": 'data-ua-card-stage="more"' in block and 'data-ua-stage="2"' in block,
        "photo": bool(re.search(r'<figure\b[^>]*class=["\'][^"\']*ua-stage-card-v2-photo', block, re.I)
                      and re.search(r'<img\b[^>]*src=["\']https://', block, re.I)),
        "vin_suffix": "VIN 4289" in text,
        "ferry_label": "На пароме · маршрут — Киев" in text,
        "old_route_absent": not bool(re.search(r"Корея\s*(?:→|&rarr;|&#8594;|-)\s*Грузи", text, re.I)),
        "ua0009_photo": bool(re.search(r"<img\b", ua9[0], re.I)),
        "filter_guard": all(token in source for token in (
            'id="ua-stage-card-v2-filter"', "p.get('etap')", "p.get('stage')", "'sea_loaded':'more'"
        )),
    }
    if not all(checks.values()):
        raise RuntimeError("PUBLIC_CONTRACT:%s:%s" % (
            variant, ",".join(key for key, ok in checks.items() if not ok)
        ))
    return {
        "http": status,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "card_count": len(spans),
        "ua0011_count": 1,
        "ua0009_count": 1,
        "checks": checks,
    }


def pass_once(label: str) -> dict:
    nonce = "%s-%d" % (label, time.time_ns())
    return {variant: inspect(variant, nonce) for variant in ("video", "site")}


def main() -> int:
    evidence = {
        "contract_id": CONTRACT,
        "status": "FAIL",
        "started_at_utc": now(),
        "errors": [],
    }
    try:
        evidence["immediate"] = pass_once("immediate")
        time.sleep(20)
        evidence["delayed"] = pass_once("delayed")
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    evidence["finished_at_utc"] = now()
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print("TASK082_PUBLIC_" + evidence["status"])
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

