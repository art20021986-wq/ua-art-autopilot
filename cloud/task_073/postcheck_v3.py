"""
TASK_073 ROUND 4 - postcheck_v3.py

Public, read-only HTTP verification for a single card publication. Used both
by gate_a_v3 (against a mocked/local HTTP layer in tests) and
gate_b_controller_v3 (against real production URLs, immediate and delayed
>=60s).
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


class PostcheckError(RuntimeError):
    pass


@dataclass
class PageCheckResult:
    url: str
    ok: bool
    detail: str = ""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch(url: str, timeout: int = 15):
    import requests

    return requests.get(url, timeout=timeout, allow_redirects=False)


def verify_primary(url: str, auto_number: str, expected_diag_href: str) -> PageCheckResult:
    try:
        response = _fetch(url)
    except Exception as exc:  # noqa: BLE001
        return PageCheckResult(url, False, "request failed: {}".format(exc))
    if response.status_code != 200:
        return PageCheckResult(url, False, "status={}".format(response.status_code))
    body = response.text
    if auto_number not in body:
        return PageCheckResult(url, False, "auto_number marker missing")
    if 'href="{}"'.format(expected_diag_href) not in body:
        return PageCheckResult(url, False, "diagnostics CTA missing")
    if response.url != url:
        return PageCheckResult(url, False, "unexpected redirect to {}".format(response.url))
    return PageCheckResult(url, True)


def verify_diagnostics(url: str, auto_number: str, placeholder_text: str) -> PageCheckResult:
    try:
        response = _fetch(url)
    except Exception as exc:  # noqa: BLE001
        return PageCheckResult(url, False, "request failed: {}".format(exc))
    if response.status_code != 200:
        return PageCheckResult(url, False, "status={}".format(response.status_code))
    body = response.text
    if auto_number not in body:
        return PageCheckResult(url, False, "auto_number marker missing")
    if placeholder_text not in body and "diag-content" not in body:
        return PageCheckResult(url, False, "neither real diagnostics nor placeholder found")
    if response.url != url:
        return PageCheckResult(url, False, "unexpected redirect to {}".format(response.url))
    return PageCheckResult(url, True)


def verify_catalog(url: str, expected_href: str) -> PageCheckResult:
    try:
        response = _fetch(url)
    except Exception as exc:  # noqa: BLE001
        return PageCheckResult(url, False, "request failed: {}".format(exc))
    if response.status_code != 200:
        return PageCheckResult(url, False, "status={}".format(response.status_code))
    occurrences = response.text.count('href="{}"'.format(expected_href))
    if occurrences != 1:
        return PageCheckResult(url, False, "expected exactly 1 href, found {}".format(occurrences))
    return PageCheckResult(url, True)


def verify_card_bundle(
    primary_url: str,
    diag_url: str,
    catalog_url: str,
    auto_number: str,
    placeholder_text: str,
) -> List[PageCheckResult]:
    return [
        verify_primary(primary_url, auto_number, "{}-diag.html".format(auto_number)),
        verify_diagnostics(diag_url, auto_number, placeholder_text),
        verify_catalog(catalog_url, "{}.html".format(auto_number)),
    ]


def verify_immediate_and_delayed(
    primary_url: str,
    diag_url: str,
    catalog_url: str,
    auto_number: str,
    placeholder_text: str,
    delay_seconds: int = 60,
    sleep_fn=time.sleep,
) -> bool:
    immediate = verify_card_bundle(primary_url, diag_url, catalog_url, auto_number, placeholder_text)
    if not all(result.ok for result in immediate):
        return False
    sleep_fn(delay_seconds)
    delayed = verify_card_bundle(primary_url, diag_url, catalog_url, auto_number, placeholder_text)
    return all(result.ok for result in delayed)


def verify_protected_hashes(paths_to_expected_sha: Dict[str, str]) -> Optional[str]:
    for path, expected in paths_to_expected_sha.items():
        try:
            with open(path, "rb") as fh:
                actual = sha256_bytes(fh.read())
        except FileNotFoundError:
            return "missing protected file: {}".format(path)
        if actual != expected:
            return "protected file changed: {} expected={} actual={}".format(path, expected, actual)
    return None
