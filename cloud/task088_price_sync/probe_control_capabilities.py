#!/usr/bin/env python3
"""Read-only, presence-only control transport probe for the observed CRM host.

No credential contents, lengths, source bodies, arbitrary environment entries,
network requests, imports of deployed modules or persistent writes are emitted.
Run on the host already authenticated by the operator's existing PA session.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
ROOT = Path("/home/Carix")
# Deployed paths grounded in current start_safe.py (TARGET run_all.py), the
# captured CRM source, and the repository's approval_gate deployment plan.
SOURCE_FILES = (
    "start_safe.py", "run_all.py", "team_bot.py", "db.py", "uaart_bridge_wsgi.py",
    "autopilot_inbox/cloud/approval_gate/claude_owner_approval_mcp.py",
    "autopilot_inbox/cloud/approval_gate/pythonanywhere_approval_gate.py",
)
# These names occur in current repository transport/approval source. An owner
# approval or PythonAnywhere credential is not a GitHub-reader credential.
KNOWN_NAMES = frozenset({"GH_TOKEN", "GITHUB_TOKEN", "PYTHONANYWHERE_API_TOKEN",
                         "MCP_OWNER_APPROVAL_SECRET"})
MAX_SOURCE = 4 * 1024 * 1024


def source_fact(relative):
    path = ROOT / relative
    fact = {"path": str(path), "present": path.exists(), "symlink": path.is_symlink()}
    if not fact["present"] or fact["symlink"]:
        return fact
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE:
        fact["inspection"] = "NOT_A_BOUNDED_REGULAR_SOURCE"
        return fact
    raw = path.read_bytes()
    fact["sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        tree = ast.parse(raw.decode("utf-8"))
        names = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or not node.args:
                continue
            owner = node.func.value
            is_env = (node.func.attr == "getenv" and isinstance(owner, ast.Name) and owner.id == "os"
                      or node.func.attr == "get" and isinstance(owner, ast.Attribute)
                      and owner.attr == "environ" and isinstance(owner.value, ast.Name) and owner.value.id == "os")
            key = node.args[0]
            if is_env and isinstance(key, ast.Constant) and type(key.value) is str and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", key.value):
                names.add(key.value)
        fact["environment_variable_names"] = sorted(names)
    except (SyntaxError, UnicodeDecodeError):
        fact["inspection"] = "UNPARSEABLE_SOURCE"
    return fact


def credential_presence(raw_environment):
    """Discard every value immediately after computing its boolean presence."""
    result = {key: False for key in sorted(KNOWN_NAMES)}
    for item in raw_environment.split(b"\0"):
        name, separator, value = item.partition(b"=")
        if not separator:
            continue
        try:
            name = name.decode("ascii")
        except UnicodeDecodeError:
            continue
        if name in KNOWN_NAMES:
            result[name] = bool(value)
    return result


def main():
    if Path.home() != ROOT or not ROOT.is_dir():
        raise SystemExit("OBSERVED_CARIX_HOST_REQUIRED")
    result = {"kind": "READ_ONLY_CONTROL_CAPABILITY_PRESENCE", "network_used": False,
              "production_written": False, "credentials_exported": False,
              "current_process": {key: bool(os.environ.get(key)) for key in sorted(KNOWN_NAMES)},
              "known_sources": [], "crm_processes": []}
    for relative in SOURCE_FILES:
        try:
            result["known_sources"].append(source_fact(relative))
        except OSError as exc:
            result["known_sources"].append({"path": str(ROOT / relative), "error_type": type(exc).__name__})
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if proc.stat().st_uid != os.geteuid():
                continue
            cmd = (proc / "cmdline").read_bytes().split(b"\0")
            if b"/home/Carix/start_safe.py" not in cmd:
                continue
            result["crm_processes"].append({"pid": int(proc.name),
                "known_credential_names_present": credential_presence((proc / "environ").read_bytes())})
        except OSError:
            continue
    result["crm_processes"].sort(key=lambda row: row["pid"])
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
