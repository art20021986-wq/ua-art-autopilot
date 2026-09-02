#!/usr/bin/env python3
"""Derive a stable numeric production-queue ticket from a task request."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re


class TicketError(ValueError):
    pass


def safe_request_path(value: str) -> pathlib.Path:
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise TicketError("UNSAFE_REQUEST_PATH")
    text = path.as_posix()
    if not text.startswith("tasks/requests/") or not text.endswith(".json"):
        raise TicketError("REQUEST_SCOPE")
    disk = pathlib.Path(text)
    if disk.is_symlink() or not disk.is_file():
        raise TicketError("REQUEST_MISSING")
    return disk


def ticket_from_task_id(task_id: str) -> int:
    text = str(task_id).strip()
    match = re.search(r"(?i)(?:^|[^A-Za-z])TASK[_-]?0*(\d{1,9})(?:[^0-9]|$)", text)
    if match:
        value = int(match.group(1))
        if value > 0:
            return value
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return 500_000_000 + int.from_bytes(digest[:4], "big") % 400_000_000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("request_path")
    args = parser.parse_args()
    path = safe_request_path(args.request_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw.get("task_id"):
        raise TicketError("TASK_ID_MISSING")
    print(ticket_from_task_id(str(raw["task_id"])))


if __name__ == "__main__":
    main()
