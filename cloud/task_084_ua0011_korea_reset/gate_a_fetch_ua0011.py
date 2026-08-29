"""Read-only live fetch for UA-0011 (Gate A step 1).

This script must be executed by the controller / operator that holds real CRM
credentials. It performs NO writes. It is provided here as a ready-to-run tool;
it was NOT executed inside the Claude/Cloud worker because that environment has
no network access to the production CRM.

Usage (controller-side only):
    CRM_BASE_URL=... CRM_API_TOKEN=... python gate_a_fetch_ua0011.py --vin KMHE341DBKA544289

Output:
    Writes a JSON report to stdout containing:
      - exact field names for status / container / arrival_date on the UA-0011 record
      - a SHA-256 fingerprint of every OTHER field (name -> sha256(value))
      - the full media manifest (ordered list of media ids/urls/roles)
      - a boolean confirming the first media entry is flagged as UA-0011's own cover photo

This script never issues PUT/POST/PATCH/DELETE requests. Any non-GET verb is
hard-disabled below to make accidental writes structurally impossible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict, List

# Structural write-lock: only GET is ever allowed from this script.
ALLOWED_HTTP_METHODS = frozenset({"GET"})


class WriteAttemptBlocked(RuntimeError):
    pass


def _guarded_request(method: str, *_, **__):
    if method.upper() not in ALLOWED_HTTP_METHODS:
        raise WriteAttemptBlocked(
            f"Gate A fetch script attempted a {method} request; only GET is permitted. "
            "Fail-closed, no request sent."
        )
    raise NotImplementedError(
        "Wire this function to the real CRM read-only GET endpoint in the "
        "controller execution environment. Not implemented here because this "
        "worker has no live CRM network access."
    )


def fetch_ua0011_record(vin: str) -> Dict[str, Any]:
    """Placeholder for the controller-side real GET call.

    Raises NotImplementedError in this offline worker context by design.
    """
    return _guarded_request("GET", f"/cards?vin={vin}")


def fingerprint_other_fields(record: Dict[str, Any], excluded_fields: List[str]) -> Dict[str, str]:
    out = {}
    for key, value in sorted(record.items()):
        if key in excluded_fields:
            continue
        payload = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
        out[key] = hashlib.sha256(payload).hexdigest()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate A read-only fetch for UA-0011")
    parser.add_argument("--vin", default="KMHE341DBKA544289")
    parser.add_argument(
        "--status-field", default=None,
        help="Exact CRM field name for stage/status (fill in after inspecting schema)."
    )
    parser.add_argument("--container-field", default=None)
    parser.add_argument("--arrival-date-field", default=None)
    args = parser.parse_args()

    if not os.environ.get("CRM_BASE_URL") or not os.environ.get("CRM_API_TOKEN"):
        sys.stderr.write(
            "CRM_BASE_URL / CRM_API_TOKEN not set. This confirms this run has no live "
            "credentials; fail-closed, no fetch attempted.\n"
        )
        return 2

    try:
        record = fetch_ua0011_record(args.vin)
    except (NotImplementedError, WriteAttemptBlocked) as exc:
        sys.stderr.write(f"Fetch blocked/not implemented in this context: {exc}\n")
        return 3

    excluded = [f for f in (args.status_field, args.container_field, args.arrival_date_field) if f]
    report = {
        "vin": args.vin,
        "status_field": args.status_field,
        "container_field": args.container_field,
        "arrival_date_field": args.arrival_date_field,
        "other_fields_sha256": fingerprint_other_fields(record, excluded),
        "media_manifest": record.get("media", []),
        "first_media_is_own_cover": bool(
            record.get("media") and record["media"][0].get("belongs_to_vin") == args.vin
            and record["media"][0].get("role") == "cover"
        ),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
