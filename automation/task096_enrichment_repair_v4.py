#!/usr/bin/env python3
"""TASK096 v4: repair transient PythonAnywhere console readiness (HTTP 412)."""
from __future__ import annotations
import time
import task096_data_enrichment_controller as ctl
import task096_enrichment_repair_v3 as repair


def ready_launch(self, command: str) -> int:
    last = None
    for outer in range(1, 4):
        console = self.create_console()
        try:
            for attempt in range(1, 8):
                try:
                    self.send_console(console, command)
                    return console
                except Exception as exc:
                    last = exc
                    if 'HTTP_412' not in str(exc):
                        raise
                    time.sleep(min(2 * attempt, 10))
        except Exception:
            self.cleanup_console(console)
            raise
        self.cleanup_console(console)
        time.sleep(3 * outer)
    raise ctl.ControllerError('CONSOLE_NOT_READY_AFTER_RETRIES:' + str(last)[:240])


def main() -> int:
    ctl.PythonAnywhereAPI.launch = ready_launch
    repair.ctl.PythonAnywhereAPI.launch = ready_launch
    repair.repair.ctl.PythonAnywhereAPI.launch = ready_launch
    return repair.main()


if __name__ == '__main__':
    raise SystemExit(main())
