"""In-memory CRM adapter used ONLY for offline unit/integration tests.

Mirrors the fields relevant to ETA: days_to_kyiv, eta_manual, updated_at.
Not connected to any real database; contains no production data.
"""
from typing import Dict


class MockCrmDb:
    def __init__(self):
        self.rows: Dict[str, dict] = {}
        self.fail_after_first_field = False
        self.fail_readback_once = False
        self._readback_failed_once = set()

    def seed(self, car_id, **fields):
        self.rows[car_id] = dict(fields)

    def begin(self, car_id):
        pass

    def write_eta(self, car_id, days_to_kyiv, eta_manual, updated_at):
        row = self.rows.setdefault(car_id, {})
        row["days_to_kyiv"] = days_to_kyiv
        if self.fail_after_first_field:
            raise RuntimeError("simulated failure after first field write")
        row["eta_manual"] = eta_manual
        row["updated_at"] = updated_at

    def read_back(self, car_id):
        if self.fail_readback_once and car_id not in self._readback_failed_once:
            self._readback_failed_once.add(car_id)
            raise RuntimeError("simulated queue/read-back timeout")
        return dict(self.rows.get(car_id, {}))

    def rollback(self, car_id, previous):
        if previous:
            self.rows[car_id] = dict(previous)

    def commit(self, car_id):
        pass
