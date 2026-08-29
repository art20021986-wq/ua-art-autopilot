"""Immediate + delayed public verification for TASK 073.

Never reports success without an actual fetch of the exact card_id and
publish revision. A redirect to home, a non-200 status, a stale revision,
or a failed delayed re-check all produce an explicit failure outcome.
"""

import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class VerifyOutcome:
    ok: bool
    reason: str


@dataclass
class FetchResponse:
    status_code: int
    body: str
    redirected_to_home: bool
    revision_header: str


def verify_public_page(
    fetch_fn: Callable[[str], "FetchResponse"],
    url: str,
    expected_card_id: str,
    expected_revision: str,
) -> VerifyOutcome:
    resp = fetch_fn(url)
    if resp.status_code != 200:
        return VerifyOutcome(False, f"http_status_{resp.status_code}")
    if resp.redirected_to_home:
        return VerifyOutcome(False, "redirected_to_home")
    if expected_card_id not in resp.body:
        return VerifyOutcome(False, "card_id_not_found")
    if resp.revision_header != expected_revision:
        return VerifyOutcome(False, "stale_revision")
    return VerifyOutcome(True, "ok")


def immediate_and_delayed_verify(
    fetch_fn: Callable[[str], "FetchResponse"],
    url: str,
    card_id: str,
    revision: str,
    sleep_fn=time.sleep,
    delay_seconds: int = 60,
) -> VerifyOutcome:
    first = verify_public_page(fetch_fn, url, card_id, revision)
    if not first.ok:
        return first
    sleep_fn(delay_seconds)
    second = verify_public_page(fetch_fn, url, card_id, revision)
    if not second.ok:
        return VerifyOutcome(False, f"delayed_verify_failed:{second.reason}")
    return VerifyOutcome(True, "immediate_and_delayed_pass")
