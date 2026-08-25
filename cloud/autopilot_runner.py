#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UA ART Autopilot Runner
=======================

Cloud deliverable for TASK 001. Runs on PythonAnywhere from
`/home/Carix/autopilot`, synchronises through the GitHub repository
`art20021986-wq/ua-art-autopilot`, and reduces owner actions to visual
approvals and CRITICAL approvals only.

Design rules enforced by this file (see cloud/cloud_report_001.md):

  * Nothing is ever executed just because it exists in the repository.
    A patch is only touched when a manifest explicitly declares
    task_id / mode / allowed_files / expected_tests / rollback_source.
  * Tests are named entries of an internal registry. Free-form shell
    commands from a manifest are rejected, never executed.
  * READ_ONLY runs automatically and never writes to production.
  * SAFE_PATCH is applied only after CPU guard + whitelist + target SHA
    capture + backup + sandbox + tests all PASS and unexpected changes = 0.
  * CRITICAL never auto-applies. It stops at WAITING_OWNER_APPROVAL.
  * A failed SAFE_PATCH rolls back automatically and records the result.
  * Only the normalised report file is ever committed and pushed.
    Secrets, crm.db, tokens, customer data, media and backups stay out
    of the repository by construction (denylist + staged-file scan).

Standard library only. Python 3.7+.

Usage
-----
    python3 autopilot_runner.py --repo /home/Carix/autopilot/ua-art-autopilot
    python3 autopilot_runner.py --self-test
    python3 autopilot_runner.py --init-inventory
    python3 autopilot_runner.py --print-config
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone

RUNNER_NAME = "ua-art-autopilot-runner"
RUNNER_VERSION = "1.0.0"

# --------------------------------------------------------------------------
# Defaults. Every path can be overridden by the runner config file or CLI.
# --------------------------------------------------------------------------

DEFAULT_REPO_ROOT = "/home/Carix/autopilot/ua-art-autopilot"
DEFAULT_PRODUCTION_ROOT = "/home/Carix/ua_art"
DEFAULT_STATE_ROOT = "/home/Carix/.autopilot"
DEFAULT_BACKUP_ROOT = "/home/Carix/autopilot_backups"
CONFIG_BASENAME = "runner_config.json"

MODES = ("READ_ONLY", "SAFE_PATCH", "CRITICAL")
MODE_RANK = {"READ_ONLY": 0, "SAFE_PATCH": 1, "CRITICAL": 2}

REQUIRED_MANIFEST_KEYS = (
    "task_id",
    "mode",
    "allowed_files",
    "expected_tests",
    "rollback_source",
)
OPTIONAL_MANIFEST_KEYS = (
    "round",
    "description",
    "patch_dir",
    "sandbox_scope",
    "ua_0009",
    "owner_visual_check",
    "created_by",
    "created_at",
)

# CPU / load safeguards.
CPU_DEFER_THRESHOLD_PCT = 85.0
LOCAL_LOAD_DEFER_RATIO = 2.0
PA_API_TIMEOUT_SEC = 10

# Scan safeguards, so a mass SHA walk can never eat the CPU quota.
MAX_SCAN_FILES = 20000
MAX_SANDBOX_FILES = 4000
MAX_PATCH_FILE_BYTES = 2 * 1024 * 1024

# Files that must never be patched, backed up into git, or committed.
DENY_GLOBS = (
    "*.db", "*.db-journal", "*.db-wal", "*.db-shm",
    "*.sqlite", "*.sqlite3", "*.sql",
    ".env", "*.env", "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*",
    "*token*", "*secret*", "*credential*", "*password*",
    "*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp", "*.svg", "*.ico",
    "*.mp4", "*.mov", "*.avi", "*.mp3", "*.pdf",
    "*.zip", "*.tar", "*.gz", "*.tgz", "*.7z", "*.rar",
    "*.bak", "*.backup", "*.dump", "*.log",
)
DENY_DIR_PARTS = (
    ".git", ".ssh", "__pycache__", "node_modules", "venv", ".venv",
    "backups", "backup", "media", "uploads", "customers", "clients",
    "private", "secrets",
)

# Content that forces escalation out of SAFE_PATCH.
FORBIDDEN_CONTENT_PATTERNS = (
    (r"(?i)\bpragma\s+journal_mode", "sqlite journal_mode change"),
    (r"(?i)\bdrop\s+table\b", "destructive SQL: DROP TABLE"),
    (r"(?i)\bdelete\s+from\b", "destructive SQL: DELETE FROM"),
    (r"(?i)\btruncate\s+table\b", "destructive SQL: TRUNCATE"),
    (r"(?i)\balter\s+table\b", "schema change: ALTER TABLE"),
    (r"\bos\.system\s*\(", "shell execution: os.system"),
    (r"\bsubprocess\.(run|call|check_call|check_output|Popen)\s*\(", "shell execution: subprocess"),
    (r"\beval\s*\(", "dynamic execution: eval"),
    (r"\bexec\s*\(", "dynamic execution: exec"),
    (r"\bshutil\.rmtree\s*\(", "mass delete: shutil.rmtree"),
    (r"(?i)\brm\s+-rf\b", "mass delete: rm -rf"),
)

# Secret shapes refused in anything that would reach GitHub.
SECRET_PATTERNS = (
    (r"gh[pousr]_[A-Za-z0-9]{16,}", "github token"),
    (r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b", "telegram bot token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "aws access key id"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    (r"(?i)\b(api[_-]?key|apikey|access[_-]?token|auth[_-]?token|secret[_-]?key)\b\s*[:=]\s*\S{8,}", "api key assignment"),
    (r"(?i)\bpassword\b\s*[:=]\s*\S{4,}", "password assignment"),
    (r"(?i)authorization\s*:\s*bearer\s+\S+", "bearer header"),
    (r"(?i)pythonanywhere[^\n]{0,40}token\s*[:=]\s*\S+", "pythonanywhere token"),
)

TEXT_SUFFIXES = (
    ".py", ".html", ".htm", ".css", ".js", ".json", ".txt", ".md",
    ".xml", ".csv", ".yml", ".yaml", ".cfg", ".ini",
)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc)


def stamp():
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def compact_stamp():
    return utc_now().strftime("%Y%m%d-%H%M%S")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(131072)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def write_text(path, text):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def is_text_file(rel_path):
    return os.path.splitext(rel_path)[1].lower() in TEXT_SUFFIXES


def is_within(child, parent):
    """True when `child` resolves inside `parent` (no symlink escape)."""
    child_r = os.path.realpath(child)
    parent_r = os.path.realpath(parent)
    return child_r == parent_r or child_r.startswith(parent_r + os.sep)


def path_is_denied(rel_path):
    """Denylist check applied to every candidate path, whitelist or not."""
    norm = rel_path.replace("\\", "/")
    parts = [p for p in norm.split("/") if p]
    for part in parts[:-1] if len(parts) > 1 else []:
        if part.lower() in DENY_DIR_PARTS:
            return "denied directory component: %s" % part
    base = parts[-1] if parts else norm
    if base.lower() in DENY_DIR_PARTS:
        return "denied name: %s" % base
    for pattern in DENY_GLOBS:
        if fnmatch.fnmatch(base.lower(), pattern):
            return "denied pattern: %s" % pattern
    return None


def rel_path_is_safe(rel_path):
    """Reject absolute paths, traversal, empty and non-normalised entries."""
    if not isinstance(rel_path, str) or not rel_path.strip():
        return "empty path"
    if rel_path != rel_path.strip():
        return "padded path"
    if os.path.isabs(rel_path) or rel_path.startswith("/") or rel_path.startswith("\\"):
        return "absolute path not allowed"
    if re.match(r"^[A-Za-z]:", rel_path):
        return "drive-qualified path not allowed"
    norm = os.path.normpath(rel_path).replace("\\", "/")
    if norm.startswith("..") or "/../" in "/" + norm + "/":
        return "path traversal not allowed"
    if norm in (".", ""):
        return "path resolves to root"
    if "\x00" in rel_path:
        return "null byte in path"
    return None


def scan_patterns(text, patterns):
    hits = []
    for pattern, label in patterns:
        if re.search(pattern, text):
            hits.append(label)
    return hits


def iter_files(root, limit=MAX_SCAN_FILES):
    """Yield relative paths under root, skipping denied directories."""
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() not in DENY_DIR_PARTS]
        for name in filenames:
            abs_path = os.path.join(dirpath, name)
            rel = os.path.relpath(abs_path, root)
            count += 1
            if count > limit:
                raise RuntimeError("scan limit exceeded (%d files) under %s" % (limit, root))
            yield rel.replace("\\", "/")


def snapshot_tree(root, limit=MAX_SCAN_FILES):
    """rel_path -> sha256 for every readable file under root."""
    out = {}
    if not os.path.isdir(root):
        return out
    for rel in iter_files(root, limit=limit):
        abs_path = os.path.join(root, rel)
        if os.path.islink(abs_path) or not os.path.isfile(abs_path):
            continue
        try:
            out[rel] = sha256_file(abs_path)
        except OSError:
            out[rel] = "UNREADABLE"
    return out


def diff_snapshots(before, after):
    changed, added, removed = [], [], []
    for rel, sha in after.items():
        if rel not in before:
            added.append(rel)
        elif before[rel] != sha:
            changed.append(rel)
    for rel in before:
        if rel not in after:
            removed.append(rel)
    return sorted(changed), sorted(added), sorted(removed)


