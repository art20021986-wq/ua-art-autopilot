"""Bounded queue -> provisioned collector -> source policy -> durable store service.

No network transport, thread, daemon, publication or live CRM is started here.
An explicit runtime binding may call run_once after verified installation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
import hashlib
import json
import re
import time
from typing import Any, Callable, Mapping

try:
    from . import sources
    from .store import SpecStore, StaleJobError, StoreError
except ImportError:  # Standalone offline execution from this directory.
    import sources
    from store import SpecStore, StaleJobError, StoreError

POLICY_ID = "UA-ART-SPEC-REBUILD-10-001:v1"
MAX_RUN_SECONDS = 120.0


@dataclass(frozen=True)
class CollectionRequest:
    source_id: str
    uid: str
    revision: int
    identity_hash: str
    identity: Mapping[str, Any]
    timeout_seconds: float
    max_bytes: int = sources.MAX_RESPONSE_BYTES


@dataclass(frozen=True)
class CollectedDocument:
    source_id: str
    payload: Any = field(default=None, repr=False)
    source_url: str | None = None
    authorization: sources.ImportAuthorization | None = field(default=None, repr=False)
    outcome: str = "OK"


@dataclass(frozen=True)
class CollectorBinding:
    source_id: str
    collect: Callable[[CollectionRequest], CollectedDocument] = field(repr=False)
    access: sources.AccessGrant | None = field(default=None, repr=False)


def vpic_collector(transport: Callable[[sources.Request], sources.Response] | None) -> CollectorBinding:
    """Concrete vPIC adapter using the explicitly supplied bounded HTTPS transport."""
    if transport is None or not callable(transport):
        raise sources.SourceError("TRANSPORT_NOT_CONFIGURED")
    def collect(request: CollectionRequest) -> CollectedDocument:
        vin = str(request.identity.get("vin", "")).upper()
        if not sources.VIN.fullmatch(vin):
            return CollectedDocument("vpic", outcome="NO_MATCH")
        url = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValuesExtended/" + vin + "?format=json"
        year = request.identity.get("year")
        if year is not None:
            if not re.fullmatch(r"(?:19|20)\d{2}", str(year)):
                raise sources.SourceError("IDENTITY_INVALID")
            url += "&modelyear=" + str(year)
        response = sources.fetch_source("vpic", url, transport=transport,
            max_bytes=request.max_bytes, timeout_seconds=request.timeout_seconds)
        return CollectedDocument("vpic", response.body, source_url=url)
    return CollectorBinding("vpic", collect)


def source_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve field-name aliases only. Never invent market, year, trim or model."""
    result = dict(identity)
    aliases = {"make": ("make", "brand", "manufacturer"),
        "year": ("year", "model_year"), "market": ("market", "origin_market"),
        "gearbox": ("gearbox", "transmission"), "fuel": ("fuel", "fuel_type"),
        "engine": ("engine", "engine_code"),
        "engine_cc": ("engine_cc", "displacement_cc"), "trim": ("trim", "variant")}
    for canonical, names in aliases.items():
        values = [identity[name] for name in names if identity.get(name) not in (None, "")]
        normalized = {" ".join(str(value).casefold().split()) for value in values}
        if len(normalized) > 1:
            raise sources.SourceError("IDENTITY_ALIAS_CONFLICT")
        if values:
            result[canonical] = values[0]
    return result


