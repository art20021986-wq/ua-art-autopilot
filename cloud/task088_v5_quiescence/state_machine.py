"""Isolated quiescence protocol prototype. No provider client or executor.

Only a reviewed integration may supply authenticated observations or consume
intents. This module cannot create a canonical Gate, claim, writer PASS, or
production authorization. Its journal is local and its outputs are NOT permits
accepted by the existing installation adapter.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
from pathlib import Path


class Rejected(ValueError):
    pass


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def sha(value):
    require(isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value), "SHA256_REQUIRED")
    return value


def validate_plan(plan):
    require(plan.get("contract") == "TASK088-ISOLATED-QUIESCENCE-PROTOTYPE-1", "PROTOTYPE_PLAN_REQUIRED")
    for key in ("task_id", "operation_id"):
        require(isinstance(plan.get(key), str) and re.fullmatch("[A-Za-z0-9._-]{8,120}", plan[key]), "IDENTITY_REQUIRED")
    for key in ("reviewed_code_sha256", "authorization_sha256", "inventory_sha256", "before_sources_sha256", "candidate_sources_sha256"):
        sha(plan.get(key))
    supervisors = plan.get("supervisors")
    require(isinstance(supervisors, list) and supervisors, "SUPERVISOR_SCOPE_REQUIRED")
    require(all(set(s) == {"id", "command", "enabled"} and type(s["id"]) is int and s["id"] > 0
                and isinstance(s["command"], str) and s["command"] and s["enabled"] is True for s in supervisors), "EXACT_PREVIOUS_CONFIGURATION_REQUIRED")
    ids = {s["id"] for s in supervisors}
    require(len(ids) == len(supervisors), "DUPLICATE_SUPERVISOR")
    crm = [s for s in supervisors if s["id"] == 266084]
    require(len(crm) == 1 and crm[0]["command"] == "python3.10 /home/Carix/start_safe.py", "EXACT_EXISTING_CRM_IDENTITY_REQUIRED")
    writers = plan.get("writers")
    require(isinstance(writers, list) and writers and len({w.get("id") for w in writers}) == len(writers), "EXACT_WRITER_SCOPE_REQUIRED")
    for writer in writers:
        require(isinstance(writer.get("id"), str) and writer["id"], "WRITER_ID_REQUIRED")
        sha(writer.get("source_sha256"))
        sha(writer.get("candidate_source_sha256"))
        mode = writer.get("mode")
        require(mode in {"MANAGED_PROCESS", "HELD_LOCK", "READ_ONLY"}, "UNKNOWN_WRITER_MUST_REMAIN_BLOCKED")
        if mode == "MANAGED_PROCESS":
            require(writer.get("supervisor_id") in ids, "UNMANAGED_PROCESS_WRITER")
        elif mode == "HELD_LOCK":
            require(isinstance(writer.get("lock_path"), str) and writer["lock_path"].startswith("/home/Carix/"), "EXACT_EXISTING_LOCK_REQUIRED")
    return plan


class Journal:
    """One writer, hash-chained, fsynced records; damaged tails fail closed."""

    def __init__(self, path, plan):
        self.path = Path(path)
        self.plan_sha = digest(validate_plan(plan))
        self.fd = os.open(self.path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            require(stat.S_ISREG(os.fstat(self.fd).st_mode) and stat.S_IMODE(os.fstat(self.fd).st_mode) == 0o600,
                    "PRIVATE_REGULAR_JOURNAL_REQUIRED")
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with os.fdopen(os.dup(self.fd), "rb") as handle:
                handle.seek(0)
                raw = handle.read()
            require(not raw or raw.endswith(b"\n"), "JOURNAL_TRUNCATED_RECONCILE_REQUIRED")
            self.records = []
            previous = "0" * 64
            for line in raw.splitlines():
                record = json.loads(line)
                recorded = record.pop("sha256")
                require(record.get("previous_sha256") == previous and record.get("sequence") == len(self.records)
                        and record.get("plan_sha256") == self.plan_sha and digest(record) == recorded, "JOURNAL_INTEGRITY_OR_PLAN_DRIFT")
                record["sha256"] = recorded
                self.records.append(record)
                previous = recorded
            self.poisoned = False
        except BaseException:
            os.close(self.fd)
            raise

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def append(self, state, facts, intents):
        require(not self.poisoned, "JOURNAL_DURABILITY_UNKNOWN_REOPEN_REQUIRED")
        record = {"sequence": len(self.records), "previous_sha256": self.records[-1]["sha256"] if self.records else "0" * 64,
                  "plan_sha256": self.plan_sha, "state": state, "facts_sha256": digest(facts), "intents": intents}
        record["sha256"] = digest(record)
        raw = encoded(record) + b"\n"
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(self.fd, raw[offset:])
                require(written > 0, "JOURNAL_WRITE_FAILED")
                offset += written
            os.fsync(self.fd)
            parent = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        except BaseException:
            self.poisoned = True
            raise
        self.records.append(json.loads(encoded(record)))
        return json.loads(encoded(intents))


class Protocol:
    """Pure transition checks plus durable local intent recording.

    Observation schema is normalized, NOT an evidence collector. In particular
    membership_complete needs actual provider/process containment evidence.
    An empty process list from another host/container never satisfies it.
    """

    def __init__(self, plan, journal, *, clock):
        self._plan_raw = encoded(validate_plan(json.loads(encoded(plan))))
        require(hashlib.sha256(self._plan_raw).hexdigest() == journal.plan_sha, "JOURNAL_PLAN_MISMATCH")
        self.journal = journal
        self.clock = clock

    @property
    def plan(self):
        return json.loads(self._plan_raw)

    @property
    def state(self):
        return self.journal.records[-1]["state"] if self.journal.records else "NEW"

    def _state(self, *allowed):
        require(hashlib.sha256(self._plan_raw).hexdigest() == self.journal.plan_sha, "JOURNAL_PLAN_MISMATCH")
        require(self.state in allowed, "STATE_REQUIRES_RECONCILIATION:" + self.state)

    def _observation(self, obs):
        require(obs.get("operation_id") == self.plan["operation_id"] and obs.get("inventory_sha256") == self.plan["inventory_sha256"], "OBSERVATION_SCOPE_MISMATCH")
        observed = obs.get("observed_at")
        require(type(observed) in (int, float) and 0 <= self.clock() - observed <= 30, "FRESH_ACTUAL_OBSERVATION_REQUIRED")
        sha(obs.get("raw_evidence_sha256"))
        require(obs.get("unaccounted_writers") == [], "UNACCOUNTED_WRITER")
        actual = obs.get("supervisors", [])
        require(len(actual) == len(self.plan["supervisors"]) and len({s.get("id") for s in actual}) == len(actual), "SUPERVISOR_SET_MISMATCH")
        by_id = {s["id"]: s for s in actual}
        for expected in self.plan["supervisors"]:
            current = by_id.get(expected["id"], {})
            require(current.get("command") == expected["command"] and type(current.get("enabled")) is bool
                    and type(current.get("running")) is bool, "EXACT_SUPERVISOR_IDENTITY_DRIFT")
        return by_id

    def _quiesced(self, obs, *, version="BEFORE"):
        require(version in {"BEFORE", "AFTER"}, "EXACT_WRITER_VERSION_REQUIRED")
        supervisors = self._observation(obs)
        for current in supervisors.values():
            require(current["enabled"] is False and current["running"] is False, "PROVIDER_STOP_NOT_CONFIRMED")
            require(current.get("membership_complete") is True and current.get("live_process_count") == 0
                    and current.get("in_flight_mutations") == 0, "COMPLETE_PROCESS_AND_WORK_DRAIN_REQUIRED")
            sha(current.get("membership_evidence_sha256"))
        listed = obs.get("writers", [])
        require(len(listed) == len(self.plan["writers"]) and len({w.get("id") for w in listed}) == len(listed), "WRITER_OBSERVATION_SET_MISMATCH")
        actual = {w["id"]: w for w in listed}
        for expected in self.plan["writers"]:
            current = actual.get(expected["id"], {})
            source_key = "candidate_source_sha256" if version == "AFTER" else "source_sha256"
            require(current.get("source_sha256") == expected[source_key], "WRITER_SOURCE_DRIFT")
            sha(current.get("evidence_sha256"))
            mode = expected["mode"]
            if mode == "MANAGED_PROCESS":
                require(current.get("supervisor_id") == expected["supervisor_id"] and current.get("status") == "STOPPED_AND_DRAINED", "MANAGED_WRITER_NOT_DRAINED")
            elif mode == "HELD_LOCK":
                require(current.get("lock_path") == expected["lock_path"] and current.get("status") == "LOCK_HELD_AND_DRAINED"
                        and current.get("lease_operation_id") == self.plan["operation_id"], "COOPERATIVE_LOCK_NOT_HELD")
            else:
                require(current.get("status") == "READ_ONLY_PROVEN", "READ_ONLY_EFFECTS_NOT_PROVEN")

    def _coherence(self, obs):
        proof = obs.get("coherence", {})
        version = proof.get("version")
        require(version in {"BEFORE", "AFTER"}, "UNKNOWN_OR_MIXED_INSTALLATION")
        expected = self.plan["candidate_sources_sha256" if version == "AFTER" else "before_sources_sha256"]
        require(proof.get("sources_sha256") == expected, "COHERENT_SOURCE_SET_REQUIRED")
        for key in ("complete_file_readback", "independent_database_readback", "schema_matches_version", "operator_changes_preserved",
                    "protected_nonprice_content_preserved", "no_in_flight_installation"):
            require(proof.get(key) is True, "COHERENCE_CHECK_REQUIRED:" + key)
        require(proof.get("backup_database_restored") is False, "OLD_DATABASE_RESTORE_FORBIDDEN")
        sha(proof.get("raw_evidence_sha256"))
        return version

    def _record(self, state, facts, kinds):
        intents = [{"kind": kind, "operation_id": self.plan["operation_id"], "sequence": len(self.journal.records), **details}
                   for kind, details in kinds]
        return self.journal.append(state, facts, intents)

    def begin_pause(self, obs):
        self._state("NEW")
        current = self._observation(obs)
        require(all(s["enabled"] is True and s["running"] is True for s in current.values()), "EXACT_INITIAL_RUNNING_STATE_REQUIRED")
        return self._record("PAUSE_PENDING", obs, [("PATCH_ENABLED_FALSE", {"supervisor_id": s["id"], "expected_command": s["command"]}) for s in self.plan["supervisors"]])

    def outcome_unknown(self):
        self._state("PAUSE_PENDING", "APPLY_PENDING", "RESUME_PENDING")
        return self._record(self.state.replace("PENDING", "UNKNOWN"), {}, [("READ_ONLY_RECONCILE", {})])

    def reconcile_pause(self, obs):
        self._state("PAUSE_PENDING", "PAUSE_UNKNOWN")
        self._quiesced(obs)
        return self._record("QUIESCED", obs, [])

    def installation_boundary(self, obs):
        self._state("QUIESCED")
        self._quiesced(obs)
        require(obs.get("canonical_install_admission_pass") is True, "EXISTING_CANONICAL_GATES_STILL_REQUIRED")
        sha(obs.get("canonical_admission_evidence_sha256"))
        return self._record("APPLY_PENDING", obs, [("PROTOTYPE_INSTALL_BOUNDARY_ONLY", {"production_authorization": False})])

    def reconcile_installation(self, obs):
        self._state("APPLY_PENDING", "APPLY_UNKNOWN", "QUIESCED")
        self._observation(obs)
        version = self._coherence(obs)
        if self.state == "QUIESCED":
            require(version == "BEFORE", "UNISSUED_INSTALLATION_CANNOT_BE_CLAIMED")
        self._quiesced(obs, version=version)
        return self._record("COHERENT_" + version, obs, [])

    def begin_resume(self, obs):
        self._state("COHERENT_BEFORE", "COHERENT_AFTER")
        self._quiesced(obs, version=self.state.removeprefix("COHERENT_"))
        require("COHERENT_" + self._coherence(obs) == self.state, "COHERENCE_CHANGED_BEFORE_RESUME")
        return self._record("RESUME_PENDING", obs, [("PATCH_ENABLED_TRUE", {"supervisor_id": s["id"], "expected_command": s["command"]}) for s in self.plan["supervisors"]])

    def reconcile_resume(self, obs):
        self._state("RESUME_PENDING", "RESUME_UNKNOWN")
        current = self._observation(obs)
        require(all(s["enabled"] is True and s["running"] is True and s.get("exactly_one_instance") is True for s in current.values()), "EXACT_PREVIOUS_SERVICE_NOT_RESTORED")
        version = self._coherence(obs)
        prior = [r["state"] for r in self.journal.records if r["state"].startswith("COHERENT_")]
        require(prior and prior[-1] == "COHERENT_" + version, "RESUMED_VERSION_DRIFT")
        require(obs.get("loaded_sources_sha256") == obs["coherence"]["sources_sha256"], "ACTUAL_LOADED_CODE_PROOF_REQUIRED")
        return self._record("RESTORED_PENDING_LIVE_ACCEPTANCE", obs, [])
