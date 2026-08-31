#!/usr/bin/env python3
"""TASK096 v7: durable PythonAnywhere trigger for sandbox enrichment.

Replaces the brittle interactive-console launcher with an always-on/scheduled
one-shot trigger. The task remains sandbox-only; production authorization is
handled separately after all TASK096 gates pass.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.parse

import task096_data_enrichment_controller as ctl
import task096_enrichment_repair_v2 as repair

_TRIGGER_MAP: dict[int, list[tuple[str, int]]] = {}
_NEXT_HANDLE = 910_000_000


def _object_id(body: bytes) -> int | None:
    try:
        value = json.loads(body.decode("utf-8"))
    except Exception:
        return None
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        identifier = value.get("id")
        if isinstance(identifier, int) and identifier > 0:
            return identifier
    return None


def _delete_trigger(self, kind: str, identifier: int) -> None:
    endpoint = ctl.BASE + ("always_on/%d/" if kind == "always_on" else "schedule/%d/") % identifier
    try:
        self.request("DELETE", endpoint, allowed=(200, 202, 204, 404, 500), timeout=90)
    except Exception:
        # Cleanup must never turn a completed/continuable sandbox stage into a
        # false task failure. Stale trigger cleanup is best-effort only.
        pass


def durable_launch(self, command: str) -> int:
    global _NEXT_HANDLE
    description = "TASK096 v7 %d" % int(time.time())
    triggers: list[tuple[str, int]] = []

    form = urllib.parse.urlencode({
        "command": command,
        "description": description,
        "enabled": "true",
    }).encode()
    status, body = self.request(
        "POST", ctl.BASE + "always_on/", form,
        {"Content-Type": "application/x-www-form-urlencoded"},
        allowed=(200, 201, 202, 400, 403, 404, 409, 429, 500, 502, 503, 504),
        timeout=120,
    )
    identifier = _object_id(body) if status in (200, 201, 202) else None
    if identifier:
        triggers.append(("always_on", identifier))
    else:
        # Fallback to bounded scheduled one-shot attempts. They are removed as
        # soon as the controller receives its receipt.
        origin = dt.datetime.now(dt.timezone.utc)
        for sequence, minutes in enumerate((2, 5, 9), start=1):
            at = origin + dt.timedelta(minutes=minutes)
            scheduled = urllib.parse.urlencode({
                "command": command,
                "description": description + " fallback-%d" % sequence,
                "enabled": "true",
                "interval": "daily",
                "hour": at.hour,
                "minute": at.minute,
            }).encode()
            status, body = self.request(
                "POST", ctl.BASE + "schedule/", scheduled,
                {"Content-Type": "application/x-www-form-urlencoded"},
                allowed=(200, 201, 202, 429, 500, 502, 503, 504),
                timeout=120,
            )
            if status not in (200, 201, 202):
                continue
            identifier = _object_id(body)
            if identifier:
                triggers.append(("schedule", identifier))
        if not triggers:
            raise ctl.ControllerError("DURABLE_REMOTE_TRIGGER_UNAVAILABLE")

    _NEXT_HANDLE += 1
    handle = _NEXT_HANDLE
    _TRIGGER_MAP[handle] = triggers
    return handle


def durable_cleanup(self, handle: int | None) -> None:
    if not handle:
        return
    triggers = _TRIGGER_MAP.pop(int(handle), [])
    for kind, identifier in triggers:
        _delete_trigger(self, kind, identifier)


def main() -> int:
    ctl.PythonAnywhereAPI.launch = durable_launch
    ctl.PythonAnywhereAPI.cleanup_console = durable_cleanup
    repair.ctl.PythonAnywhereAPI.launch = durable_launch
    repair.ctl.PythonAnywhereAPI.cleanup_console = durable_cleanup
    return repair.main()


if __name__ == "__main__":
    raise SystemExit(main())
