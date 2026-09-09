#!/usr/bin/env python3
"""Print a source audit as JSON; default is offline NOT_RUN.

Use --network only in the environment whose connectivity is being checked.
This CLI never opens CRM/state databases, writes reports, or sends a VIN.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", action="store_true", help="Perform public read-only GET probes (no VINs).")
    parser.add_argument("--context", default="local environment; worker verification pending")
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent / "runtime"))
    import source_policy
    report = source_policy.audit_sources(network=args.network, execution_origin=args.context)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # A generated report is not a successful live acceptance gate.
    return 0 if not args.network else (0 if report["pass_count"] == report["source_count"] else 2)


if __name__ == "__main__":
    raise SystemExit(main())
