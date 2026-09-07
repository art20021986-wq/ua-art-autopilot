#!/usr/bin/env python3
"""Read the exact UA-0017 VIN from CRM and invoke the read-only Gate A probe."""

from __future__ import annotations

import runpy
import sqlite3
import sys


sys.dont_write_bytecode = True

CRM_URI = "file:/home/Carix/crm.db?mode=ro&immutable=1"
PROBE_PATH = "/home/Carix/task116_gate_a_sandbox/remote_gate_a.py"


def main() -> None:
    connection = sqlite3.connect(CRM_URI, uri=True)
    try:
        rows = connection.execute(
            "SELECT vin FROM cars WHERE auto_number = ?", ("UA-0017",)
        ).fetchall()
    finally:
        connection.close()

    if len(rows) != 1 or not str(rows[0][0] or "").strip():
        raise SystemExit("exact UA-0017 VIN was not found")

    sys.argv = [
        PROBE_PATH,
        "--root",
        "/home/Carix",
        "--uid",
        "UA-0017",
        "--vin",
        str(rows[0][0]),
    ]
    runpy.run_path(PROBE_PATH, run_name="__main__")


if __name__ == "__main__":
    main()
