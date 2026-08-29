"""Single logical transaction for updating a card's ETA (TASK 076 contract).

One input N days must produce, as ONE logical transaction:
  days_to_kyiv=N, eta_manual=UTC_today+N days, updated_at=now.

Success is reported to the caller ONLY after:
  1. both fields are written,
  2. a verified read-back confirms BOTH fields match what was written,
  3. bounded rebuild + publish PASS for the card page, required diag/
     placeholder if any, BOTH catalogs, and BOTH /video and /site surfaces.

Any partial write, stale row, busy/queue timeout, read-back mismatch, or
publisher FAIL means success is NEVER reported; a bounded rollback of the DB
fields is attempted (when prior state is known) and a retryable job is kept.

This module is transport/schema agnostic (DbAdapter / PublishAdapter
protocols) so it can be wired to the real db.py / konteyner.py / yadro.py /
publikaciya.py once their exact live behaviour is confirmed under Gate A.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol, List, Dict, Any
import time

from eta_engine import compute_manual_eta, InvalidDaysError


class DbAdapter(Protocol):
    def begin(self, car_id: str) -> None: ...
    def write_eta(self, car_id: str, days_to_kyiv: int, eta_manual: str, updated_at: str) -> None: ...
    def read_back(self, car_id: str) -> dict: ...
    def rollback(self, car_id: str, previous: dict) -> None: ...
    def commit(self, car_id: str) -> None: ...


class PublishAdapter(Protocol):
    def rebuild_card(self, car_id: str) -> bool: ...
    def rebuild_catalogs(self) -> bool: ...
    def publish_video(self, car_id: str) -> bool: ...
    def publish_site(self, car_id: str) -> bool: ...


@dataclass
class TransactionResult:
    success: bool
    car_id: str
    days_to_kyiv: Optional[int] = None
    eta_manual: Optional[str] = None
    error: Optional[str] = None
    rolled_back: bool = False
    retry_queued: bool = False
    steps_log: List[str] = field(default_factory=list)


class EtaSyncController:
    """Applies the single-write ETA contract idempotently and generically
    (keyed only by car_id, no hardcoded ID special-casing)."""

    def __init__(self, db: DbAdapter, publisher: PublishAdapter,
                 readback_timeout_s: float = 5.0):
        self.db = db
        self.publisher = publisher
        self.readback_timeout_s = readback_timeout_s
        self._retry_queue: Dict[str, int] = {}

    def submit(self, car_id: str, days: int) -> TransactionResult:
        log: List[str] = []
        try:
            eta = compute_manual_eta(days)
        except InvalidDaysError as e:
            return TransactionResult(success=False, car_id=car_id, error=str(e),
                                      steps_log=["validate:REJECTED"])
        log.append("validate:OK")

        try:
            previous = self.db.read_back(car_id)
        except Exception:
            previous = None

        updated_at = datetime.now(timezone.utc).isoformat()

        try:
            self.db.begin(car_id)
            log.append("db_begin:OK")
            self.db.write_eta(car_id, eta.days_to_kyiv, eta.eta_manual.isoformat(), updated_at)
            log.append("db_write:OK")
        except Exception as e:
            log.append(f"db_write:FAIL:{e}")
            self._queue_retry(car_id, days)
            return TransactionResult(success=False, car_id=car_id, error="db_write_failed",
                                      retry_queued=True, steps_log=log)

        try:
            row = self._readback_with_timeout(car_id)
        except TimeoutError:
            log.append("readback:TIMEOUT")
            self._safe_rollback(car_id, previous, log)
            self._queue_retry(car_id, days)
            return TransactionResult(success=False, car_id=car_id, error="readback_timeout",
                                      rolled_back=True, retry_queued=True, steps_log=log)
        except Exception as e:
            log.append(f"readback:ERROR:{e}")
            self._safe_rollback(car_id, previous, log)
            self._queue_retry(car_id, days)
            return TransactionResult(success=False, car_id=car_id, error="readback_error",
                                      rolled_back=True, retry_queued=True, steps_log=log)

        if (str(row.get("days_to_kyiv")) != str(eta.days_to_kyiv)
                or row.get("eta_manual") != eta.eta_manual.isoformat()):
            log.append("readback:MISMATCH")
            self._safe_rollback(car_id, previous, log)
            self._queue_retry(car_id, days)
            return TransactionResult(success=False, car_id=car_id, error="readback_mismatch",
                                      rolled_back=True, retry_queued=True, steps_log=log)
        log.append("readback:MATCH")

        ok = True
        try:
            ok = ok and self.publisher.rebuild_card(car_id)
            log.append(f"rebuild_card:{'OK' if ok else 'FAIL'}")
            ok = ok and self.publisher.rebuild_catalogs()
            log.append(f"rebuild_catalogs:{'OK' if ok else 'FAIL'}")
            ok = ok and self.publisher.publish_video(car_id)
            log.append(f"publish_video:{'OK' if ok else 'FAIL'}")
            ok = ok and self.publisher.publish_site(car_id)
            log.append(f"publish_site:{'OK' if ok else 'FAIL'}")
        except Exception as e:
            ok = False
            log.append(f"publish:EXCEPTION:{e}")

        if not ok:
            self._safe_rollback(car_id, previous, log)
            self._queue_retry(car_id, days)
            return TransactionResult(success=False, car_id=car_id, error="publisher_failed",
                                      rolled_back=True, retry_queued=True, steps_log=log)

        self.db.commit(car_id)
        log.append("commit:OK")
        self._retry_queue.pop(car_id, None)
        return TransactionResult(success=True, car_id=car_id, days_to_kyiv=eta.days_to_kyiv,
                                  eta_manual=eta.eta_manual.isoformat(), steps_log=log)

    def _readback_with_timeout(self, car_id: str) -> dict:
        start = time.monotonic()
        last_err = None
        while time.monotonic() - start < self.readback_timeout_s:
            try:
                return self.db.read_back(car_id)
            except Exception as e:
                last_err = e
                time.sleep(0.01)
        raise TimeoutError(str(last_err) if last_err else "readback timeout")

    def _safe_rollback(self, car_id: str, previous: Optional[dict], log: List[str]) -> None:
        if previous is None:
            log.append("rollback:SKIPPED_NO_PRIOR_STATE")
            return
        try:
            self.db.rollback(car_id, previous)
            log.append("rollback:OK")
        except Exception as e:
            log.append(f"rollback:FAIL:{e}")

    def _queue_retry(self, car_id: str, days: int) -> None:
        self._retry_queue[car_id] = days

    def has_pending_retry(self, car_id: str) -> bool:
        return car_id in self._retry_queue

    def process_retries(self) -> List[TransactionResult]:
        results = []
        for car_id, days in list(self._retry_queue.items()):
            results.append(self.submit(car_id, days))
        return results
