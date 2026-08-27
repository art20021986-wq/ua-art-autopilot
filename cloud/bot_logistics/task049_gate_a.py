#!/usr/bin/env python3
"""TASK 049 Gate A: build and compile one isolated cars_ui.py candidate.

The only writable locations are two exact files below autopilot_inbox. The
live source is opened read-only and is never imported or replaced. crm.db,
services, schedules, consoles and web apps are not touched.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import py_compile
import stat
import tempfile

import task049_transform as transform

TASK_ID = "task_049"
MODE = "GATE_A_ISOLATED_CANDIDATE"
SOURCE_PATH = pathlib.Path("/home/Carix/cars_ui.py")
SAFE_ROOT = pathlib.Path("/home/Carix/autopilot_inbox/cloud/bot_logistics")
CANDIDATE_PATH = SAFE_ROOT / "task049_cars_ui.py.candidate"
PYC_PATH = SAFE_ROOT / "task049_cars_ui.py.candidate.pyc"
MAX_SOURCE_BYTES = 2_000_000


class GateABlocked(RuntimeError):
    pass


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def read_live_source() -> tuple[str, str]:
    before = os.lstat(SOURCE_PATH)
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise GateABlocked("source_not_single_regular_file")
    if not 0 < before.st_size <= MAX_SOURCE_BYTES:
        raise GateABlocked("source_size_out_of_bounds")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(SOURCE_PATH, flags)
    chunks: list[bytes] = []
    total = 0
    try:
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            raise GateABlocked("source_changed_during_open")
        while True:
            chunk = os.read(descriptor, min(65_536, MAX_SOURCE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_SOURCE_BYTES:
                raise GateABlocked("source_size_out_of_bounds")
        opened_after = os.fstat(descriptor)
        path_after = os.lstat(SOURCE_PATH)
        if _identity(opened_after) != _identity(before) or _identity(path_after) != _identity(before):
            raise GateABlocked("source_changed_during_read")
    finally:
        os.close(descriptor)
    data = b"".join(chunks)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise GateABlocked("source_not_utf8") from exc
    return text, hashlib.sha256(data).hexdigest()


def atomic_candidate(text: str) -> None:
    if SAFE_ROOT.resolve(strict=True) != SAFE_ROOT:
        raise GateABlocked("safe_root_not_canonical")
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=SAFE_ROOT,
        prefix=".task049_candidate.",
        suffix=".tmp",
        delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, CANDIDATE_PATH)
    finally:
        if temporary.exists():
            temporary.unlink()


def _base_receipt() -> dict:
    return {
        "task_id": TASK_ID,
        "mode": MODE,
        "status": "BLOCKED",
        "source_path": str(SOURCE_PATH),
        "candidate_path": str(CANDIDATE_PATH),
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "service_reload": False,
        "gate_b_executed": False,
        "ua0009_published": False,
        "errors": [],
    }


def run_gate_a() -> dict:
    receipt = _base_receipt()
    try:
        source, source_sha = read_live_source()
        if source_sha != transform.EXPECTED_SOURCE_SHA256:
            raise GateABlocked("source_sha256_mismatch")
        result = transform.transform_source(source, transform.EXPECTED_SOURCE_SHA256)
        checks = transform.validate_candidate(result.candidate)
        atomic_candidate(result.candidate)
        try:
            py_compile.compile(
                str(CANDIDATE_PATH),
                cfile=str(PYC_PATH),
                doraise=True,
            )
        except py_compile.PyCompileError as exc:
            raise GateABlocked("candidate_py_compile_failed") from exc
        finally:
            try:
                PYC_PATH.unlink()
            except FileNotFoundError:
                pass
        persisted = CANDIDATE_PATH.read_bytes()
        persisted_sha = hashlib.sha256(persisted).hexdigest()
        if persisted_sha != result.candidate_sha256:
            raise GateABlocked("candidate_readback_hash_mismatch")
        receipt.update(
            {
                "status": "PASS",
                "source_sha256": result.source_sha256,
                "candidate_sha256": result.candidate_sha256,
                "candidate_size": len(persisted),
                "operations": list(result.operations),
                "checks": checks,
                "already_applied": result.already_applied,
                "errors": [],
            }
        )
    except (GateABlocked, transform.TransformBlocked) as exc:
        receipt["errors"] = [str(exc)]
    except (OSError, ValueError, TypeError):
        receipt["errors"] = ["gate_a_io_or_validation_failure"]
    return receipt


def main() -> int:
    receipt = run_gate_a()
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

