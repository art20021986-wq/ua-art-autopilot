#!/usr/bin/env python3
"""Verify the public TASK 063 pages after the atomic Gate B install."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
GATE_B_PATH = HERE / "evidence" / "ferry_gate_b.json"
LIVE_PATH = HERE / "evidence" / "ferry_gate_b_live.json"
BASE_URL = "https://www.uaart.com.ua/"
ALLOWED_HOSTS = {"www.uaart.com.ua", "uaart.com.ua"}
MAX_PAGE_BYTES = 2 * 1024 * 1024
ATTEMPTS = 8
RETRY_SECONDS = 10


class LiveBlocked(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


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


def fetch(rel_path: str, nonce: str) -> tuple[bytes, str, int]:
    pure = pathlib.PurePosixPath(rel_path)
    if pure.is_absolute() or ".." in pure.parts or str(pure) != rel_path:
        raise LiveBlocked("unsafe_live_path:" + rel_path)
    url = urllib.parse.urljoin(BASE_URL, rel_path) + "?task063_gate_b=" + nonce
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "UA-ART-TASK-063-Gate-B/1",
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status = getattr(response, "status", response.getcode())
            final_url = response.geturl()
            body = response.read(MAX_PAGE_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LiveBlocked("live_request_failed:" + rel_path) from exc
    parsed = urllib.parse.urlparse(final_url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise LiveBlocked("unexpected_live_redirect:" + rel_path)
    if status != 200:
        raise LiveBlocked("unexpected_live_status:%s:%s" % (rel_path, status))
    if len(body) > MAX_PAGE_BYTES:
        raise LiveBlocked("live_page_too_large:" + rel_path)
    return body, final_url, status


def require_catalog_contract(data: bytes) -> None:
    try:
        html = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LiveBlocked("catalog_not_utf8") from exc

    checks = {
        "catalog_card_count": html.count('class="catalog-card"') == 10,
        "sea_card_count": html.count('class="catalog-card" data-stage="sea"') == 4,
        "ru_two_line_route_count": html.count(
            'data-ru="На пароме&#10;Маршрут: Корея → Грузия"'
        ) == 4,
        "uk_two_line_route_count": html.count(
            'data-uk="На поромі&#10;Маршрут: Корея → Грузія"'
        ) == 4,
        "visible_two_line_route_count": html.count(
            ">На пароме&#10;Маршрут: Корея → Грузия</div>"
        ) == 4,
        "line_break_style": html.count("white-space:pre-line") >= 4,
        "legacy_filter_absent": ">В море · 4<" not in html,
        "ferry_filter_present": ">На пароме · 4<" in html,
        "shown_count": ">Показано: 10<" in html,
    }
    for number in range(1, 11):
        checks["card_UA_%04d" % number] = 'href="UA-%04d.html"' % number in html
    failed = [label for label, passed in checks.items() if not passed]
    if failed:
        raise LiveBlocked("catalog_contract_failed:" + ",".join(failed))


def verify() -> dict:
    gate_b = json.loads(GATE_B_PATH.read_text(encoding="utf-8"))
    if gate_b.get("status") != "PASS":
        raise LiveBlocked("gate_b_not_pass")
    expected = {
        item["path"]: item["candidate_sha256"]
        for item in gate_b.get("files", [])
        if isinstance(item, dict) and item.get("path", "").startswith("video/")
    }
    expected_paths = {
        "video/index.html", "video/katalog.html", "video/info.html", "video/podbor.html",
        *("video/UA-%04d.html" % number for number in range(1, 11)),
    }
    if set(expected) != expected_paths:
        raise LiveBlocked("expected_live_page_set_invalid")
    last_errors = []
    for attempt in range(1, ATTEMPTS + 1):
        pages = []
        bodies = {}
        errors = []
        nonce = "%s-%s-%s" % (
            os.environ.get("GITHUB_RUN_ID", "local"),
            os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
            attempt,
        )
        for rel_path, expected_sha in expected.items():
            try:
                body, final_url, status = fetch(rel_path, nonce)
                actual_sha = sha256_bytes(body)
                pages.append(
                    {
                        "path": rel_path,
                        "url": final_url,
                        "status": status,
                        "expected_sha256": expected_sha,
                        "actual_sha256": actual_sha,
                        "size": len(body),
                    }
                )
                bodies[rel_path] = body
                if actual_sha != expected_sha:
                    errors.append("live_hash_mismatch:" + rel_path)
            except LiveBlocked as exc:
                errors.append(str(exc))
        if not errors:
            try:
                require_catalog_contract(bodies["video/katalog.html"])
            except LiveBlocked as exc:
                errors.append(str(exc))
        if not errors:
            return {
                "task": "task_063",
                "mode": "FERRY_GATE_B_PUBLIC_LIVE_VERIFY",
                "status": "PASS",
                "generated_at_utc": utc_now(),
                "attempt": attempt,
                "page_count": len(pages),
                "catalog_cards": 10,
                "ferry_cards": 4,
                "crm_write": False,
                "db_write": False,
                "service_reload": False,
                "pages": pages,
                "errors": [],
            }
        last_errors = errors
        if attempt < ATTEMPTS:
            time.sleep(RETRY_SECONDS)
    return {
        "task": "task_063",
        "mode": "FERRY_GATE_B_PUBLIC_LIVE_VERIFY",
        "status": "BLOCKED",
        "generated_at_utc": utc_now(),
        "attempt": ATTEMPTS,
        "page_count": 0,
        "catalog_cards": 0,
        "ferry_cards": 0,
        "crm_write": False,
        "db_write": False,
        "service_reload": False,
        "pages": [],
        "errors": last_errors,
    }


def main() -> int:
    try:
        receipt = verify()
    except (LiveBlocked, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        receipt = {
            "task": "task_063",
            "mode": "FERRY_GATE_B_PUBLIC_LIVE_VERIFY",
            "status": "BLOCKED",
            "generated_at_utc": utc_now(),
            "attempt": 0,
            "page_count": 0,
            "catalog_cards": 0,
            "ferry_cards": 0,
            "crm_write": False,
            "db_write": False,
            "service_reload": False,
            "pages": [],
            "errors": [str(exc)],
        }
    atomic_write(LIVE_PATH, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": receipt["status"],
        "page_count": receipt["page_count"],
        "catalog_cards": receipt["catalog_cards"],
        "ferry_cards": receipt["ferry_cards"],
        "errors": receipt["errors"],
    }, ensure_ascii=False, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
