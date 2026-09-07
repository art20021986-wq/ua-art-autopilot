from __future__ import annotations

import datetime as dt

from recovery_core import SpecFact, WorkerHealth, activate_candidate, build_candidate_revision
from vin_ingestion import handle_saved_vin, prepare_for_publish


VIN = "1HGBH41JXMN109186"  # Synthetic fixture; not the VIN of UA-0017.


def card():
    return {
        "brand": "Mercedes-Benz",
        "model": "B-Class",
        "year": "2010",
        "vin": VIN,
        "fuel": "бензин",
        "engine_cc": 1700,
        "gearbox": "автомат",
        "drive": "передний",
        "mileage_km": 104000,
        "color": "белая",
    }


def active(count=10):
    rows = [
        SpecFact(f"f{i}", f"F{i}", str(i), source_domains=("auto-data.net",))
        for i in range(count)
    ]
    candidate = build_candidate_revision(
        "UA-0017", VIN, "P1", rows, revision_id="r1"
    )
    return activate_candidate(None, candidate)[1]


class Backend:
    def __init__(self):
        self.job = {"id": 1, "status": "NOT_QUEUED", "attempts": 0}
        self.process_calls = 0
        self.enqueue_calls = 0
        self.spec = None
        self.duplicates = ()

    def load_card(self, uid):
        return card()

    def enqueue_exact(self, uid, vin):
        self.enqueue_calls += 1
        if self.job["status"] == "NOT_QUEUED":
            self.job = {"id": 1, "status": "PENDING", "attempts": 0}
        return dict(self.job)

    def process_exact(self, uid, vin):
        self.process_calls += 1
        self.spec = active()
        self.job = {"id": 1, "status": "READY", "attempts": 1}
        return dict(self.job)

    def job_state(self, uid, vin):
        return dict(self.job)

    def active_spec(self, uid):
        return self.spec

    def worker_health(self):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        return WorkerHealth("worker-1", now, now)

    def duplicate_active_uids(self, uid, vin):
        return self.duplicates


def test_saved_vin_targets_exact_job() -> None:
    backend = Backend()
    result = handle_saved_vin(backend, uid="UA-0017", vin=VIN)
    assert result.state == "READY"
    assert backend.process_calls == 1


def test_immediate_publish_prepares_before_readiness_check() -> None:
    backend = Backend()
    result = prepare_for_publish(backend, uid="UA-0017", expected_vin=VIN)
    assert result.ready
    assert result.preflight.visible_spec_rows == 10
    # A repeated click reuses READY state and does not process another job.
    again = prepare_for_publish(backend, uid="UA-0017", expected_vin=VIN)
    assert again.ready
    assert backend.process_calls == 1


def test_duplicate_active_vin_blocks_publish_with_precise_reason() -> None:
    backend = Backend()
    backend.duplicates = ("UA-0002",)
    result = prepare_for_publish(backend, uid="UA-0017", expected_vin=VIN)
    assert not result.ready
    assert result.state == "NOT_PUBLIC_READY"
    assert "DUPLICATE_ACTIVE_VIN:UA-0002" in result.detail


def test_timeout_remains_pending_without_publish() -> None:
    backend = Backend()

    def never_ready(uid, vin):
        backend.process_calls += 1
        backend.job = {"id": 1, "status": "RUNNING", "attempts": 1}
        return dict(backend.job)

    backend.process_exact = never_ready
    result = prepare_for_publish(
        backend, uid="UA-0017", expected_vin=VIN, timeout_seconds=0
    )
    assert not result.ready
    assert result.state == "PENDING"
    assert backend.spec is None
