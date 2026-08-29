"""TASK 073 ROUND 5 - gate_b_installer_v4.py

Runs ON the PythonAnywhere host only, invoked by gate_b_controller_v4.py
via a manual, owner-approved Gate B run. Never auto-triggered. Performs
backup, SHA-anchored patch application, atomic install, exactly one real
publisher call for UA-0011, and rollback-on-any-failure.

Usage on the remote host only:
    python3.10 gate_b_installer_v4.py --root /home/Carix --shadow
    python3.10 gate_b_installer_v4.py --root /home/Carix --install
    python3.10 gate_b_installer_v4.py --root /home/Carix --rollback --backup-dir <dir>
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patcher_v4 as pv4

CODE_FILES = list(pv4.FULL_FILE_ANCHORS.keys())


def _sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _write_atomic(path, content):
    tmp = path + ".tmp_v4"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(content)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def backup_code(root, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    manifest = {}
    for filename in CODE_FILES:
        src = os.path.join(root, filename)
        dst = os.path.join(backup_dir, filename)
        shutil.copy2(src, dst)
        manifest[filename] = _sha256_file(src)
    with open(os.path.join(backup_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    return manifest


def build_candidates(root):
    sources = {f: _read(os.path.join(root, f)) for f in CODE_FILES}
    candidates = {}
    candidates["konteyner.py"] = pv4.patch_konteyner(sources["konteyner.py"])
    candidates["cars_ui.py"] = pv4.patch_cars_ui(sources["cars_ui.py"])
    candidates["stranica.py"] = pv4.patch_seo068_stale_precondition("stranica.py", sources["stranica.py"])
    candidates["master_card.py"] = pv4.patch_seo068_stale_precondition("master_card.py", sources["master_card.py"])
    candidates["yadro.py"] = pv4.patch_seo068_stale_precondition("yadro.py", sources["yadro.py"])
    candidates["publikaciya.py"] = pv4.patch_publikaciya(sources["publikaciya.py"])
    return candidates


def rollback_code(root, backup_dir):
    for filename in CODE_FILES:
        src = os.path.join(backup_dir, filename)
        dst = os.path.join(root, filename)
        shutil.copy2(src, dst)


def run_shadow(root):
    result = {"mode": "shadow", "production_writes": 0}
    try:
        candidates = build_candidates(root)
        for filename, content in candidates.items():
            compile(content, filename, "exec")
        result["status"] = "SHADOW_PASS"
        result["files"] = list(candidates.keys())
    except Exception as exc:
        result["status"] = "SHADOW_FAIL"
        result["reason"] = str(exc)
    return result


def run_install(root):
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backup_dir = os.path.join(root, "autopilot_inbox", "cloud", "task_073", "backups", ts)
    result = {"mode": "install", "backup_dir": backup_dir}
    try:
        manifest = backup_code(root, backup_dir)
        result["preimage_sha"] = manifest
        candidates = build_candidates(root)
        for filename, content in candidates.items():
            compile(content, filename, "exec")
        for filename, content in candidates.items():
            _write_atomic(os.path.join(root, filename), content)
        for filename in CODE_FILES:
            actual = _sha256_file(os.path.join(root, filename))
            expected = hashlib.sha256(candidates[filename].encode("utf-8")).hexdigest()
            if actual != expected:
                raise RuntimeError("READBACK_MISMATCH:%s" % filename)

        spec = importlib.util.spec_from_file_location("publikaciya_v4", os.path.join(root, "publikaciya.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        ok, msg = module.opublikovat("UA-0011", proba=False)
        result["publish_ok"] = ok
        result["publish_message"] = msg
        if not ok:
            raise RuntimeError("PUBLISH_FAILED:%s" % msg)
        result["status"] = "INSTALL_PASS"
    except Exception as exc:
        rollback_code(root, backup_dir)
        result["status"] = "INSTALL_FAIL_ROLLED_BACK"
        result["reason"] = str(exc)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--backup-dir", default=None)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--shadow", action="store_true")
    group.add_argument("--install", action="store_true")
    group.add_argument("--rollback", action="store_true")
    args = parser.parse_args()

    if args.shadow:
        result = run_shadow(args.root)
    elif args.install:
        result = run_install(args.root)
    else:
        if not args.backup_dir:
            result = {"status": "ROLLBACK_FAIL", "reason": "missing --backup-dir"}
        else:
            rollback_code(args.root, args.backup_dir)
            result = {"status": "ROLLBACK_DONE", "backup_dir": args.backup_dir}

    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] not in ("SHADOW_PASS", "INSTALL_PASS", "ROLLBACK_DONE"):
        sys.exit(1)


if __name__ == "__main__":
    main()
