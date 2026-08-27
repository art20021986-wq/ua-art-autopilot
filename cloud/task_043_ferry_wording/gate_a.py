"""TASK 043 — Isolated Gate A builder/runner.

Writes are only ever performed under the three approved task-043 roots.
Every write is atomic (temp file + fsync + os.replace). On any failure,
every file written during the current call is rolled back. Path escapes
and symlink components in the destination roots are rejected before any
write happens.

Standard library only.
"""

import difflib
import hashlib
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from transform import transform_html  # noqa: E402

ALLOWED_PREVIEW_ROOT = "/home/Carix/video/preview/task-043-ferry-wording/"
ALLOWED_REPORT_ROOT = "/home/Carix/video/reports/task-043-ferry-wording/"
ALLOWED_STAGING_ROOT = "/home/Carix/autopilot_runs/task_043_ferry_wording/"


class GateABlocked(Exception):
    pass


def _validate_under(path, allowed_root):
    norm_root = os.path.normpath(allowed_root)
    norm_path = os.path.normpath(path)
    if not (norm_path == norm_root or norm_path.startswith(norm_root + os.sep)):
        raise GateABlocked("path %r escapes allowed root %r" % (path, allowed_root))
    cur = os.sep
    for part in norm_path.split(os.sep):
        if not part:
            continue
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise GateABlocked("symlink component rejected: %s" % cur)
    return norm_path


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data_bytes):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data_bytes)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def build_gate_a(source_root, candidate_relpaths, staging_root, preview_root,
                  report_root, lang_for_file=None,
                  preview_allowed_root=ALLOWED_PREVIEW_ROOT,
                  report_allowed_root=ALLOWED_REPORT_ROOT,
                  staging_allowed_root=ALLOWED_STAGING_ROOT):
    """Build isolated preview copies with contextual transforms applied.

    Only .html candidates are transformed in this round; every other
    source type is recorded as AMBIGUOUS/blocked because no per-file
    reviewed anchor mapping has been produced yet for Python/template
    sources (per TASK 043 section 1: 'ambiguous or multiple anchors
    BLOCK; never guess').
    """
    _validate_under(staging_root, staging_allowed_root)
    _validate_under(preview_root, preview_allowed_root)
    _validate_under(report_root, report_allowed_root)
    lang_for_file = lang_for_file or {}
    manifest = {"files": [], "blocked": []}
    written_paths = []
    try:
        for rel_path in candidate_relpaths:
            if os.path.isabs(rel_path) or ".." in rel_path.replace("\\", "/").split("/"):
                manifest["blocked"].append({"path": rel_path, "reason": "path escape rejected"})
                continue
            full_source = os.path.join(source_root, rel_path)
            if not os.path.isfile(full_source) or os.path.islink(full_source):
                manifest["blocked"].append({"path": rel_path, "reason": "source missing or symlink"})
                continue
            with open(full_source, "rb") as fh:
                original = fh.read()
            sha_before = sha256_bytes(original)
            if rel_path.endswith(".html"):
                lang = lang_for_file.get(rel_path, "ru")
                text = original.decode("utf-8", errors="strict")
                new_text, occurrences = transform_html(text, lang=lang)
                new_bytes = new_text.encode("utf-8")
            else:
                manifest["blocked"].append({
                    "path": rel_path,
                    "reason": "AMBIGUOUS: no reviewed per-file transform for this source type in this round",
                })
                continue
            sha_after = sha256_bytes(new_bytes)
            staged_path = os.path.join(staging_root, rel_path)
            preview_path = os.path.join(preview_root, rel_path)
            atomic_write(staged_path, new_bytes)
            written_paths.append(staged_path)
            atomic_write(preview_path, new_bytes)
            written_paths.append(preview_path)
            diff = list(difflib.unified_diff(
                original.decode("utf-8", errors="replace").splitlines(),
                new_bytes.decode("utf-8", errors="replace").splitlines(),
                lineterm="",
            ))
            manifest["files"].append({
                "path": rel_path,
                "sha_before": sha_before,
                "sha_after": sha_after,
                "occurrences": occurrences,
                "diff": diff,
            })
        receipt = {
            "task": "task_043_ferry_wording",
            "manifest": manifest,
            "production_touched": "NO",
            "crm_touched": "NO",
            "gate_b_executed": "NO",
        }
        report_path = os.path.join(report_root, "receipt.json")
        atomic_write(report_path, json.dumps(receipt, sort_keys=True).encode("utf-8"))
        written_paths.append(report_path)
        return receipt
    except Exception:
        for p in written_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        raise


def determinism_check(source_root, candidate_relpaths, lang_for_file=None, runs=10):
    """Prove the transform output hash is stable across N repeated runs."""
    lang_for_file = lang_for_file or {}
    hashes = set()
    for _ in range(runs):
        parts = []
        for rel_path in candidate_relpaths:
            full_source = os.path.join(source_root, rel_path)
            if not os.path.isfile(full_source):
                continue
            with open(full_source, "rb") as fh:
                original = fh.read()
            if rel_path.endswith(".html"):
                lang = lang_for_file.get(rel_path, "ru")
                new_text, _ = transform_html(original.decode("utf-8"), lang=lang)
                parts.append(sha256_bytes(new_text.encode("utf-8")))
        hashes.add(sha256_bytes("|".join(parts).encode("utf-8")))
    return len(hashes) == 1, hashes
