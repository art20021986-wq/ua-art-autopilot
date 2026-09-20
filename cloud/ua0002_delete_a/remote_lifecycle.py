#!/usr/bin/env python3
"""One bounded UA-0002 retirement worker; credentials stay in provider environment.

The GitHub controller starts this worker before CRM pause. It survives loss of
the GitHub connection, journals pause intent, and reconciles an interrupted
install through its own forward-only retirement recovery before CRM resume.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
COMMAND = "python3.10 /home/Carix/start_safe.py"
SUPERVISOR = 266084

def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))+"\n").encode()

def atomic(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    data = canonical(value)
    with temporary.open("wb") as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

class API:
    def __init__(self):
        self.token = os.environ.get("API_TOKEN", "").strip()
        if not self.token:
            raise RuntimeError("REMOTE_API_TOKEN_UNAVAILABLE_BEFORE_PAUSE")
    def request(self, method, endpoint, fields=None):
        data = urllib.parse.urlencode(fields).encode() if fields is not None else None
        req = urllib.request.Request(BASE+endpoint, data=data, method=method,
            headers={"Authorization":"Token "+self.token,
                     "Content-Type":"application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=40) as response:
            payload = response.read(512*1024)
        return json.loads(payload or b"{}")
    def supervisor(self):
        obj = self.request("GET", "always_on/%d/" % SUPERVISOR)
        if obj.get("id") != SUPERVISOR or obj.get("command") != COMMAND:
            raise RuntimeError("CRM_SUPERVISOR_IDENTITY_DRIFT")
        return obj
    def set_enabled(self, enabled):
        self.supervisor()
        self.request("PATCH", "always_on/%d/" % SUPERVISOR,
                     {"enabled":str(bool(enabled)).lower()})
        deadline = time.monotonic()+180
        while time.monotonic()<deadline:
            obj = self.supervisor()
            if obj.get("enabled") is enabled and (not enabled or str(obj.get("state", "")).lower()=="running"):
                return {"id":SUPERVISOR, "enabled":enabled, "state":str(obj.get("state", ""))}
            time.sleep(3)
        raise RuntimeError("CRM_ENABLE_READBACK_TIMEOUT" if enabled else "CRM_DISABLE_READBACK_TIMEOUT")

def child(operation, plan_path, plan_sha):
    env = dict(os.environ)
    # Provider credential is needed by this lifecycle owner only.
    env.pop("API_TOKEN", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("remote_stage_a.py")),
        "--operation", operation, "--plan", str(plan_path), "--plan-sha256", plan_sha],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1200, env=env, check=False)
    try:
        value = json.loads(result.stdout.decode("utf-8").strip())
    except Exception:
        # Private interpreter trace and source fragments are never copied to a public receipt.
        raise RuntimeError("INSTALLER_RECEIPT_INVALID_EXIT_%d" % result.returncode)
    if value.get("plan_sha256") != plan_sha or value.get("operation") != operation:
        raise RuntimeError("INSTALLER_RECEIPT_IDENTITY_MISMATCH")
    if result.returncode or value.get("status") != "PASS":
        raise RuntimeError("INSTALLER_PHASE_FAILED:"+str(value.get("error_code", "UNSPECIFIED"))[:200])
    return value


def no_mutation_proof(plan_path, plan_sha):
    """Read the same locked durable worker journal; never infer from an error.

    The worker writes RETIRE_STARTED before its first public effect. An
    authenticated observation of an earlier phase proves that a failed
    admission did not alter the site. Any uncertainty remains fail-closed.
    """
    proof = child("recovery_status", plan_path, plan_sha)
    if proof.get("no_mutation") is not True:
        return None
    if proof.get("durable_stage") not in {"NOT_STARTED", "BACKUP_STARTED", "BACKED_UP"}:
        raise RuntimeError("INVALID_NO_MUTATION_DURABLE_STAGE")
    return proof


def provider_admission(api, plan, operation, plan_path, plan_sha, result_path, *, resume=False):
    """Fresh provider inventory and a bounded window before pausing CRM.

    Exact known background commands stay in the private plan. No unknown task
    is stopped or assumed harmless, and the provider token stays in this owner.
    """
    writers = plan.get("writers", {})
    if writers.get("reviewed") is not True:
        raise RuntimeError("PROVIDER_WRITER_REVIEW_REQUIRED")
    expected = writers.get("always_on")
    expected_schedule = writers.get("scheduled")
    if not isinstance(expected, list) or not isinstance(expected_schedule, list):
        raise RuntimeError("PROVIDER_INVENTORY_BINDING_REQUIRED")
    window_end = writers.get("safe_window_end_epoch")
    if not isinstance(window_end, (int, float)) or not time.time() + 1800 < window_end:
        raise RuntimeError("SCHEDULE_QUIET_WINDOW_TOO_SHORT")
    own_command = ("cd " + str(plan_path.parent) + " && python3.10 -B remote_lifecycle.py --operation " + operation
                   + " --plan " + str(plan_path) + " --plan-sha256 " + plan_sha + " --result " + str(result_path))
    def objects(value):
        if isinstance(value, dict):
            value = value.get("results", value.get("objects", value.get("tasks")))
        if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
            raise RuntimeError("PROVIDER_LIST_SHAPE")
        return value
    always = objects(api.request("GET", "always_on/"))
    normalized, own_count = [], 0
    for row in always:
        if row.get("command") == own_command:
            own_count += 1
            continue
        normalized.append({"id": row.get("id"), "command_sha256": hashlib.sha256(str(row.get("command", "")).encode()).hexdigest(),
                           "enabled": row.get("enabled")})
        if resume and row.get("id") == SUPERVISOR and row.get("enabled") is False:
            normalized[-1]["enabled"] = True  # This journal owns the CRM pause.
    if own_count != 1 or sorted(normalized, key=lambda r: r["id"]) != sorted(expected, key=lambda r: r["id"]):
        raise RuntimeError("PROVIDER_ALWAYS_ON_DRIFT")
    scheduled = objects(api.request("GET", "schedule/"))
    normalized_schedule = []
    for row in scheduled:
        normalized_schedule.append({"id": row.get("id"),
            "command_sha256": hashlib.sha256(str(row.get("command", "")).encode()).hexdigest(),
            "hour": row.get("hour"), "minute": row.get("minute"), "interval": row.get("interval"),
            "enabled": row.get("enabled", True)})
    if sorted(normalized_schedule, key=lambda r: r["id"]) != sorted(expected_schedule, key=lambda r: r["id"]):
        raise RuntimeError("PROVIDER_SCHEDULE_DRIFT")
    now = datetime.now(timezone.utc)
    for row in normalized_schedule:
        if row["enabled"] is False:
            continue
        minute, hour = row["minute"], row["hour"]
        if type(minute) is not int or not 0 <= minute < 60:
            raise RuntimeError("SCHEDULE_MINUTE_UNSUPPORTED")
        if row["interval"] == "daily" and type(hour) is int and 0 <= hour < 24:
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
        elif row["interval"] == "hourly":
            next_run = now.replace(minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(hours=1)
        else:
            raise RuntimeError("SCHEDULE_INTERVAL_UNSUPPORTED")
        if (next_run - now).total_seconds() <= 1800:
            raise RuntimeError("SCHEDULE_DUE_DURING_RETIREMENT_WINDOW")
    # The monitor process allowlist is derived from one observed, hash-bound
    # provider command, then compared with the worker's normalized /proc argv.
    approved = next((r for r in always if r.get("id") == 270984), None)
    if approved is None:
        raise RuntimeError("KNOWN_MONITOR_ABSENT")
    argv = shlex.split(approved.get("command", ""))
    if not argv:
        raise RuntimeError("KNOWN_MONITOR_COMMAND_EMPTY")
    argv[0] = Path(argv[0]).name
    compact = json.dumps(argv, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if writers.get("allowed_python_cmdline_sha256") != [hashlib.sha256(compact).hexdigest()]:
        raise RuntimeError("MONITOR_OS_COMMAND_BINDING_MISMATCH")
    return {"observed_epoch": int(time.time()), "always_on_sha256": hashlib.sha256(canonical(normalized)).hexdigest(),
            "scheduled_sha256": hashlib.sha256(canonical(normalized_schedule)).hexdigest()}

def _execute(operation, plan_path, plan_sha, result_path):
    plan_bytes = plan_path.read_bytes()
    if hashlib.sha256(plan_bytes).hexdigest() != plan_sha:
        raise RuntimeError("PLAN_SHA_MISMATCH")
    plan = json.loads(plan_bytes)
    if operation not in {"backup", "install_verify", "rollback"}:
        raise RuntimeError("OPERATION_SCOPE")
    if plan.get("alwayson_id") != SUPERVISOR:
        raise RuntimeError("SUPERVISOR_PLAN_SCOPE")
    result_path = Path(result_path)
    journal_path = result_path.with_suffix(".journal.json")
    api = API()  # Validate credential availability before any CRM change.
    if result_path.exists():
        value = json.loads(result_path.read_text())
        if value.get("plan_sha256") != plan_sha or value.get("operation") != operation:
            raise RuntimeError("REMOTE_RESULT_CONFLICT")
        if value.get("safe_to_stop") is not True:
            raise RuntimeError("REMOTE_RESULT_NOT_TERMINAL")
        return value
    prior = json.loads(journal_path.read_text()) if journal_path.exists() else None
    if prior and (prior.get("plan_sha256") != plan_sha or prior.get("operation") != operation):
        raise RuntimeError("LIFECYCLE_JOURNAL_CONFLICT")
    observed = api.supervisor()
    if not prior and (observed.get("enabled") is not True or str(observed.get("state", "")).lower() != "running"):
        raise RuntimeError("CRM_NOT_RUNNING_BEFORE_PLANNED_PAUSE")
    journal = prior or {"plan_sha256":plan_sha,"operation":operation,"stage":"PAUSE_INTENT"}
    if not prior or journal["stage"] in {"PAUSE_INTENT", "CHILD_STARTED"}:
        expected_sha = plan.get("package_sha256", {}).get("remote_lifecycle.py")
        if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != expected_sha:
            raise RuntimeError("LIFECYCLE_SOURCE_HASH_MISMATCH")
        journal["provider_admission"] = provider_admission(api, plan, operation, plan_path, plan_sha, result_path,
                                                          resume=bool(prior))
    atomic(journal_path, journal)
    if journal["stage"] in {"CHILD_DONE", "RESUME_INTENT", "FINISHED"}:
        # A completed child is never replayed or rolled back after CRM resume.
        value=dict(journal["value"])
    else:
        value = {"plan_sha256":plan_sha,"operation":operation,"status":"FAIL"}
        uncertain_install = bool(prior and prior["stage"]=="CHILD_STARTED" and operation=="install_verify")
        uncertain_mutation = bool(prior and prior["stage"]=="CHILD_STARTED" and operation in {"install_verify","rollback"})
        paused = False
        try:
            api.set_enabled(False)
            paused = True
            journal["stage"] = "CHILD_STARTED"; atomic(journal_path, journal)
            if uncertain_install:
                restored = child("recover", plan_path, plan_sha)
                value.update({"status":"PASS", "installer":restored, "interrupted_install_recovered":True})
            else:
                result = child("recover" if operation == "rollback" else operation, plan_path, plan_sha)
                value.update({"status":"PASS", "installer":result})
        except Exception as exc:
            if uncertain_mutation and not paused:
                # Prior mutation may be incomplete. Preserve CHILD_STARTED;
                # never turn an unconfirmed pause into permission to resume.
                raise
            value["error"] = type(exc).__name__+":"+str(exc)[:220]
            if paused and operation in {"install_verify", "rollback"}:
                try:
                    untouched = no_mutation_proof(plan_path, plan_sha)
                except Exception as probe_error:
                    untouched = None
                    value["recovery_status_error"] = type(probe_error).__name__+":"+str(probe_error)[:180]
                if untouched is not None:
                    value["no_mutation_proof"] = untouched
                elif operation == "rollback":
                    # This child already attempted forward recovery. Do not
                    # repeat an unconfirmed failed effect in this same pass.
                    value["rollback_error"] = value["error"]
                else:
                    try:
                        value["forward_recovery"] = child("recover", plan_path, plan_sha)
                    except Exception as rollback_error:
                        value["rollback_error"] = type(rollback_error).__name__+":"+str(rollback_error)[:180]
        journal.update({"stage":"CHILD_DONE","value":value})
        atomic(journal_path,journal)
    # Durable completed child receipt precedes the resume intent and API write.
    journal["stage"]="RESUME_INTENT";atomic(journal_path,journal)
    if value.get("rollback_error"):
        value["status"]="FAIL"
        value["crm_resume"]={"id":SUPERVISOR,"enabled":False,
            "status":"BLOCKED_UNCONFIRMED_FORWARD_RECOVERY_REQUIRES_RECONCILIATION"}
        value["safe_to_stop"]=True  # Explicit fail-closed state, never claimed resumed.
    else:
        # A transient resume failure leaves RESUME_INTENT and no terminal file.
        # The always-on restart retries only resume, never the completed child.
        value["crm_resume"]=api.set_enabled(True)
        value["safe_to_stop"]=True
    journal.update({"stage":"FINISHED","value":value});atomic(journal_path,journal)
    atomic(result_path,value)
    return value

def execute(operation, plan_path, plan_sha, result_path):
    # All phases for this exact immutable plan share one lifecycle owner.
    # Kernel unlock on process death lets a supervisor restart reconcile it.
    lock_path=Path(result_path).parent/"lifecycle.worker.lock"
    with lock_path.open("a+") as handle:
        fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
        return _execute(operation,plan_path,plan_sha,result_path)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--operation", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--result", type=Path, required=True)
    args=parser.parse_args()
    try:
        value=execute(args.operation,args.plan,args.plan_sha256,args.result)
    except Exception as exc:
        value={"status":"FAIL","operation":args.operation,"plan_sha256":args.plan_sha256,
               "error":type(exc).__name__+":"+str(exc)[:220]}
        if not args.result.with_suffix(".journal.json").exists():
            # No pause intent was ever issued; this startup error is terminal.
            value["safe_to_stop"]=True
            atomic(args.result,value)
    print(json.dumps(value,sort_keys=True))
    return 0 if value.get("status")=="PASS" else 1

if __name__=="__main__":
    raise SystemExit(main())