def acceptance_evidence(fact: Mapping[str, Any], job: Mapping[str, Any]) -> dict[str, Any]:
    """Bind the policy decision to exact accepted fact content and queue revision."""
    value = copy.deepcopy(dict(fact))
    value["identity_hash"] = job["identity_hash"]
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    value["policy_acceptance"] = {"policy_id": POLICY_ID, "decision": "ACCEPTED",
        "uid": job["uid"], "revision": job["revision"], "identity_hash": job["identity_hash"],
        "source_ids": value["provenance"]["corroborating_sources"],
        "evidence_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}
    return value


class SpecWorker:
    def __init__(self, store: SpecStore, collectors: Mapping[str, CollectorBinding] | None = None,
                 *, worker_id: str = "spec-rebuild10", max_run_seconds: float = 90.0,
                 lease_seconds: int = 120, retry_after: float = 60.0,
                 clock: Callable[[], float] = time.time,
                 monotonic: Callable[[], float] = time.monotonic):
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", worker_id):
            raise sources.SourceError("WORKER_ID_INVALID")
        if (isinstance(max_run_seconds, bool) or not 0 < max_run_seconds <= MAX_RUN_SECONDS
                or isinstance(lease_seconds, bool) or not max_run_seconds + 5 <= lease_seconds <= 900
                or not 0 <= retry_after <= 86400):
            raise sources.SourceError("WORKER_LIMITS_INVALID")
        self.store, self.worker_id = store, worker_id
        self.max_run_seconds, self.lease_seconds, self.retry_after = max_run_seconds, lease_seconds, retry_after
        self.clock, self.monotonic = clock, monotonic
        self.registry = sources.load_registry()
        self.collectors = dict(collectors or {})
        for key, binding in self.collectors.items():
            if (key not in self.registry or not isinstance(binding, CollectorBinding)
                    or binding.source_id != key or not callable(binding.collect)):
                raise sources.SourceError("COLLECTOR_BINDING_INVALID")
            sources._check_access(self.registry[key], binding.access)

    def readiness(self) -> dict[str, Any]:
        states = {}
        for source_id, source in self.registry.items():
            states[source_id] = {"state": "CONFIGURED_NOT_RUN" if source_id in self.collectors else
                ("TRANSPORT_NOT_CONFIGURED" if source_id == "vpic" else "NOT_PROVISIONED"),
                "live_acceptance": "NOT_TESTED"}
        return {"sources": states, "configured": len(self.collectors), "selected": 10,
                "all_sources_provisioned": len(self.collectors) == 10}

    def _current(self, job: Mapping[str, Any]) -> None:
        vehicle = self.store.get_vehicle(job["uid"])
        if (vehicle["tombstoned"] or vehicle["revision"] != job["revision"]
                or vehicle["identity_hash"] != job["identity_hash"]):
            raise StaleJobError("vehicle identity changed or was deleted")
        if self.clock() >= job["lease_until"]:
            raise StaleJobError("lease expired")

    def _failure(self, job: Mapping[str, Any], report: dict, code: str) -> dict:
        # Fixed codes only: arbitrary supplier exception text is never persisted.
        report["error"] = code
        try:
            outcome = self.store.fail_job(job["id"], job["lease_token"], code,
                retry_after=self.retry_after, now=self.clock())
            report["status"] = "EXHAUSTED" if outcome["state"] == "exhausted" else "RETRY_SCHEDULED"
            report["queue_state"] = outcome["state"]
        except StaleJobError:
            report["status"] = "STALE_RESULT_DISCARDED"
        return report

    def run_once(self) -> dict[str, Any]:
        """Process at most one durable job; stop collection on first real error.

        Injected collectors must honor timeout/byte limits. No generic untrusted
        callable can be forcibly cancelled by this synchronous service; a runtime
        must supply the bounded source transport. Late results never commit.
        """
        report = {"worker_id": self.worker_id, "publication_performed": False,
            "app_writes": 0, "new_store_writes_only": True, **self.readiness()}
        if not self.collectors:
            return dict(report, status="BLOCKED_NO_PROVISIONED_COLLECTORS", job_id=None)
        job = self.store.claim_job(self.worker_id, lease_seconds=self.lease_seconds, now=self.clock())
        if job is None:
            return dict(report, status="IDLE", job_id=None)
        report.update({"job_id": job["id"], "uid": job["uid"], "revision": job["revision"],
            "identity_hash": job["identity_hash"], "attempt": job["attempts"]})
        started = self.monotonic()
        try:
            target = source_identity(job["identity"])
            candidates = []
            for source_id, binding in self.collectors.items():
                self._current(job)
                remaining = self.max_run_seconds - (self.monotonic() - started)
                if remaining <= 0:
                    raise sources.SourceError("WORKER_TIME_BUDGET_EXHAUSTED")
                request = CollectionRequest(source_id, job["uid"], job["revision"],
                    job["identity_hash"], copy.deepcopy(target), min(remaining, sources.MAX_TOTAL_SECONDS))
                try:
                    collected = binding.collect(request)
                except sources.SourceError:
                    raise
                except Exception:
                    raise sources.SourceError("COLLECTOR_FAILED") from None
                self._current(job)
                if self.monotonic() - started > self.max_run_seconds:
                    raise sources.SourceError("WORKER_TIME_BUDGET_EXHAUSTED")
                if not isinstance(collected, CollectedDocument) or collected.source_id != source_id:
                    raise sources.SourceError("COLLECTOR_SOURCE_IMPERSONATION")
                if collected.outcome == "NO_MATCH":
                    report["sources"][source_id].update(state="NO_MATCH", live_acceptance="CONTROL_CASE_NO_MATCH")
                    continue
                if collected.outcome != "OK":
                    raise sources.SourceError("COLLECTOR_UNAVAILABLE")
                if source_id == "vpic":
                    facts = sources.parse_vpic(collected.payload, target, source_url=collected.source_url)
                else:
                    facts = sources.parse_normalized_import(source_id, collected.payload, target,
                        access=binding.access, authorization=collected.authorization, registry=self.registry)
                candidates.extend(facts)
                report["sources"][source_id].update(state="PARSED_CONTROL_CASE", candidates=len(facts),
                    live_acceptance="DOCUMENT_PARSED_NOT_FULL_ADAPTER_ACCEPTANCE")
            self._current(job)
            resolution = sources.resolve_facts(candidates, target, self.registry)
            approved = [acceptance_evidence(row, job) for row in resolution["accepted"]]
            # Pending rows retain their unverified status and enter durable review.
            pending = [dict(row, identity_hash=job["identity_hash"]) for row in resolution["pending"]]
            rejected = [{**row, "value": None, "source_policy_rejection": row["reason"],
                "identity_hash": job["identity_hash"]} for row in resolution["rejected"]]
            decision = self.store.approve_candidates(job["id"], job["lease_token"], approved + pending + rejected,
                                                      now=self.clock())
            report.update({"status": "COLLECTED" if decision["accepted"] else "NO_NEW_CONFIRMED_FACTS",
                "queue_state": "succeeded", "accepted": decision["accepted"], "review": decision["review"],
                "rejected": decision["rejected"],
                "source_policy_accepted": len(approved),
                "all_ten_live_acceptance": False})
            return report
        except StaleJobError:
            return dict(report, status="STALE_RESULT_DISCARDED", error="LEASE_OR_IDENTITY_CHANGED")
        except sources.SourceError as error:
            if "source_id" in locals():
                report["sources"][source_id].update(state="ERROR", error=error.code)
            return self._failure(job, report, error.code)
        except StoreError:
            return self._failure(job, report, "STORE_REJECTED_OPERATION")
        except Exception:
            return self._failure(job, report, "WORKER_INTERNAL_ERROR")


def bind_worker(store: SpecStore, collectors: Mapping[str, CollectorBinding],
                *, installation_receipt: Mapping[str, Any],
                verify_installation: Callable[[Mapping[str, Any]], bool], **options) -> SpecWorker:
    """Explicit runtime handoff binding, without starting an old or new daemon.

    The authenticating verifier belongs to the approved installation route. A
    receipt's own PASS text is insufficient. This API cannot stop legacy writers.
    """
    if not callable(verify_installation) or verify_installation(installation_receipt) is not True:
        raise sources.SourceError("VERIFIED_INSTALLATION_HANDOFF_REQUIRED")
    if (installation_receipt.get("module") != "spec_rebuild10"
            or installation_receipt.get("old_workers_stopped") is not True
            or installation_receipt.get("exclusive_owner") is not True
            or not installation_receipt.get("receipt_id")):
        raise sources.SourceError("VERIFIED_INSTALLATION_HANDOFF_REQUIRED")
    return SpecWorker(store, collectors, **options)
