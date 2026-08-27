#!/usr/bin/env python3
"""Bounded, read-only discovery tool for TASK 042.

Designed to run against real UA ART source paths on PythonAnywhere via
the already-reviewed safe-inbox / read-only discovery path. In THIS
execution context (Claude/Cloud sandbox) there is no filesystem access
to /home/Carix, so running without arguments correctly reports
NOT_PROVEN instead of fabricating results. The tool is otherwise
complete and ready to execute for real once pointed at an approved root.

Safety bounds:
- read-only (never writes/opens files for writing)
- bounded file count and per-file byte size
- skips symlinks
- restricted to a small set of plausible text/template extensions
- redacts nothing itself (no secret-bearing content is expected in
  matched lines, but callers should still redact before publishing)
"""
import hashlib
import json
import os
import sys
from pathlib import Path

CANDIDATE_PATTERNS = [
    "В море", "В море:", "В море ·", "в море", "Море", "Море:",
    "У морі", "У морі:", "у морі",
    "На пароме", "на пароме", "Паром",
    "На поромі", "на поромі", "Пором",
]

ALLOWED_SUFFIXES = {".html", ".htm", ".py", ".json", ".txt", ".j2", ".jinja", ".jinja2", ".md"}
MAX_FILES = 5000
MAX_FILE_BYTES = 2_000_000


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_root(root: Path):
    occurrences = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".git")]
        for fn in filenames:
            if count > MAX_FILES:
                return occurrences
            p = Path(dirpath) / fn
            if p.is_symlink():
                continue
            if p.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            count += 1
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                low = line.lower()
                for pat in CANDIDATE_PATTERNS:
                    if pat.lower() in low:
                        occurrences.append({
                            "file": str(p),
                            "line": lineno,
                            "pattern": pat,
                            "sha256_file": sha256_of(p),
                        })
    return occurrences


def main():
    if len(sys.argv) < 2:
        result = {
            "status": "NOT_PROVEN",
            "reason": (
                "No approved real source root was provided/accessible in "
                "this execution context (no filesystem access to "
                "/home/Carix from Claude/Cloud sandbox). This tool is "
                "ready to execute for real once run on PythonAnywhere "
                "against an approved read-only root via the safe-inbox path."
            ),
            "occurrences": [],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    root = Path(sys.argv[1])
    if not root.exists():
        print(json.dumps({"status": "NOT_PROVEN", "reason": f"root not found: {root}"}, ensure_ascii=False))
        return 1
    occ = scan_root(root)
    print(json.dumps({"status": "SCANNED", "root": str(root), "occurrences": occ}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
