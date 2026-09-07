#!/usr/bin/env python3
"""Targeted VIN readiness coordinator.

The coordinator never publishes and never toggles ``cars.published``.  It
closes the race between saving a VIN and pressing the publish button by asking
the backend to process the exact UID ahead of the generic backlog, then running
the single authoritative preflight.
"""
from __future__ import annotations

import dataclasses
import time
from typing import Any, Callable, Mapping, Protocol

from recovery_core import (
    PreflightResult,
    SpecRevision,
    WorkerHealth,
    canonical_uid,
    normalize_vin,
    publication_preflight,
)


TERMINAL = frozenset({"READY", "NEEDS_REVIEW", "FAILED", "SUPERSEDED"})
IN_PROGRESS = frozenset({"NOT_QUEUED", "PENDING", "RUNNING", "PROCESSING"})


class VinBackend(Protocol):
    def load_card(self, uid: str) -> Mapping[str, Any] | None: ...

    def enqueue_exact(self, uid: str, vin: str) -> Mapping[str, Any]: ...

    def process_exact(self, uid: str, vin: str) -> Mapping[str, Any]: ...

    def job_state(self, uid: str, vin: str) -> Mapping[str, Any]: ...

    def active_spec(self, uid: str) -> SpecRevision | None: ...

    def worker_health(self) -> WorkerHealth | Mapping[str, Any] | None: ...

    def duplicate_active_uids(self, uid: str, vin: str) -> tuple[str, ...]: ...


@dataclasses.dataclass(frozen=True)
class PreparationResult:
    uid: str
    state: str
    job_id: int | None
    attempts: int
    preflight: PreflightResult | None
    detail: str
    elapsed_seconds: float

    @property
    def ready(self) -> bool:
        return bool(self.preflight and self.preflight.ok and self.state == "READY")


def _job_fields(value: Mapping[str, Any] | None) -> tuple[str, int | None, int, str]:
    value = value or {}
    state = str(value.get("status") or "NOT_QUEUED").upper()
    job_id = value.get("id")
    try:
        job_id = int(job_id) if job_id is not None else None
    except (TypeError, ValueError):
        job_id = None
    try:
        attempts = int(value.get("attempts") or 0)
    except (TypeError, ValueError):
        attempts = 0
    detail = str(value.get("last_error") or value.get("detail") or "")[:500]
    return state, job_id, attempts, detail


def handle_saved_vin(
    backend: VinBackend,
    *,
    uid: str,
    vin: str,
    process_now: bool = True,
) -> PreparationResult:
    """Idempotently queue a VIN and prioritize this exact card."""

    started = time.monotonic()
    uid, vin = canonical_uid(uid), normalize_vin(vin)
    queued = backend.enqueue_exact(uid, vin)
    state, job_id, attempts, detail = _job_fields(queued)
    if process_now and state in IN_PROGRESS:
        processed = backend.process_exact(uid, vin)
        state, job_id, attempts, detail = _job_fields(processed)
    return PreparationResult(
        uid=uid,
        state=state,
        job_id=job_id,
        attempts=attempts,
        preflight=None,
        detail=detail,
        elapsed_seconds=max(0.0, time.monotonic() - started),
    )


def prepare_for_publish(
    backend: VinBackend,
    *,
    uid: str,
    expected_vin: str,
    timeout_seconds: float = 8.0,
    poll_seconds: float = 0.10,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], Any] = time.sleep,
) -> PreparationResult:
    """Reach READY for exactly ``uid+vin`` or return a precise non-ready state."""

    uid, expected_vin = canonical_uid(uid), normalize_vin(expected_vin)
    started = monotonic()
    deadline = started + max(0.0, float(timeout_seconds))
    backend.enqueue_exact(uid, expected_vin)
    processed_once = False

    while True:
        card = backend.load_card(uid)
        if card is None:
            return PreparationResult(
                uid, "CARD_NOT_FOUND", None, 0, None, "", monotonic() - started
            )
        try:
            current_vin = normalize_vin(card.get("vin"))
        except Exception:
            current_vin = ""
        if current_vin != expected_vin:
            return PreparationResult(
                uid,
                "SUPERSEDED",
                None,
                0,
                None,
                "CARD_VIN_CHANGED",
                monotonic() - started,
            )

        raw = backend.job_state(uid, expected_vin)
        state, job_id, attempts, detail = _job_fields(raw)
        if state in {"NOT_QUEUED", "PENDING", "NEEDS_REVIEW", "FAILED"} and not processed_once:
            raw = backend.process_exact(uid, expected_vin)
            processed_once = True
            state, job_id, attempts, detail = _job_fields(raw)

        if state == "READY":
            active = backend.active_spec(uid)
            preflight = publication_preflight(
                uid=uid,
                vin=expected_vin,
                card=card,
                active_spec=active,
                worker_health=backend.worker_health(),
                duplicate_active_uids=backend.duplicate_active_uids(uid, expected_vin),
            )
            if preflight.ok:
                return PreparationResult(
                    uid,
                    "READY",
                    job_id,
                    attempts,
                    preflight,
                    "",
                    monotonic() - started,
                )
            detail = ";".join(preflight.codes)
            # READY from the old service is not authoritative when the shared
            # >=10-visible/base/heartbeat gate fails.
            state = "NOT_PUBLIC_READY"
            return PreparationResult(
                uid,
                state,
                job_id,
                attempts,
                preflight,
                detail,
                monotonic() - started,
            )

        if state in {"SUPERSEDED"}:
            return PreparationResult(
                uid, state, job_id, attempts, None, detail, monotonic() - started
            )
        if state in {"FAILED", "NEEDS_REVIEW"} and processed_once:
            return PreparationResult(
                uid, state, job_id, attempts, None, detail, monotonic() - started
            )
        if monotonic() >= deadline:
            return PreparationResult(
                uid,
                "PENDING" if state in IN_PROGRESS else state,
                job_id,
                attempts,
                None,
                detail or "VIN_PREPARATION_TIMEOUT",
                monotonic() - started,
            )
        sleeper(max(0.0, min(float(poll_seconds), deadline - monotonic())))

