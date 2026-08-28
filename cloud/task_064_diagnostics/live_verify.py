#!/usr/bin/env python3
"""Verify TASK 064 from the public UA ART origin by exact SHA-256."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import tempfile
import time
import urllib.error
import urllib.request


HERE = pathlib.Path(__file__).resolve().parent
REPAIR = HERE / "evidence" / "repair.json"
OUTPUT = HERE / "evidence" / "live.json"
BASE = "https://www.uaart.com.ua/video/"
CARD_MARKER = "<!--ua-art-diagnostics-permanent-v1-->"
MAX_BYTES = 2_000_000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fetch(path: str, nonce: str) -> tuple[int, bytes, str]:
    url = BASE + path + "?task064=" + nonce
    request = urllib.request.Request(url, headers={
        "User-Agent": "UA-ART-TASK064-LIVE-VERIFY/1",
        "Cache-Control": "no-cache",
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = getattr(response, "status", response.getcode())
            data = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_BYTES + 1), url
    if len(data) > MAX_BYTES:
        raise RuntimeError("response_too_large:" + path)
    return status, data, url


def card_link_count(source: str, identifier: str) -> int:
    return len(re.findall(
        r'href=["\']' + re.escape(identifier) + r'-diag\.html(?:\?[^"\']*)?["\']',
        source,
        flags=re.IGNORECASE,
    ))


def validate_page(identifier: str, kind: str, data: bytes, expected_sha: str) -> list[str]:
    errors = []
    if sha256(data) != expected_sha:
        errors.append("sha256_mismatch")
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        return errors + ["not_utf8"]
    lowered = source.lower()
    if "</html>" not in lowered or identifier.lower() not in lowered:
        errors.append("html_or_id_missing")
    if kind == "card":
        if card_link_count(source, identifier) != 1:
            errors.append("diagnostics_link_count")
        if source.count(CARD_MARKER) != 1:
            errors.append("permanent_marker_count")
    else:
        if "диагност" not in lowered and "diagnostic" not in lowered:
            errors.append("diagnostics_heading_missing")
        if not re.search(
            r'href=["\']' + re.escape(identifier) + r'\.html(?:\?[^"\']*)?["\']',
            source,
            flags=re.IGNORECASE,
        ):
            errors.append("return_link_missing")
        if CARD_MARKER in source:
            for heading in (
                "Кузов и безопасность", "Техническое состояние",
                "Электроника и OBD", "Фото и видео проверки",
            ):
                if heading not in source:
                    errors.append("section_missing:" + heading)
            for tag in re.findall(r"<video\b[^>]*>", source, flags=re.IGNORECASE):
                if "poster=" not in tag.lower():
                    errors.append("video_poster_missing")
    return errors


def atomic_write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run() -> dict:
    repair = json.loads(REPAIR.read_text(encoding="utf-8"))
    if repair.get("status") != "PASS":
        raise RuntimeError("repair_receipt_not_pass")
    expected = {item["id"]: item["roots"]["video"] for item in repair["cards"]}
    final_results = []
    last_errors = []
    for attempt in range(1, 13):
        results = []
        errors = []
        nonce = "%d-%d-%d" % (int(time.time()), attempt, os.getpid())
        for identifier in repair["card_ids"]:
            item = {"id": identifier, "card": {}, "diag": {}}
            for kind, suffix, hash_key in (
                ("card", ".html", "card_sha256"),
                ("diag", "-diag.html", "diag_sha256"),
            ):
                path = identifier + suffix
                try:
                    status, data, url = fetch(path, nonce)
                    page_errors = [] if status == 200 else ["http_%d" % status]
                    if status == 200:
                        page_errors += validate_page(
                            identifier, kind, data, expected[identifier][hash_key]
                        )
                except Exception as exc:
                    status, data, url = 0, b"", BASE + path
                    page_errors = ["fetch_error:" + type(exc).__name__]
                item[kind] = {
                    "status": status,
                    "sha256": sha256(data) if data else "",
                    "expected_sha256": expected[identifier][hash_key],
                    "url": url,
                    "errors": page_errors,
                }
                errors += [identifier + ":" + kind + ":" + value for value in page_errors]
            results.append(item)
        final_results = results
        last_errors = errors
        if not errors:
            break
        if attempt < 12:
            time.sleep(5)

    receipt = {
        "mode": "TASK_064_PUBLIC_LIVE_VERIFY",
        "status": "PASS" if not last_errors else "BLOCKED",
        "generated_at_utc": utc_now(),
        "page_count": len(repair["card_ids"]) * 2,
        "card_count": len(repair["card_ids"]),
        "ua0009_safe": (
            "UA-0009" not in repair["card_ids"]
            or any(item["id"] == "UA-0009" and not item["card"]["errors"] and not item["diag"]["errors"]
                   for item in final_results)
        ),
        "results": final_results,
        "errors": last_errors,
    }
    atomic_write(OUTPUT, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return receipt


def main() -> int:
    receipt = run()
    print("TASK064_LIVE_%s pages=%d cards=%d ua0009=%s" % (
        receipt["status"], receipt["page_count"], receipt["card_count"],
        "PASS" if receipt["ua0009_safe"] else "FAIL",
    ))
    if receipt["status"] != "PASS":
        print(json.dumps(receipt["errors"], ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
