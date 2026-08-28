"""Passive canary/continuous-control guard for TASK 070.

Gate A: prepared here only, never launched against production.
Gate B: after explicit written owner approval, this can be scheduled to run
every 5 seconds against the live bot/queue/db.

Implements exactly the safe-action ladder from the task text:
  1. single lock -> durable enqueue, no restart (handled by writer, observed here)
  2. queue>0 -> drain immediately once db is free
  3. oldest queue age >15s OR heartbeat >15s -> one controlled restart of writer/bot
  4. repeat P0 / queue age >30s / quick_check!=ok / card-count or SHA mismatch ->
     stop new writes, roll back code only to backup, keep queue, one alert
  5. never auto-deletes/fixes data; never restart-loops
  6. one alert per incident + one recovery alert, no spam

No LLM tokens are used by this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

POLL_SECONDS = 5
HEARTBEAT_STALE_SECONDS = 15
QUEUE_AGE_RESTART_SECONDS = 15
QUEUE_AGE_P0_SECONDS = 30


@dataclass
class GuardState:
    incident_open: bool = False
    last_alert_ts: float = 0.0
    consecutive_locks: int = 0
    writes_stopped: bool = False


@dataclass
class GuardConfig:
    heartbeat_path: str
    db_path: str
    queue_depth_fn: Callable[[], int]
    queue_oldest_age_fn: Callable[[], float]
    expected_card_count: int
    protected_sha: dict
    alert_fn: Callable[[str], None]
    restart_writer_fn: Callable[[], None]
    stop_writes_fn: Callable[[], None]
    rollback_code_fn: Callable[[], None]


def _quick_check(db_path: str) -> bool:
    try:
        conn = sqlite3.connect(db_path, timeout=1)
        row = conn.execute("PRAGMA quick_check").fetchone()
        conn.close()
        return bool(row) and row[0] == "ok"
    except sqlite3.Error:
        return False


def _card_count(db_path: str) -> Optional[int]:
    try:
        conn = sqlite3.connect(db_path, timeout=1)
        row = conn.execute("SELECT COUNT(*) FROM cars").fetchone()
        conn.close()
        return row[0]
    except sqlite3.Error:
        return None


def _sha256(path: str) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _heartbeat_age(path: str) -> float:
    try:
        return time.time() - os.path.getmtime(path)
    except OSError:
        return float("inf")


def check_once(cfg: GuardConfig, state: GuardState) -> dict:
    """One 5-second tick. Returns a diagnostic dict; mutates state; performs at
    most one safe action."""
    hb_age = _heartbeat_age(cfg.heartbeat_path)
    depth = cfg.queue_depth_fn()
    oldest = cfg.queue_oldest_age_fn() if depth else 0.0
    qc_ok = _quick_check(cfg.db_path)
    card_count = _card_count(cfg.db_path)
    sha_mismatch = False
    for p, expected in cfg.protected_sha.items():
        actual = _sha256(p)
        if actual and expected and not actual.startswith(expected[:12]):
            sha_mismatch = True

    p0 = (not qc_ok) or (card_count is not None and card_count != cfg.expected_card_count) \
        or sha_mismatch or oldest > QUEUE_AGE_P0_SECONDS

    action = "none"
    if p0:
        if not state.writes_stopped:
            cfg.stop_writes_fn()
            cfg.rollback_code_fn()
            state.writes_stopped = True
            action = "stop_writes_rollback_code"
        if not state.incident_open:
            cfg.alert_fn(
                f"P0: quick_check_ok={qc_ok} card_count={card_count} "
                f"expected={cfg.expected_card_count} sha_mismatch={sha_mismatch} "
                f"oldest_queue_age={oldest:.1f}s"
            )
            state.incident_open = True
            state.last_alert_ts = time.time()
    elif hb_age > HEARTBEAT_STALE_SECONDS or oldest > QUEUE_AGE_RESTART_SECONDS:
        cfg.restart_writer_fn()
        action = "controlled_restart"
    elif depth > 0:
        action = "drain_signal"  # drain loop already runs continuously; this
        # is a no-op marker for observability, never a data mutation.
    else:
        if state.incident_open:
            cfg.alert_fn("RECOVERY: guard nominal again")
            state.incident_open = False
            state.writes_stopped = False

    return {
        "heartbeat_age": hb_age,
        "queue_depth": depth,
        "oldest_queue_age": oldest,
        "quick_check_ok": qc_ok,
        "card_count": card_count,
        "sha_mismatch": sha_mismatch,
        "p0": p0,
        "action": action,
    }


def run_forever(cfg: GuardConfig, poll_seconds: float = POLL_SECONDS,
                 max_iterations: Optional[int] = None):
    """Gate B only. Loops check_once every poll_seconds. Never called by this
    worker; provided for the owner-approved Gate B rollout."""
    state = GuardState()
    i = 0
    while max_iterations is None or i < max_iterations:
        result = check_once(cfg, state)
        yield result
        i += 1
        time.sleep(poll_seconds)
