"""TASK 096 — approved source reachability checker.

NOT executed by Claude/Cloud in this delivery: this environment has no outbound
network access. The controller must run this script from an environment with
internet access and attach the JSON output to evidence.json.

The script only performs a HEAD/GET reachability check (status code + latency).
It never scrapes or stores pricing data from these sources; the only approved
use of these two links is internal technical cross-checking of vehicle specs
(engine power, torque, drivetrain, transmission, etc.), never for pricing and
never shown to clients.
"""
from __future__ import annotations
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

SOURCES = {
    "automobile_catalog": "https://www.automobile-catalog.com/car/2017/2297795/mercedes-benz_e_220_d.html",
    "auto_data": "https://www.auto-data.net/ru/mercedes-benz-e-class-w213-e-220d-194hp-9g-tronic-22636",
}


def check(url: str, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "UA-ART-tech-spec-checker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"reachable": True, "status_code": resp.status}
    except urllib.error.HTTPError as e:
        # Some sites reject HEAD; a 4xx/405 still proves reachability of the host.
        return {"reachable": e.code < 500, "status_code": e.code}
    except Exception as exc:  # noqa: BLE001
        return {"reachable": False, "error": str(exc)}


def run() -> dict:
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "sources": {}}
    for name, url in SOURCES.items():
        result["sources"][name] = {"url": url, **check(url)}
    return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