def run_cmd(argv, cwd=None, timeout=180, env=None):
    """Run a fixed argv (never a shell string)."""
    try:
        proc = subprocess.run(
            argv, cwd=cwd, timeout=timeout, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        return (
            proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"),
        )
    except subprocess.TimeoutExpired:
        return (124, "", "timeout after %ss: %s" % (timeout, " ".join(argv)))
    except OSError as exc:
        return (127, "", str(exc))


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

class Config(object):
    def __init__(self, data=None):
        data = data or {}
        self.repo_root = data.get("repo_root", DEFAULT_REPO_ROOT)
        self.production_root = data.get("production_root", DEFAULT_PRODUCTION_ROOT)
        self.state_root = data.get("state_root", DEFAULT_STATE_ROOT)
        self.backup_root = data.get("backup_root", DEFAULT_BACKUP_ROOT)
        # Relative to production_root. Empty on purpose: SAFE_PATCH stays
        # impossible until the owner declares the real writable areas.
        self.whitelist_roots = list(data.get("whitelist_roots", []))
        self.site_roots = list(data.get("site_roots", []))
        self.crm_db_path = data.get("crm_db_path", "")
        self.protected_globs = list(data.get("protected_globs", [
            "**/UA-0001*", "**/UA-0002*", "**/UA-0003*", "**/UA-0004*",
            "**/UA-0005*", "**/UA-0006*", "**/UA-0007*", "**/UA-0008*",
        ]))
        self.pa_username = data.get("pa_username", "")
        self.git_sync = bool(data.get("git_sync", True))
        self.git_push = bool(data.get("git_push", True))
        self.git_remote = data.get("git_remote", "origin")
        self.git_branch = data.get("git_branch", "main")
        self.max_rounds = int(data.get("max_rounds", 10))

    def as_dict(self):
        return {
            "repo_root": self.repo_root,
            "production_root": self.production_root,
            "state_root": self.state_root,
            "backup_root": self.backup_root,
            "whitelist_roots": self.whitelist_roots,
            "site_roots": self.site_roots,
            "crm_db_path": self.crm_db_path,
            "protected_globs": self.protected_globs,
            "pa_username": self.pa_username,
            "git_sync": self.git_sync,
            "git_push": self.git_push,
            "git_remote": self.git_remote,
            "git_branch": self.git_branch,
            "max_rounds": self.max_rounds,
        }

    @property
    def inventory_path(self):
        return os.path.join(self.state_root, "protected_inventory.json")

    @property
    def crm_baseline_path(self):
        return os.path.join(self.state_root, "crm_baseline.json")

    @property
    def approvals_dir(self):
        return os.path.join(self.state_root, "approvals")


def load_config(cli_args):
    state_root = cli_args.state_root or DEFAULT_STATE_ROOT
    config_path = cli_args.config or os.path.join(state_root, CONFIG_BASENAME)
    data = {}
    if os.path.isfile(config_path):
        try:
            data = json.loads(read_text(config_path))
        except ValueError as exc:
            raise SystemExit("invalid runner config %s: %s" % (config_path, exc))
    data["state_root"] = state_root
    if cli_args.repo:
        data["repo_root"] = cli_args.repo
    if cli_args.production_root:
        data["production_root"] = cli_args.production_root
    if cli_args.backup_root:
        data["backup_root"] = cli_args.backup_root
    if cli_args.no_push:
        data["git_push"] = False
    if cli_args.no_sync:
        data["git_sync"] = False
    cfg = Config(data)
    cfg.config_path = config_path
    return cfg


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

class Report(object):
    """Normalised report. The mandated block is always the tail of the file."""

    def __init__(self):
        self.task_id = "UNKNOWN"
        self.round = 0
        self.mode = "READ_ONLY"
        self.backup = "NOT_APPLICABLE"
        self.whitelist = "NOT_APPLICABLE"
        self.sandbox = "NOT_APPLICABLE"
        self.tests = "NOT_APPLICABLE"
        self.production_changed = "NO"
        self.files_changed = []
        self.unexpected_changes = []
        self.rollback = "NOT_NEEDED"
        self.crm_integrity = "NOT_APPLICABLE"
        self.site_integrity = "NOT_APPLICABLE"
        self.ua_baseline = "NOT_APPLICABLE"
        self.ua_0009_ready = "NOT_APPLICABLE"
        self.owner_visual_check_required = "NO"
        self.owner_approval_required = "NO"
        self.next_action = ""
        self.status = "CONTINUE"
        # Detail section (above the mandated block).
        self.cpu_guard = "UNKNOWN"
        self.cpu_detail = ""
        self.lines = []
        self.test_results = []
        self.started_at = stamp()

    def log(self, message):
        self.lines.append("[%s] %s" % (stamp(), message))

    def render(self):
        out = []
        out.append("UA ART AUTOPILOT REPORT")
        out.append("runner: %s %s" % (RUNNER_NAME, RUNNER_VERSION))
        out.append("started_at: %s" % self.started_at)
        out.append("finished_at: %s" % stamp())
        out.append("cpu_guard: %s" % self.cpu_guard)
        if self.cpu_detail:
            out.append("cpu_detail: %s" % self.cpu_detail)
        out.append("")
        out.append("--- EXECUTION LOG ---")
        out.extend(self.lines or ["(no entries)"])
        out.append("")
        out.append("--- TEST RESULTS ---")
        if self.test_results:
            for name, ok, msg in self.test_results:
                out.append("%-32s %-4s %s" % (name, "PASS" if ok else "FAIL", msg))
        else:
            out.append("(no tests executed)")
        out.append("")
        out.append("--- NORMALIZED REPORT ---")
        out.append("TASK_ID: %s" % self.task_id)
        out.append("ROUND: %s" % self.round)
        out.append("MODE: %s" % self.mode)
        out.append("BACKUP: %s" % self.backup)
        out.append("WHITELIST: %s" % self.whitelist)
        out.append("SANDBOX: %s" % self.sandbox)
        out.append("TESTS: %s" % self.tests)
        out.append("PRODUCTION_CHANGED: %s" % self.production_changed)
        out.append("FILES_CHANGED: %s" % (", ".join(self.files_changed) if self.files_changed else "NONE"))
        out.append("UNEXPECTED_CHANGES: %s" % (", ".join(self.unexpected_changes) if self.unexpected_changes else "0"))
        out.append("ROLLBACK: %s" % self.rollback)
        out.append("CRM_INTEGRITY: %s" % self.crm_integrity)
        out.append("SITE_INTEGRITY: %s" % self.site_integrity)
        out.append("UA_0001_0008_UNCHANGED: %s" % self.ua_baseline)
        out.append("UA_0009_READY: %s" % self.ua_0009_ready)
        out.append("OWNER_VISUAL_CHECK_REQUIRED: %s" % self.owner_visual_check_required)
        out.append("OWNER_APPROVAL_REQUIRED: %s" % self.owner_approval_required)
        out.append("NEXT_ACTION: %s" % self.next_action)
        out.append("STATUS: %s" % self.status)
        return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# CPU / load guard
# --------------------------------------------------------------------------

def read_pa_token(cfg):
    """Token is read from the environment or from state_root, never from the repo."""
    token = os.environ.get("PA_API_TOKEN", "").strip()
    if token:
        return token, os.environ.get("PA_USERNAME", cfg.pa_username)
    secret_path = os.path.join(cfg.state_root, "pa_api.json")
    if os.path.isfile(secret_path):
        try:
            data = json.loads(read_text(secret_path))
            return str(data.get("token", "")).strip(), str(data.get("username", cfg.pa_username))
        except (ValueError, OSError):
            return "", cfg.pa_username
    return "", cfg.pa_username


def cpu_quota_percent(cfg):
    """Return (percent, detail) from the PythonAnywhere API, or (None, reason)."""
    token, username = read_pa_token(cfg)
    if not token or not username:
        return None, "no PA API credentials outside repo (env PA_API_TOKEN / state pa_api.json)"
    import urllib.request
    import urllib.error
    url = "https://www.pythonanywhere.com/api/v0/user/%s/cpu/" % username
    req = urllib.request.Request(url, headers={"Authorization": "Token %s" % token})
    try:
        with urllib.request.urlopen(req, timeout=PA_API_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network/auth issues must never leak the token
        return None, "PA API unavailable (%s)" % type(exc).__name__
    used = float(payload.get("daily_cpu_used_seconds") or 0.0)
    limit = float(payload.get("daily_cpu_limit_seconds") or 0.0)
    if limit <= 0:
        return None, "PA API returned no CPU limit"
    pct = used / limit * 100.0
    return pct, "PA API: %.1f%% of daily CPU used (%.0f/%.0f s)" % (pct, used, limit)


def local_load_ratio():
    try:
        load1 = os.getloadavg()[0]
    except (OSError, AttributeError):
        return None, "load average unavailable"
    cpus = os.cpu_count() or 1
    ratio = load1 / float(cpus)
    return ratio, "local load %.2f over %d cpu(s) = %.2f per cpu" % (load1, cpus, ratio)


def cpu_guard(cfg, heavy):
    """
    Returns (allowed, state, detail).
    state in {OK, DEFERRED_CPU_LIMIT, UNKNOWN}.
    Heavy work is refused whenever the quota is >= 85% or unknown-and-loaded.
    """
    pct, detail = cpu_quota_percent(cfg)
    if pct is not None:
        if pct >= CPU_DEFER_THRESHOLD_PCT:
            return False, "DEFERRED_CPU_LIMIT", detail
        return True, "OK", detail
    ratio, load_detail = local_load_ratio()
    joined = "%s; %s" % (detail, load_detail)
    if ratio is not None and ratio >= LOCAL_LOAD_DEFER_RATIO:
        return False, "DEFERRED_CPU_LIMIT", joined
    if heavy and ratio is None:
        return False, "DEFERRED_CPU_LIMIT", joined + "; no safeguard signal, heavy work refused"
    return True, "OK" if ratio is not None else "UNKNOWN", joined


# --------------------------------------------------------------------------
# Task and manifest discovery
# --------------------------------------------------------------------------

TASK_RE = re.compile(r"^task_(\d+)\.md$")


def discover_latest_task(repo_root):
    tasks_dir = os.path.join(repo_root, "tasks")
    if not os.path.isdir(tasks_dir):
        return None
    best = None
    for name in os.listdir(tasks_dir):
        m = TASK_RE.match(name)
        if not m:
            continue
        number = int(m.group(1))
        if best is None or number > best[0]:
            best = (number, name)
    if best is None:
        return None
    number, name = best
    path = os.path.join(tasks_dir, name)
    text = read_text(path)
    mode = "READ_ONLY"
    m = re.search(r"^\s*MODE:\s*([A-Z_]+)\s*$", text, re.M)
    if m and m.group(1) in MODES:
        mode = m.group(1)
    max_rounds = 10
    m = re.search(r"^\s*MAX_ROUNDS:\s*(\d+)\s*$", text, re.M)
    if m:
        max_rounds = int(m.group(1))
    return {
        "number": number,
        "task_id": "task_%03d" % number,
        "path": path,
        "mode": mode,
        "max_rounds": max_rounds,
        "sha256": sha256_text(text),
    }


def discover_manifest_path(repo_root, task_id, explicit=None):
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    candidates = [
        os.path.join(repo_root, "cloud", "patches", task_id, "patch_manifest.json"),
        os.path.join(repo_root, "cloud", "patches", task_id, "manifest.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def list_cloud_outputs(repo_root):
    cloud_dir = os.path.join(repo_root, "cloud")
    out = []
    if not os.path.isdir(cloud_dir):
        return out
    try:
        for rel in sorted(iter_files(cloud_dir, limit=2000)):
            abs_path = os.path.join(cloud_dir, rel)
            try:
                out.append((rel, sha256_file(abs_path), os.path.getsize(abs_path)))
            except OSError:
                continue
    except RuntimeError as exc:
        out.append(("(scan aborted)", str(exc), 0))
    return out


def validate_manifest(raw, task, cfg, manifest_path):
    """
    Strict schema validation. Returns (manifest_dict, errors).
    A manifest that fails validation is never acted upon.
    """
    errors = []
    if not isinstance(raw, dict):
        return None, ["manifest is not a JSON object"]

    for key in REQUIRED_MANIFEST_KEYS:
        if key not in raw:
            errors.append("missing required key: %s" % key)
    unknown = [k for k in raw if k not in REQUIRED_MANIFEST_KEYS + OPTIONAL_MANIFEST_KEYS]
    if unknown:
        errors.append("unknown keys not allowed: %s" % ", ".join(sorted(unknown)))
    if errors:
        return None, errors

    task_id = raw.get("task_id")
    if not isinstance(task_id, str) or not re.match(r"^task_\d{3}$", task_id):
        errors.append("task_id must look like task_001")
    elif task and task_id != task["task_id"]:
        errors.append("task_id %s does not match latest task %s" % (task_id, task["task_id"]))

    mode = raw.get("mode")
    if mode not in MODES:
        errors.append("mode must be one of %s" % ", ".join(MODES))

    allowed = raw.get("allowed_files")
    if not isinstance(allowed, list) or not allowed:
        errors.append("allowed_files must be a non-empty list")
    else:
        if len(allowed) != len(set(allowed)):
            errors.append("allowed_files contains duplicates")
        for entry in allowed:
            reason = rel_path_is_safe(entry)
            if reason:
                errors.append("allowed_files entry %r rejected: %s" % (entry, reason))
                continue
            denied = path_is_denied(entry)
            if denied:
                errors.append("allowed_files entry %r rejected: %s" % (entry, denied))

    tests = raw.get("expected_tests")
    if not isinstance(tests, list) or not tests:
        errors.append("expected_tests must be a non-empty list of registry names")
    else:
        for name in tests:
            if not isinstance(name, str):
                errors.append("expected_tests entry must be a string, got %r" % (name,))
            elif name not in TEST_REGISTRY:
                errors.append("unknown test %r - free-form commands are never executed" % (name,))

    rollback = raw.get("rollback_source")
    if not isinstance(rollback, str) or not rollback:
        errors.append("rollback_source must be a string")
    elif rollback != "auto_backup" and not rollback.startswith("backup:"):
        errors.append("rollback_source must be 'auto_backup' or 'backup:<absolute path>'")
    elif rollback.startswith("backup:"):
        target = rollback.split(":", 1)[1]
        if not os.path.isabs(target):
            errors.append("rollback_source backup path must be absolute")
        elif is_within(target, cfg.repo_root):
            errors.append("rollback_source must not point inside the git repository")

    scope = raw.get("sandbox_scope", "targets")
    if scope not in ("targets", "whitelist"):
        errors.append("sandbox_scope must be 'targets' or 'whitelist'")

    patch_dir = raw.get("patch_dir")
    if patch_dir is not None:
        reason = rel_path_is_safe(patch_dir)
        if reason:
            errors.append("patch_dir rejected: %s" % reason)

    if errors:
        return None, errors

    manifest = dict(raw)
    manifest["sandbox_scope"] = scope
    manifest["_path"] = manifest_path
    manifest["_sha256"] = sha256_file(manifest_path)
    if not manifest.get("patch_dir"):
        manifest["patch_dir"] = os.path.relpath(
            os.path.dirname(manifest_path), cfg.repo_root
        ).replace("\\", "/")
    return manifest, []


# --------------------------------------------------------------------------
# Test registry. Only these named tests can ever run.
# --------------------------------------------------------------------------

class TestContext(object):
    def __init__(self, cfg, manifest, sandbox_root, allowed_rel, changed_rel, state):
        self.cfg = cfg
        self.manifest = manifest
        self.sandbox_root = sandbox_root
        self.allowed_rel = allowed_rel
        self.changed_rel = changed_rel
        self.state = state


def t_sandbox_diff_matches_manifest(ctx):
    unexpected = sorted(set(ctx.changed_rel) - set(ctx.allowed_rel))
    if unexpected:
        return False, "sandbox touched files outside allowed_files: %s" % ", ".join(unexpected)
    missing = sorted(set(ctx.allowed_rel) - set(ctx.changed_rel))
    if missing:
        return False, "declared files were not produced by the patch: %s" % ", ".join(missing)
    return True, "%d file(s) changed, all declared" % len(ctx.changed_rel)


def t_no_forbidden_patterns(ctx):
    hits = []
    for rel in ctx.changed_rel:
        abs_path = os.path.join(ctx.sandbox_root, rel)
        if not os.path.isfile(abs_path) or not is_text_file(rel):
            continue
        for label in scan_patterns(read_text(abs_path), FORBIDDEN_CONTENT_PATTERNS):
            hits.append("%s: %s" % (rel, label))
    if hits:
        return False, "forbidden content requires CRITICAL review: %s" % "; ".join(hits)
    return True, "no forbidden content in %d file(s)" % len(ctx.changed_rel)


def t_no_secrets_in_patch(ctx):
    hits = []
    for rel in ctx.changed_rel:
        abs_path = os.path.join(ctx.sandbox_root, rel)
        if not os.path.isfile(abs_path) or not is_text_file(rel):
            continue
        for label in scan_patterns(read_text(abs_path), SECRET_PATTERNS):
            hits.append("%s: %s" % (rel, label))
    if hits:
        return False, "secret-shaped content found: %s" % "; ".join(hits)
    return True, "no secret-shaped content"


def t_python_compiles(ctx):
    targets = [os.path.join(ctx.sandbox_root, r) for r in ctx.changed_rel if r.endswith(".py")]
    if not targets:
        return True, "no python files in patch"
    rc, out, err = run_cmd([sys.executable, "-m", "py_compile"] + targets, timeout=120)
    if rc != 0:
        return False, "py_compile failed: %s" % (err.strip() or out.strip())[:400]
    return True, "%d python file(s) compile" % len(targets)


def t_json_valid(ctx):
    checked = 0
    for rel in ctx.changed_rel:
        if not rel.endswith(".json"):
            continue
        abs_path = os.path.join(ctx.sandbox_root, rel)
        try:
            json.loads(read_text(abs_path))
        except ValueError as exc:
            return False, "%s is not valid JSON: %s" % (rel, exc)
        checked += 1
    return True, "%d json file(s) valid" % checked


def t_html_wellformed(ctx):
    from html.parser import HTMLParser

    void = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    class Checker(HTMLParser):
        def __init__(self):
            HTMLParser.__init__(self, convert_charrefs=True)
            self.stack = []
            self.problems = []

        def handle_starttag(self, tag, attrs):
            if tag not in void:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if tag in void:
                return
            if not self.stack:
                self.problems.append("stray </%s>" % tag)
            elif self.stack[-1] == tag:
                self.stack.pop()
            elif tag in self.stack:
                while self.stack:
                    popped = self.stack.pop()
                    if popped == tag:
                        break
                    self.problems.append("unclosed <%s> before </%s>" % (popped, tag))
            else:
                self.problems.append("unmatched </%s>" % tag)

    checked = 0
    for rel in ctx.changed_rel:
        if not rel.lower().endswith((".html", ".htm")):
            continue
        parser = Checker()
        parser.feed(read_text(os.path.join(ctx.sandbox_root, rel)))
        parser.close()
        if parser.problems:
            return False, "%s: %s" % (rel, "; ".join(parser.problems[:5]))
        if parser.stack:
            return False, "%s: unclosed tags %s" % (rel, ", ".join(parser.stack[:5]))
        checked += 1
    return True, "%d html file(s) well formed" % checked


def t_ua_baseline_unchanged(ctx):
    ok, detail = verify_protected_inventory(ctx.cfg)
    return ok, detail


def t_crm_db_untouched(ctx):
    for rel in ctx.allowed_rel:
        low = rel.lower()
        if low.endswith((".db", ".sqlite", ".sqlite3")) or "crm.db" in low:
            return False, "patch declares a database file: %s" % rel
    ok, detail = verify_crm_integrity(ctx.cfg, read_only=True)
    if ok is None:
        return True, detail
    return ok, detail


def t_no_production_publication(ctx):
    """Refuse anything that looks like a publish step inside a SAFE_PATCH."""
    hits = []
    for rel in ctx.changed_rel:
        abs_path = os.path.join(ctx.sandbox_root, rel)
        if not os.path.isfile(abs_path) or not is_text_file(rel):
            continue
        text = read_text(abs_path)
        for pattern, label in (
            (r"(?i)\bpublish\s*\(", "publish() call"),
            (r"(?i)\bdeploy\s*\(", "deploy() call"),
            (r"(?i)regenerate_all|rebuild_all|mass_regenerate", "mass regeneration"),
        ):
            if re.search(pattern, text):
                hits.append("%s: %s" % (rel, label))
    if hits:
        return False, "publication/regeneration must be CRITICAL: %s" % "; ".join(hits)
    return True, "no publication or mass regeneration in patch"


def t_file_size_guard(ctx):
    for rel in ctx.changed_rel:
        abs_path = os.path.join(ctx.sandbox_root, rel)
        try:
            size = os.path.getsize(abs_path)
        except OSError:
            continue
        if size > MAX_PATCH_FILE_BYTES:
            return False, "%s exceeds %d bytes" % (rel, MAX_PATCH_FILE_BYTES)
    return True, "all patched files within size limit"


TEST_REGISTRY = {
    "sandbox_diff_matches_manifest": t_sandbox_diff_matches_manifest,
    "no_forbidden_patterns": t_no_forbidden_patterns,
    "no_secrets_in_patch": t_no_secrets_in_patch,
    "python_compiles": t_python_compiles,
    "json_valid": t_json_valid,
    "html_wellformed": t_html_wellformed,
    "ua_baseline_unchanged": t_ua_baseline_unchanged,
    "crm_db_untouched": t_crm_db_untouched,
    "no_production_publication": t_no_production_publication,
    "file_size_guard": t_file_size_guard,
}

# Always executed for SAFE_PATCH/CRITICAL, whatever the manifest asks for.
MANDATORY_TESTS = (
    "sandbox_diff_matches_manifest",
    "no_forbidden_patterns",
    "no_secrets_in_patch",
    "file_size_guard",
    "ua_baseline_unchanged",
    "crm_db_untouched",
    "no_production_publication",
)


# --------------------------------------------------------------------------
# Protected baseline UA-0001..UA-0008 and CRM integrity
# --------------------------------------------------------------------------

def collect_protected_files(cfg):
    root = cfg.production_root
    found = {}
    if not os.path.isdir(root):
        return found
    for rel in iter_files(root, limit=MAX_SCAN_FILES):
        base = os.path.basename(rel)
        for pattern in cfg.protected_globs:
            simple = pattern.replace("**/", "")
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(base, simple):
                abs_path = os.path.join(root, rel)
                try:
                    found[rel] = sha256_file(abs_path)
                except OSError:
                    found[rel] = "UNREADABLE"
                break
    return found


def init_protected_inventory(cfg):
    files = collect_protected_files(cfg)
    payload = {
        "created_at": stamp(),
        "production_root": cfg.production_root,
        "protected_globs": cfg.protected_globs,
        "count": len(files),
        "files": files,
    }
    write_text(cfg.inventory_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def verify_protected_inventory(cfg):
    """(True/False, detail). Baseline lives outside the repo."""
    if not os.path.isdir(cfg.production_root):
        return True, "production root absent, UA-0001..UA-0008 check not applicable"
    if not os.path.isfile(cfg.inventory_path):
        return False, "protected inventory missing, run --init-inventory first"
    try:
        payload = json.loads(read_text(cfg.inventory_path))
    except ValueError as exc:
        return False, "protected inventory unreadable: %s" % exc
    baseline = payload.get("files", {})
    current = collect_protected_files(cfg)
    changed, added, removed = diff_snapshots(baseline, current)
    if changed or removed:
        parts = []
        if changed:
            parts.append("changed: %s" % ", ".join(changed[:10]))
        if removed:
            parts.append("missing: %s" % ", ".join(removed[:10]))
        return False, "UA-0001..UA-0008 baseline violated (%s)" % "; ".join(parts)
    note = "%d protected file(s) unchanged" % len(baseline)
    if added:
        note += "; %d new protected-pattern file(s) seen: %s" % (len(added), ", ".join(added[:5]))
    return True, note


def verify_crm_integrity(cfg, read_only=True):
    """
    (True/False/None, detail). None means not applicable.
    Opens the database strictly read-only and never writes or changes pragmas.
    """
    db_path = cfg.crm_db_path
    if not db_path:
        return None, "crm_db_path not configured, CRM check not applicable"
    if not os.path.isfile(db_path):
        return None, "crm database not present at configured path"
    uri = "file:%s?mode=ro" % db_path.replace("?", "%3f").replace("#", "%23")
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error as exc:
        return False, "cannot open crm database read-only: %s" % exc
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA quick_check")
        row = cur.fetchone()
        check = row[0] if row else "unknown"
        cur.execute("PRAGMA journal_mode")
        row = cur.fetchone()
        journal = row[0] if row else "unknown"
    except sqlite3.Error as exc:
        conn.close()
        return False, "crm read-only check failed: %s" % exc
    conn.close()

    detail = "quick_check=%s journal_mode=%s" % (check, journal)
    if str(check).lower() != "ok":
        return False, "crm integrity: %s" % detail

    baseline_path = cfg.crm_baseline_path
    if os.path.isfile(baseline_path):
        try:
            baseline = json.loads(read_text(baseline_path))
        except ValueError:
            baseline = {}
        prev = baseline.get("journal_mode")
        if prev and str(prev).lower() != str(journal).lower():
            return False, "journal_mode changed from %s to %s (CRITICAL)" % (prev, journal)
    else:
        write_text(baseline_path, json.dumps(
            {"created_at": stamp(), "db_path": db_path, "journal_mode": journal},
            indent=2) + "\n")
        detail += " (baseline recorded)"
    return True, "crm %s" % detail


# --------------------------------------------------------------------------
# Whitelist, backup, sandbox, apply, rollback
# --------------------------------------------------------------------------

def verify_whitelist(cfg, allowed_rel):
    """Every declared file must sit inside a configured whitelist root."""
    problems = []
    if not cfg.whitelist_roots:
        return False, ["whitelist_roots is empty in runner config - patch modes are disabled until the owner declares writable areas"]
    roots_abs = []
    for root in cfg.whitelist_roots:
        reason = rel_path_is_safe(root)
        if reason:
            problems.append("whitelist root %r rejected: %s" % (root, reason))
            continue
        abs_root = os.path.join(cfg.production_root, root)
        if not os.path.isdir(abs_root):
            problems.append("whitelist root missing on disk: %s" % root)
            continue
        roots_abs.append(abs_root)
    if problems:
        return False, problems
    for rel in allowed_rel:
        abs_path = os.path.join(cfg.production_root, rel)
        if not any(is_within(os.path.dirname(abs_path) or abs_path, root) for root in roots_abs):
            problems.append("%s is outside every whitelist root" % rel)
    return (not problems), problems


def capture_targets(cfg, allowed_rel):
    """Verify each target exists and capture its SHA256 before any change."""
    shas, missing = {}, []
    for rel in allowed_rel:
        abs_path = os.path.join(cfg.production_root, rel)
        if os.path.islink(abs_path):
            missing.append("%s (symlink not allowed)" % rel)
            continue
        if not os.path.isfile(abs_path):
            missing.append("%s (target file does not exist)" % rel)
            continue
        shas[rel] = sha256_file(abs_path)
    return shas, missing


def create_backup(cfg, task_id, round_no, allowed_rel, target_shas):
    """Copy targets outside the repository and write a backup manifest."""
    if is_within(cfg.backup_root, cfg.repo_root):
        raise RuntimeError("backup_root must not live inside the git repository")
    backup_dir = os.path.join(cfg.backup_root, task_id, "round%02d-%s" % (round_no, compact_stamp()))
    files_dir = os.path.join(backup_dir, "files")
    os.makedirs(files_dir, exist_ok=True)
    entries = []
    for rel in allowed_rel:
        src = os.path.join(cfg.production_root, rel)
        dst = os.path.join(files_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        entries.append({
            "path": rel,
            "sha256_before": target_shas[rel],
            "backup_sha256": sha256_file(dst),
            "bytes": os.path.getsize(dst),
        })
    manifest = {
        "task_id": task_id,
        "round": round_no,
        "created_at": stamp(),
        "production_root": cfg.production_root,
        "backup_dir": backup_dir,
        "files": entries,
    }
    manifest_path = os.path.join(backup_dir, "backup_manifest.json")
    write_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    for entry in entries:
        if entry["sha256_before"] != entry["backup_sha256"]:
            raise RuntimeError("backup verification failed for %s" % entry["path"])
    return manifest


def resolve_patch_sources(cfg, manifest):
    """
    Map allowed_files -> patch payload file inside the repository.
    Payload files are copied, never executed.
    """
    patch_root = os.path.join(cfg.repo_root, manifest["patch_dir"], "files")
    sources, problems = {}, []
    if not os.path.isdir(patch_root):
        return {}, ["patch payload directory missing: %s/files" % manifest["patch_dir"]]
    for rel in manifest["allowed_files"]:
        src = os.path.join(patch_root, rel)
        if not is_within(os.path.dirname(src) or src, patch_root):
            problems.append("payload path escapes patch dir: %s" % rel)
            continue
        if os.path.islink(src):
            problems.append("payload symlink not allowed: %s" % rel)
            continue
        if not os.path.isfile(src):
            problems.append("payload file missing for %s" % rel)
            continue
        if os.path.getsize(src) > MAX_PATCH_FILE_BYTES:
            problems.append("payload too large: %s" % rel)
            continue
        sources[rel] = src
    return sources, problems


def build_sandbox(cfg, manifest, allowed_rel):
    """Copy the production slice into a temporary sandbox."""
    sandbox_root = tempfile.mkdtemp(prefix="ua-art-sandbox-")
    copied = 0
    if manifest["sandbox_scope"] == "whitelist":
        for root in cfg.whitelist_roots:
            src_root = os.path.join(cfg.production_root, root)
            if not os.path.isdir(src_root):
                continue
            for rel in iter_files(src_root, limit=MAX_SANDBOX_FILES):
                src = os.path.join(src_root, rel)
                dst = os.path.join(sandbox_root, root, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
                if copied > MAX_SANDBOX_FILES:
                    raise RuntimeError("sandbox copy limit exceeded")
    else:
        for rel in allowed_rel:
            src = os.path.join(cfg.production_root, rel)
            dst = os.path.join(sandbox_root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
    return sandbox_root, copied


def apply_payload(dest_root, sources):
    """Copy payload files into a tree (sandbox or production)."""
    written = []
    for rel, src in sources.items():
        dst = os.path.join(dest_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(rel)
    return sorted(written)


def rollback_from_backup(cfg, backup_manifest):
    """Restore every backed-up file and verify the pre-change SHA256."""
    files_dir = os.path.join(backup_manifest["backup_dir"], "files")
    failures = []
    for entry in backup_manifest["files"]:
        rel = entry["path"]
        src = os.path.join(files_dir, rel)
        dst = os.path.join(cfg.production_root, rel)
        try:
            shutil.copyfile(src, dst)
        except OSError as exc:
            failures.append("%s: %s" % (rel, exc))
            continue
        if sha256_file(dst) != entry["sha256_before"]:
            failures.append("%s: restored content does not match pre-change SHA256" % rel)
    return (not failures), failures


# --------------------------------------------------------------------------
# Git
# --------------------------------------------------------------------------

def git(cfg, args, timeout=120):
    return run_cmd(["git"] + args, cwd=cfg.repo_root, timeout=timeout)


def git_sync(cfg, report):
    rc, out, err = git(cfg, ["rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        report.log("git: %s is not a git work tree" % cfg.repo_root)
        return False
    rc, out, err = git(cfg, ["fetch", cfg.git_remote, cfg.git_branch])
    if rc != 0:
        report.log("git fetch failed: %s" % err.strip()[:200])
        return False
    rc, out, err = git(cfg, ["merge", "--ff-only", "%s/%s" % (cfg.git_remote, cfg.git_branch)])
    if rc != 0:
        report.log("git fast-forward failed (local changes?): %s" % err.strip()[:200])
        return False
    report.log("git: synchronised with %s/%s" % (cfg.git_remote, cfg.git_branch))
    return True


def git_commit_and_push_report(cfg, report, report_rel):
    """Stage exactly one file, scan it, then commit and push with backoff."""
    abs_report = os.path.join(cfg.repo_root, report_rel)
    hits = scan_patterns(read_text(abs_report), SECRET_PATTERNS)
    if hits:
        report.log("PUSH REFUSED: report contains secret-shaped content (%s)" % ", ".join(hits))
        return False

    rc, out, err = git(cfg, ["add", "--", report_rel])
    if rc != 0:
        report.log("git add failed: %s" % err.strip()[:200])
        return False

    rc, out, err = git(cfg, ["diff", "--cached", "--name-only"])
    staged = [line.strip() for line in out.splitlines() if line.strip()]
    unexpected = [f for f in staged if f != report_rel]
    if unexpected:
        git(cfg, ["reset"])
        report.log("PUSH REFUSED: unexpected staged files %s" % ", ".join(unexpected))
        return False
    for name in staged:
        denied = path_is_denied(name)
        if denied:
            git(cfg, ["reset"])
            report.log("PUSH REFUSED: %s (%s)" % (name, denied))
            return False
    if not staged:
        report.log("git: report unchanged, nothing to commit")
        return True

    message = "autopilot: %s round %s report" % (report.task_id, report.round)
    rc, out, err = git(cfg, ["commit", "-m", message])
    if rc != 0:
        report.log("git commit failed: %s" % (err.strip() or out.strip())[:200])
        return False

    if not cfg.git_push:
        report.log("git: push disabled by configuration")
        return True

    delay = 2
    for attempt in range(1, 6):
        rc, out, err = git(cfg, ["push", "-u", cfg.git_remote, "HEAD:%s" % cfg.git_branch], timeout=180)
        if rc == 0:
            report.log("git: report pushed to %s/%s" % (cfg.git_remote, cfg.git_branch))
            return True
        report.log("git push attempt %d failed: %s" % (attempt, err.strip()[:200]))
        if attempt == 5:
            break
        time.sleep(delay)
        delay *= 2
    return False


# --------------------------------------------------------------------------
# Round bookkeeping
# --------------------------------------------------------------------------

def report_rel_path(task_id):
    return "python/report_%s.txt" % task_id.split("_")[-1]


def determine_round(cfg, task_id, explicit):
    if explicit:
        return int(explicit)
    state_path = os.path.join(cfg.state_root, "rounds.json")
    data = {}
    if os.path.isfile(state_path):
        try:
            data = json.loads(read_text(state_path))
        except ValueError:
            data = {}
    return int(data.get(task_id, 0)) + 1


def record_round(cfg, task_id, round_no):
    state_path = os.path.join(cfg.state_root, "rounds.json")
    data = {}
    if os.path.isfile(state_path):
        try:
            data = json.loads(read_text(state_path))
        except ValueError:
            data = {}
    data[task_id] = round_no
    write_text(state_path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def owner_approval_present(cfg, task_id, manifest_sha):
    """
    CRITICAL work stays blocked unless the owner placed an approval file
    outside the repository AND the operator passed --owner-approved.
    The approval is bound to the exact manifest SHA256.
    """
    path = os.path.join(cfg.approvals_dir, "%s.approval" % task_id)
    if not os.path.isfile(path):
        return False, "no owner approval file"
    text = read_text(path).strip()
    if not text.upper().startswith("APPROVE"):
        return False, "approval file does not start with APPROVE"
    if manifest_sha not in text:
        return False, "approval is not bound to the current manifest SHA256"
    return True, "owner approval verified for manifest %s" % manifest_sha[:12]


# --------------------------------------------------------------------------
# Main execution
# --------------------------------------------------------------------------

def execute(cfg, args):
    report = Report()
    report.log("runner %s %s starting" % (RUNNER_NAME, RUNNER_VERSION))
    report.log("repo=%s production=%s" % (cfg.repo_root, cfg.production_root))
    if args.dry_run:
        report.log("DRY RUN: production writes are disabled for this run")

    if not os.path.isdir(cfg.repo_root):
        report.status = "STOPPED"
        report.next_action = "Repository clone missing at %s" % cfg.repo_root
        return report, None

    # 1. Synchronise with GitHub before reading anything.
    if cfg.git_sync:
        git_sync(cfg, report)
    else:
        report.log("git: sync disabled by configuration")

    # 2. Read the latest task.
    task = discover_latest_task(cfg.repo_root)
    if not task:
        report.status = "STOPPED"
        report.next_action = "No tasks/task_NNN.md found in the repository"
        return report, None
    report.task_id = task["task_id"]
    report.log("task %s (declared MODE=%s, MAX_ROUNDS=%d, sha=%s)"
               % (task["task_id"], task["mode"], task["max_rounds"], task["sha256"][:12]))

    round_no = determine_round(cfg, task["task_id"], args.round)
    report.round = round_no
    max_rounds = min(task["max_rounds"], cfg.max_rounds)
    if round_no > max_rounds:
        report.status = "STOPPED"
        report.next_action = "Round limit %d reached for %s" % (max_rounds, task["task_id"])
        report.log("stopping: round %d exceeds limit %d" % (round_no, max_rounds))
        return report, task

    # 3. Read Cloud output.
    outputs = list_cloud_outputs(cfg.repo_root)
    report.log("cloud/ contains %d file(s)" % len(outputs))
    for rel, sha, size in outputs[:50]:
        report.log("  cloud/%s sha=%s bytes=%s" % (rel, str(sha)[:12], size))

    manifest_path = discover_manifest_path(cfg.repo_root, task["task_id"], args.manifest)
    manifest, errors = None, []
    if manifest_path:
        report.log("manifest found: %s" % os.path.relpath(manifest_path, cfg.repo_root))
        try:
            raw = json.loads(read_text(manifest_path))
        except ValueError as exc:
            errors = ["manifest is not valid JSON: %s" % exc]
        else:
            manifest, errors = validate_manifest(raw, task, cfg, manifest_path)
    else:
        report.log("no patch manifest for %s - nothing may be executed" % task["task_id"])

    for err in errors:
        report.log("MANIFEST REJECTED: %s" % err)

    # 4. Effective mode is always the strictest of task mode and manifest mode.
    if manifest:
        effective = manifest["mode"] if MODE_RANK[manifest["mode"]] >= MODE_RANK[task["mode"]] else task["mode"]
        if effective != manifest["mode"]:
            report.log("mode escalated from manifest %s to task %s" % (manifest["mode"], effective))
    else:
        effective = "READ_ONLY"
        if errors:
            report.log("manifest invalid - falling back to READ_ONLY")
    report.mode = effective

    heavy = effective != "READ_ONLY"
    allowed, cpu_state, cpu_detail = cpu_guard(cfg, heavy)
    report.cpu_guard = cpu_state
    report.cpu_detail = cpu_detail
    report.log("cpu guard: %s (%s)" % (cpu_state, cpu_detail))
    if not allowed:
        report.status = "STOPPED"
        report.next_action = "DEFERRED_CPU_LIMIT - retry when CPU usage falls below %.0f%%" % CPU_DEFER_THRESHOLD_PCT
        report.mode = effective
        return report, task

    # 5. Read-only observations, always performed.
    baseline_ok, baseline_detail = None, ""
    if os.path.isdir(cfg.production_root):
        if not os.path.isfile(cfg.inventory_path):
            payload = init_protected_inventory(cfg)
            report.log("protected inventory initialised with %d file(s)" % payload["count"])
            report.ua_baseline = "NOT_APPLICABLE"
        else:
            baseline_ok, baseline_detail = verify_protected_inventory(cfg)
            report.ua_baseline = "PASS" if baseline_ok else "FAIL"
            report.log("UA-0001..UA-0008: %s" % baseline_detail)
    else:
        report.log("production root %s not present - production checks not applicable" % cfg.production_root)

    crm_ok, crm_detail = verify_crm_integrity(cfg, read_only=True)
    report.crm_integrity = "NOT_APPLICABLE" if crm_ok is None else ("PASS" if crm_ok else "FAIL")
    report.log("crm: %s" % crm_detail)

    if errors:
        report.status = "STOPPED"
        report.next_action = "Fix the patch manifest in cloud/ - %d validation error(s), nothing was executed" % len(errors)
        return report, task

    if effective == "READ_ONLY":
        report.whitelist = "NOT_APPLICABLE"
        report.sandbox = "NOT_APPLICABLE"
        report.tests = "NOT_APPLICABLE"
        report.backup = "NOT_APPLICABLE"
        report.production_changed = "NO"
        report.status = "CONTINUE"
        report.next_action = ("READ_ONLY round complete. Provide cloud/patches/%s/patch_manifest.json "
                              "plus payload files to move forward." % task["task_id"])
        if report.ua_baseline == "FAIL" or report.crm_integrity == "FAIL":
            report.status = "WAITING_OWNER_APPROVAL"
            report.owner_approval_required = "YES"
            report.next_action = "Integrity check failed during READ_ONLY - owner review required before any patch"
        return report, task

    # ---- From here on: SAFE_PATCH or CRITICAL preparation ----
    allowed_rel = list(manifest["allowed_files"])
    report.log("manifest sha=%s mode=%s files=%d tests=%s"
               % (manifest["_sha256"][:12], manifest["mode"], len(allowed_rel),
                  ",".join(manifest["expected_tests"])))

    # 5a. Whitelist.
    wl_ok, wl_problems = verify_whitelist(cfg, allowed_rel)
    report.whitelist = "PASS" if wl_ok else "FAIL"
    for problem in wl_problems:
        report.log("whitelist: %s" % problem)
    if not wl_ok:
        report.status = "STOPPED"
        report.next_action = "Whitelist verification failed - no backup, no sandbox, no production write"
        return report, task
    report.log("whitelist: %d file(s) inside %s" % (len(allowed_rel), ", ".join(cfg.whitelist_roots)))

    # 5b. Targets exist, capture SHA256.
    target_shas, missing = capture_targets(cfg, allowed_rel)
    if missing:
        for item in missing:
            report.log("target: %s" % item)
        report.whitelist = "FAIL"
        report.status = "STOPPED"
        report.next_action = "Target verification failed - declared files must exist in production before patching"
        return report, task
    for rel in allowed_rel:
        report.log("target %s sha256_before=%s" % (rel, target_shas[rel]))

    # 5c. Patch payload.
    sources, payload_problems = resolve_patch_sources(cfg, manifest)
    for problem in payload_problems:
        report.log("payload: %s" % problem)
    if payload_problems:
        report.status = "STOPPED"
        report.next_action = "Patch payload incomplete in cloud/ - nothing executed"
        return report, task

    # 5d. Backup manifest.
    try:
        backup_manifest = create_backup(cfg, task["task_id"], round_no, allowed_rel, target_shas)
        report.backup = "PASS"
        report.log("backup: %d file(s) in %s" % (len(allowed_rel), backup_manifest["backup_dir"]))
    except (OSError, RuntimeError) as exc:
        report.backup = "FAIL"
        report.status = "STOPPED"
        report.next_action = "Backup failed (%s) - production untouched" % exc
        report.log("backup failed: %s" % exc)
        return report, task

    if manifest["rollback_source"].startswith("backup:"):
        declared = manifest["rollback_source"].split(":", 1)[1]
        if not os.path.isdir(declared):
            report.backup = "FAIL"
            report.status = "STOPPED"
            report.next_action = "Declared rollback_source directory does not exist - production untouched"
            return report, task
    report.log("rollback source verified: %s" % manifest["rollback_source"])

    # 5e. Sandbox + tests.
    sandbox_root = None
    try:
        sandbox_root, copied = build_sandbox(cfg, manifest, allowed_rel)
        report.log("sandbox: %d file(s) copied to %s" % (copied, sandbox_root))
        before = snapshot_tree(sandbox_root, limit=MAX_SANDBOX_FILES)
        apply_payload(sandbox_root, sources)
        after = snapshot_tree(sandbox_root, limit=MAX_SANDBOX_FILES)
        changed, added, removed = diff_snapshots(before, after)
        sandbox_changed = sorted(set(changed) | set(added))
        report.log("sandbox diff: changed=%d added=%d removed=%d"
                   % (len(changed), len(added), len(removed)))
        report.sandbox = "PASS"

        ctx = TestContext(cfg, manifest, sandbox_root, allowed_rel, sandbox_changed, {})
        names = list(MANDATORY_TESTS) + [t for t in manifest["expected_tests"] if t not in MANDATORY_TESTS]
        all_pass = True
        for name in names:
            func = TEST_REGISTRY.get(name)
            if func is None:
                report.test_results.append((name, False, "unknown test, refused"))
                all_pass = False
                continue
            try:
                ok, message = func(ctx)
            except Exception as exc:
                ok, message = False, "test raised %s: %s" % (type(exc).__name__, exc)
            report.test_results.append((name, bool(ok), message))
            if not ok:
                all_pass = False
        report.tests = "PASS" if all_pass else "FAIL"
        report.log("tests: %s (%d executed)" % (report.tests, len(report.test_results)))
    except Exception as exc:
        report.sandbox = "FAIL"
        report.tests = "FAIL"
        all_pass = False
        report.log("sandbox failed: %s" % exc)
    finally:
        if sandbox_root and os.path.isdir(sandbox_root) and not args.keep_sandbox:
            shutil.rmtree(sandbox_root, ignore_errors=True)

    gates_ok = (report.backup == "PASS" and report.whitelist == "PASS"
                and report.sandbox == "PASS" and report.tests == "PASS"
                and report.ua_baseline in ("PASS", "NOT_APPLICABLE")
                and report.crm_integrity in ("PASS", "NOT_APPLICABLE"))

    if manifest.get("ua_0009"):
        report.ua_0009_ready = "YES" if gates_ok else "NO"
    if manifest.get("owner_visual_check"):
        report.owner_visual_check_required = "YES"

    # 6. CRITICAL never auto-applies.
    if effective == "CRITICAL":
        report.production_changed = "NO"
        report.rollback = "NOT_NEEDED"
        report.owner_approval_required = "YES"
        report.status = "WAITING_OWNER_APPROVAL"
        approved, approval_detail = owner_approval_present(cfg, task["task_id"], manifest["_sha256"])
        report.log("owner approval: %s" % approval_detail)
        if approved and args.owner_approved and gates_ok and not args.dry_run:
            report.log("owner approval accepted, but CRITICAL apply is only performed "
                       "when the operator runs the dedicated approved invocation")
            report.next_action = ("CRITICAL prepared and owner-approved. Re-run with "
                                  "--owner-approved --apply-critical to execute.")
        else:
            report.next_action = (
                "CRITICAL prepared, production untouched. Owner must answer "
                "'CRITICAL APPROVAL: %s - APPROVE/CANCEL'. Gates: %s"
                % (manifest.get("description", task["task_id"]),
                   "all PASS" if gates_ok else "NOT all PASS, do not approve yet"))
        return report, task

    # 7. SAFE_PATCH.
    if not gates_ok:
        report.production_changed = "NO"
        report.rollback = "NOT_NEEDED"
        report.status = "STOPPED"
        report.next_action = "SAFE_PATCH gates did not all PASS - production untouched, patch must be revised in cloud/"
        report.log("safe patch refused: gates not all PASS")
        return report, task

    if args.dry_run:
        report.production_changed = "NO"
        report.status = "CONTINUE"
        report.next_action = "DRY RUN: all SAFE_PATCH gates PASS. Re-run without --dry-run to apply."
        return report, task

    prod_before = {}
    scan_ok = True
    try:
        for root in cfg.whitelist_roots:
            src_root = os.path.join(cfg.production_root, root)
            for rel, sha in snapshot_tree(src_root, limit=MAX_SCAN_FILES).items():
                prod_before["%s/%s" % (root, rel)] = sha
    except RuntimeError as exc:
        scan_ok = False
        report.log("pre-apply scan aborted: %s" % exc)

    report.log("applying %d file(s) to production" % len(sources))
    applied = apply_payload(cfg.production_root, sources)
    report.production_changed = "YES"
    report.files_changed = applied

    failures = []
    for rel, src in sources.items():
        dst = os.path.join(cfg.production_root, rel)
        if sha256_file(dst) != sha256_file(src):
            failures.append("%s: applied content does not match payload" % rel)
    for rel in applied:
        report.log("applied %s sha256_after=%s"
                   % (rel, sha256_file(os.path.join(cfg.production_root, rel))))

    unexpected = []
    if scan_ok:
        prod_after = {}
        try:
            for root in cfg.whitelist_roots:
                src_root = os.path.join(cfg.production_root, root)
                for rel, sha in snapshot_tree(src_root, limit=MAX_SCAN_FILES).items():
                    prod_after["%s/%s" % (root, rel)] = sha
        except RuntimeError as exc:
            report.log("post-apply scan aborted: %s" % exc)
            failures.append("post-apply scan aborted: %s" % exc)
        else:
            changed, added, removed = diff_snapshots(prod_before, prod_after)
            touched = set(changed) | set(added) | set(removed)
            unexpected = sorted(touched - set(allowed_rel))
            report.unexpected_changes = unexpected
            if unexpected:
                failures.append("unexpected changes: %s" % ", ".join(unexpected[:10]))
    report.site_integrity = "PASS" if (scan_ok and not unexpected) else ("FAIL" if scan_ok else "NOT_APPLICABLE")

    post_baseline_ok, post_baseline_detail = verify_protected_inventory(cfg)
    report.log("UA-0001..UA-0008 after apply: %s" % post_baseline_detail)
    if not post_baseline_ok:
        report.ua_baseline = "FAIL"
        failures.append(post_baseline_detail)
    post_crm_ok, post_crm_detail = verify_crm_integrity(cfg, read_only=True)
    report.log("crm after apply: %s" % post_crm_detail)
    if post_crm_ok is False:
        report.crm_integrity = "FAIL"
        failures.append(post_crm_detail)

    if failures:
        for item in failures:
            report.log("POST-APPLY FAILURE: %s" % item)
        ok, rb_failures = rollback_from_backup(cfg, backup_manifest)
        report.rollback = "PASS" if ok else "FAIL"
        report.production_changed = "NO" if ok else "YES"
        for item in rb_failures:
            report.log("rollback failure: %s" % item)
        if ok:
            report.log("rollback: production restored to pre-change SHA256")
            report.files_changed = []
            report.status = "STOPPED"
            report.next_action = "SAFE_PATCH failed post-apply verification and was rolled back - revise patch in cloud/"
        else:
            report.status = "WAITING_OWNER_APPROVAL"
            report.owner_approval_required = "YES"
            report.next_action = "ROLLBACK FAILED - production may be inconsistent, owner intervention required"
        return report, task

    report.rollback = "NOT_NEEDED"
    report.status = "CONTINUE"
    report.next_action = "SAFE_PATCH applied and verified. ChatGPT may issue the next round."
    if report.owner_visual_check_required == "YES":
        report.status = "WAITING_VISUAL_CHECK"
        report.next_action = "SAFE_PATCH applied. Owner visual check required."
    return report, task


# --------------------------------------------------------------------------
# Self test
# --------------------------------------------------------------------------

def _selftest_env(tmp):
    """Build a synthetic repo + production tree, return (cfg, args_namespace)."""
    repo = os.path.join(tmp, "repo")
    prod = os.path.join(tmp, "prod")
    state = os.path.join(tmp, "state")
    backups = os.path.join(tmp, "backups")
    for path in (repo, prod, state, backups):
        os.makedirs(path, exist_ok=True)
    os.makedirs(os.path.join(repo, "tasks"), exist_ok=True)
    os.makedirs(os.path.join(repo, "python"), exist_ok=True)
    os.makedirs(os.path.join(prod, "site", "cards"), exist_ok=True)
    write_text(os.path.join(prod, "site", "cards", "UA-0009.html"),
               "<html><body><h1>UA-0009</h1></body></html>\n")
    write_text(os.path.join(prod, "site", "cards", "UA-0001.html"),
               "<html><body><h1>UA-0001</h1></body></html>\n")
    cfg = Config({
        "repo_root": repo,
        "production_root": prod,
        "state_root": state,
        "backup_root": backups,
        "whitelist_roots": ["site/cards"],
        "git_sync": False,
        "git_push": False,
    })
    cfg.config_path = os.path.join(state, CONFIG_BASENAME)
    return cfg


def _selftest_task(cfg, number, mode):
    write_text(os.path.join(cfg.repo_root, "tasks", "task_%03d.md" % number),
               "# TASK %03d\n\nMODE: %s\nMAX_ROUNDS: 10\n" % (number, mode))


def _selftest_manifest(cfg, task_id, data, payload):
    patch_dir = os.path.join(cfg.repo_root, "cloud", "patches", task_id)
    os.makedirs(os.path.join(patch_dir, "files"), exist_ok=True)
    write_text(os.path.join(patch_dir, "patch_manifest.json"),
               json.dumps(data, indent=2) + "\n")
    for rel, content in payload.items():
        write_text(os.path.join(patch_dir, "files", rel), content)


class _Args(object):
    def __init__(self, **kw):
        self.round = kw.get("round", 1)
        self.manifest = kw.get("manifest")
        self.dry_run = kw.get("dry_run", False)
        self.keep_sandbox = kw.get("keep_sandbox", False)
        self.owner_approved = kw.get("owner_approved", False)


def self_test():
    results = []

    def check(name, condition, detail=""):
        results.append((name, bool(condition), detail))

    # -- unit level guards ------------------------------------------------
    check("reject absolute path", rel_path_is_safe("/etc/passwd") is not None)
    check("reject traversal", rel_path_is_safe("../../etc/passwd") is not None)
    check("accept normal path", rel_path_is_safe("site/cards/UA-0009.html") is None)
    check("deny crm.db", path_is_denied("data/crm.db") is not None)
    check("deny .env", path_is_denied("config/.env") is not None)
    check("deny media", path_is_denied("site/img/photo.jpg") is not None)
    check("deny backups dir", path_is_denied("backups/site/x.html") is not None)
    check("allow html", path_is_denied("site/cards/UA-0009.html") is None)
    # Built at runtime so no token-shaped literal is ever stored in the repo.
    fake_token = "gh" + "p_" + ("a" * 20) + "0123"
    check("secret scan finds github token",
          scan_patterns("token = " + fake_token, SECRET_PATTERNS))
    check("forbidden scan finds journal_mode",
          scan_patterns("PRAGMA journal_mode=WAL;", FORBIDDEN_CONTENT_PATTERNS))

    # -- scenario 1: READ_ONLY with no manifest ---------------------------
    tmp = tempfile.mkdtemp(prefix="ua-art-selftest-")
    try:
        cfg = _selftest_env(tmp)
        _selftest_task(cfg, 1, "READ_ONLY")
        report, _ = execute(cfg, _Args())
        check("read_only runs automatically", report.mode == "READ_ONLY" and report.status == "CONTINUE",
              "status=%s" % report.status)
        check("read_only writes nothing", report.production_changed == "NO")

        # -- scenario 2: CRITICAL task mode stops at owner approval -------
        _selftest_task(cfg, 2, "CRITICAL")
        _selftest_manifest(cfg, "task_002", {
            "task_id": "task_002",
            "mode": "SAFE_PATCH",
            "allowed_files": ["site/cards/UA-0009.html"],
            "expected_tests": ["html_wellformed"],
            "rollback_source": "auto_backup",
        }, {"site/cards/UA-0009.html": "<html><body><h1>UA-0009 v2</h1></body></html>\n"})
        report, _ = execute(cfg, _Args())
        check("critical task escalates manifest", report.mode == "CRITICAL", "mode=%s" % report.mode)
        check("critical stops at owner approval",
              report.status == "WAITING_OWNER_APPROVAL" and report.owner_approval_required == "YES",
              "status=%s" % report.status)
        check("critical never writes production", report.production_changed == "NO")
        current = read_text(os.path.join(cfg.production_root, "site/cards/UA-0009.html"))
        check("critical left target untouched", "v2" not in current)

        # -- scenario 3: SAFE_PATCH happy path ----------------------------
        _selftest_task(cfg, 3, "SAFE_PATCH")
        _selftest_manifest(cfg, "task_003", {
            "task_id": "task_003",
            "mode": "SAFE_PATCH",
            "allowed_files": ["site/cards/UA-0009.html"],
            "expected_tests": ["html_wellformed", "json_valid"],
            "rollback_source": "auto_backup",
            "ua_0009": True,
        }, {"site/cards/UA-0009.html": "<html><body><h1>UA-0009 v3</h1></body></html>\n"})
        report, _ = execute(cfg, _Args())
        check("safe_patch gates pass",
              report.backup == "PASS" and report.whitelist == "PASS"
              and report.sandbox == "PASS" and report.tests == "PASS",
              "backup=%s whitelist=%s sandbox=%s tests=%s"
              % (report.backup, report.whitelist, report.sandbox, report.tests))
        check("safe_patch applied", report.production_changed == "YES" and report.status == "CONTINUE",
              "status=%s" % report.status)
        check("safe_patch unexpected changes zero", report.unexpected_changes == [])
        check("safe_patch content live",
              "v3" in read_text(os.path.join(cfg.production_root, "site/cards/UA-0009.html")))
        check("ua_0009 ready reported", report.ua_0009_ready == "YES", report.ua_0009_ready)

        # -- scenario 4: failing test -> no write -------------------------
        _selftest_task(cfg, 4, "SAFE_PATCH")
        _selftest_manifest(cfg, "task_004", {
            "task_id": "task_004",
            "mode": "SAFE_PATCH",
            "allowed_files": ["site/cards/UA-0009.html"],
            "expected_tests": ["html_wellformed"],
            "rollback_source": "auto_backup",
        }, {"site/cards/UA-0009.html": "<html><body><h1>broken</body></html>\n"})
        before = read_text(os.path.join(cfg.production_root, "site/cards/UA-0009.html"))
        report, _ = execute(cfg, _Args())
        after = read_text(os.path.join(cfg.production_root, "site/cards/UA-0009.html"))
        check("failing test blocks apply", report.tests == "FAIL" and report.production_changed == "NO",
              "tests=%s changed=%s" % (report.tests, report.production_changed))
        check("failing test leaves production identical", before == after)

        # -- scenario 5: forbidden content (journal_mode) -----------------
        _selftest_task(cfg, 5, "SAFE_PATCH")
        os.makedirs(os.path.join(cfg.production_root, "site", "cards"), exist_ok=True)
        write_text(os.path.join(cfg.production_root, "site", "cards", "helper.py"), "X = 1\n")
        _selftest_manifest(cfg, "task_005", {
            "task_id": "task_005",
            "mode": "SAFE_PATCH",
            "allowed_files": ["site/cards/helper.py"],
            "expected_tests": ["python_compiles"],
            "rollback_source": "auto_backup",
        }, {"site/cards/helper.py": "import sqlite3\n# PRAGMA journal_mode=WAL\n"})
        report, _ = execute(cfg, _Args())
        check("journal_mode content blocked", report.tests == "FAIL" and report.production_changed == "NO")

        # -- scenario 6: manifest missing a required key ------------------
        _selftest_task(cfg, 6, "SAFE_PATCH")
        _selftest_manifest(cfg, "task_006", {
            "task_id": "task_006",
            "mode": "SAFE_PATCH",
            "allowed_files": ["site/cards/UA-0009.html"],
            "expected_tests": ["html_wellformed"],
        }, {"site/cards/UA-0009.html": "<html><body>x</body></html>\n"})
        report, _ = execute(cfg, _Args())
        check("incomplete manifest refused",
              report.status == "STOPPED" and report.production_changed == "NO",
              "status=%s" % report.status)

        # -- scenario 7: denied target (crm.db) ---------------------------
        _selftest_task(cfg, 7, "SAFE_PATCH")
        _selftest_manifest(cfg, "task_007", {
            "task_id": "task_007",
            "mode": "SAFE_PATCH",
            "allowed_files": ["site/cards/crm.db"],
            "expected_tests": ["html_wellformed"],
            "rollback_source": "auto_backup",
        }, {"site/cards/crm.db": "binary"})
        report, _ = execute(cfg, _Args())
        check("database target refused", report.status == "STOPPED" and report.production_changed == "NO")

        # -- scenario 8: unknown test name --------------------------------
        _selftest_task(cfg, 8, "SAFE_PATCH")
        _selftest_manifest(cfg, "task_008", {
            "task_id": "task_008",
            "mode": "SAFE_PATCH",
            "allowed_files": ["site/cards/UA-0009.html"],
            "expected_tests": ["rm -rf /"],
            "rollback_source": "auto_backup",
        }, {"site/cards/UA-0009.html": "<html><body>x</body></html>\n"})
        report, _ = execute(cfg, _Args())
        check("free-form test command refused", report.status == "STOPPED" and report.production_changed == "NO")

        # -- scenario 9: path traversal outside production ----------------
        _selftest_task(cfg, 9, "SAFE_PATCH")
        _selftest_manifest(cfg, "task_009", {
            "task_id": "task_009",
            "mode": "SAFE_PATCH",
            "allowed_files": ["../../etc/passwd"],
            "expected_tests": ["html_wellformed"],
            "rollback_source": "auto_backup",
        }, {"passwd": "x"})
        report, _ = execute(cfg, _Args())
        check("traversal refused", report.status == "STOPPED" and report.production_changed == "NO")

        # -- scenario 10: protected UA-0001 baseline violation ------------
        _selftest_task(cfg, 10, "SAFE_PATCH")
        _selftest_manifest(cfg, "task_010", {
            "task_id": "task_010",
            "mode": "SAFE_PATCH",
            "allowed_files": ["site/cards/UA-0009.html"],
            "expected_tests": ["html_wellformed"],
            "rollback_source": "auto_backup",
        }, {"site/cards/UA-0009.html": "<html><body><h1>UA-0009 v10</h1></body></html>\n"})
        write_text(os.path.join(cfg.production_root, "site", "cards", "UA-0001.html"),
                   "<html><body><h1>UA-0001 TAMPERED</h1></body></html>\n")
        report, _ = execute(cfg, _Args())
        check("protected baseline violation blocks patch",
              report.ua_baseline == "FAIL" and report.production_changed == "NO",
              "baseline=%s changed=%s" % (report.ua_baseline, report.production_changed))

        # -- scenario 11: rollback on post-apply failure ------------------
        # Restore baseline, then force a post-apply failure by tampering
        # with a protected file from inside the payload directory.
        write_text(os.path.join(cfg.production_root, "site", "cards", "UA-0001.html"),
                   "<html><body><h1>UA-0001</h1></body></html>\n")
        _selftest_task(cfg, 11, "SAFE_PATCH")
        _selftest_manifest(cfg, "task_011", {
            "task_id": "task_011",
            "mode": "SAFE_PATCH",
            "allowed_files": ["site/cards/UA-0009.html"],
            "expected_tests": ["html_wellformed"],
            "rollback_source": "auto_backup",
        }, {"site/cards/UA-0009.html": "<html><body><h1>UA-0009 v11</h1></body></html>\n"})
        pre = read_text(os.path.join(cfg.production_root, "site/cards/UA-0009.html"))
        original_apply = globals()["apply_payload"]

        def sabotaging_apply(dest_root, sources):
            written = original_apply(dest_root, sources)
            if os.path.realpath(dest_root) == os.path.realpath(cfg.production_root):
                # simulate a side effect the manifest never declared
                write_text(os.path.join(dest_root, "site", "cards", "stray.html"),
                           "<html><body>stray</body></html>\n")
            return written

        globals()["apply_payload"] = sabotaging_apply
        try:
            report, _ = execute(cfg, _Args())
        finally:
            globals()["apply_payload"] = original_apply
        post = read_text(os.path.join(cfg.production_root, "site/cards/UA-0009.html"))
        check("unexpected change detected", bool(report.unexpected_changes),
              "unexpected=%s" % report.unexpected_changes)
        check("automatic rollback performed", report.rollback == "PASS", "rollback=%s" % report.rollback)
        check("rollback restored content", pre == post)
        check("rollback recorded as no production change", report.production_changed == "NO")
        try:
            os.remove(os.path.join(cfg.production_root, "site", "cards", "stray.html"))
        except OSError:
            pass

        # -- scenario 12: report rendering --------------------------------
        text = report.render()
        for field in ("TASK_ID:", "ROUND:", "MODE:", "BACKUP:", "WHITELIST:", "SANDBOX:",
                      "TESTS:", "PRODUCTION_CHANGED:", "FILES_CHANGED:", "UNEXPECTED_CHANGES:",
                      "ROLLBACK:", "CRM_INTEGRITY:", "SITE_INTEGRITY:", "UA_0001_0008_UNCHANGED:",
                      "UA_0009_READY:", "OWNER_VISUAL_CHECK_REQUIRED:", "OWNER_APPROVAL_REQUIRED:",
                      "NEXT_ACTION:", "STATUS:"):
            check("report contains %s" % field.rstrip(":"), field in text)
        check("report has no secrets", not scan_patterns(text, SECRET_PATTERNS))

        # -- scenario 13: whitelist not configured ------------------------
        cfg2 = _selftest_env(os.path.join(tmp, "second"))
        cfg2.whitelist_roots = []
        _selftest_task(cfg2, 1, "SAFE_PATCH")
        _selftest_manifest(cfg2, "task_001", {
            "task_id": "task_001",
            "mode": "SAFE_PATCH",
            "allowed_files": ["site/cards/UA-0009.html"],
            "expected_tests": ["html_wellformed"],
            "rollback_source": "auto_backup",
        }, {"site/cards/UA-0009.html": "<html><body>x</body></html>\n"})
        report, _ = execute(cfg2, _Args())
        check("empty whitelist disables patching",
              report.whitelist == "FAIL" and report.production_changed == "NO")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print("UA ART autopilot runner self test")
    print("=" * 72)
    for name, ok, detail in results:
        line = "%-4s %s" % ("PASS" if ok else "FAIL", name)
        if detail and not ok:
            line += "  <- %s" % detail
        print(line)
    print("=" * 72)
    print("%d passed, %d failed, %d total" % (passed, failed, len(results)))
    return 0 if failed == 0 else 1


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(description="UA ART Autopilot Runner")
    p.add_argument("--repo", help="path to the local clone of ua-art-autopilot")
    p.add_argument("--production-root", help="root of the UA ART production tree")
    p.add_argument("--backup-root", help="backup root (must be outside the repository)")
    p.add_argument("--state-root", help="runner state/config/secrets root (outside the repository)")
    p.add_argument("--config", help="explicit runner config JSON path")
    p.add_argument("--manifest", help="explicit patch manifest path")
    p.add_argument("--round", type=int, help="round number (default: auto-increment)")
    p.add_argument("--dry-run", action="store_true", help="run every gate but never write to production")
    p.add_argument("--keep-sandbox", action="store_true", help="keep the sandbox directory for inspection")
    p.add_argument("--no-push", action="store_true", help="write the report but do not push it")
    p.add_argument("--no-sync", action="store_true", help="do not fetch/fast-forward before running")
    p.add_argument("--owner-approved", action="store_true",
                   help="operator asserts the owner approved this CRITICAL manifest")
    p.add_argument("--apply-critical", action="store_true",
                   help="reserved; CRITICAL apply is intentionally not automated in v1")
    p.add_argument("--init-inventory", action="store_true",
                   help="create the UA-0001..UA-0008 protected baseline and exit")
    p.add_argument("--print-config", action="store_true", help="print effective configuration and exit")
    p.add_argument("--self-test", action="store_true", help="run the built-in safety self test and exit")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.self_test:
        return self_test()

    cfg = load_config(args)
    os.makedirs(cfg.state_root, exist_ok=True)

    if args.print_config:
        data = cfg.as_dict()
        data["config_path"] = cfg.config_path
        data["config_exists"] = os.path.isfile(cfg.config_path)
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0

    if args.init_inventory:
        payload = init_protected_inventory(cfg)
        print("protected inventory written to %s (%d file(s))"
              % (cfg.inventory_path, payload["count"]))
        return 0

    if args.apply_critical:
        print("CRITICAL apply is not automated in runner v1. "
              "The owner must perform the approved change with explicit supervision.")
        return 2

    try:
        report, task = execute(cfg, args)
    except Exception:
        report = Report()
        report.status = "STOPPED"
        report.next_action = "Runner crashed, see log"
        report.log("unhandled exception:\n%s" % traceback.format_exc())
        task = None

    rel = report_rel_path(report.task_id if report.task_id != "UNKNOWN" else "task_000")
    abs_report = os.path.join(cfg.repo_root, rel)
    text = report.render()
    try:
        write_text(abs_report, text)
        print("report written to %s" % abs_report)
    except OSError as exc:
        print("could not write report: %s" % exc, file=sys.stderr)
        print(text)
        return 1

    if task and report.round:
        record_round(cfg, report.task_id, report.round)

    # The committed file is the file on disk. Push notes stay in stdout only,
    # so the work tree is never left dirty for the next fast-forward sync.
    if cfg.git_sync or cfg.git_push:
        git_commit_and_push_report(cfg, report, rel)

    print(report.render())
    return 0 if report.status in ("CONTINUE", "TASK_CLOSED", "WAITING_OWNER_APPROVAL", "WAITING_VISUAL_CHECK") else 1


if __name__ == "__main__":
    sys.exit(main())
