#!/usr/bin/env python3
"""TASK096 v8: resilient transport + durable remote trigger, sandbox only.

The v7 run reached the remote trigger but stopped on a PythonAnywhere network
read timeout. v8 keeps all TASK096 safety boundaries and adds bounded retries
around transient PythonAnywhere transport failures before delegating to v7.
"""
from __future__ import annotations

import time

import task096_data_enrichment_controller as ctl
import task096_enrichment_repair_v7 as v7

_ORIGINAL_REQUEST = ctl.PythonAnywhereAPI.request
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_TRANSIENT_MARKERS = (
    "PYTHONANYWHERE_NETWORK_ERROR",
    "PYTHONANYWHERE_HTTP_429",
    "PYTHONANYWHERE_HTTP_500",
    "PYTHONANYWHERE_HTTP_502",
    "PYTHONANYWHERE_HTTP_503",
    "PYTHONANYWHERE_HTTP_504",
    "TimeoutError",
    "timed out",
)


def resilient_request(self, method, url, data=None, headers=None, allowed=(200,), timeout=90):
    last = None
    for attempt in range(1, 7):
        try:
            status, body = _ORIGINAL_REQUEST(
                self, method, url, data=data, headers=headers,
                allowed=allowed, timeout=max(int(timeout or 90), 120),
            )
            if status in _TRANSIENT_STATUS and attempt < 6:
                last = ctl.ControllerError("TRANSIENT_HTTP_%d" % status)
                time.sleep(min(3 * attempt, 15))
                continue
            return status, body
        except Exception as exc:
            last = exc
            text = type(exc).__name__ + ":" + str(exc)
            if not any(marker in text for marker in _TRANSIENT_MARKERS) or attempt >= 6:
                raise
            print("TASK096_TRANSPORT_RETRY=%d;ERROR=%s" % (attempt, type(exc).__name__))
            time.sleep(min(3 * attempt, 15))
    raise ctl.ControllerError("PYTHONANYWHERE_TRANSIENT_RETRIES_EXHAUSTED:" + str(last)[:300])


def main() -> int:
    ctl.PythonAnywhereAPI.request = resilient_request
    v7.ctl.PythonAnywhereAPI.request = resilient_request
    return v7.main()


if __name__ == "__main__":
    raise SystemExit(main())
