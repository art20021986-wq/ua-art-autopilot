#!/usr/bin/env python3
"""Immediate/delayed production verification for TASK 081 Gate B."""

from __future__ import annotations

import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import gate_b_installer_v2 as installer


CONTRACT = installer.CONTRACT
SAFE = installer.SAFE
INSTALL_RECEIPT = installer.INSTALL_RECEIPT
POSTCHECK_RECEIPT = SAFE / "postcheck_receipt_v2.json"
ORIGIN = "https://www.uaart.com.ua"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_get(path: str) -> dict:
    separator = "&" if "?" in path else "?"
    url = ORIGIN + path + separator + "task081=%d" % int(time.time())
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ua-art-task081-postcheck-v2/1", "Cache-Control": "no-cache"},
        method="GET",
    )
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=45) as response:
            status = int(response.status)
            final_url = response.geturl()
            body = response.read(6_000_001)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        final_url = exc.geturl()
        body = exc.read(6_000_001)
    installer.require(len(body) <= 6_000_000, "PUBLIC_RESPONSE_TOO_LARGE:" + path)
    return {
        "status": status,
        "final_url": final_url,
        "body": body.decode("utf-8", "replace"),
    }


def exact_path(value: str, expected: str) -> bool:
    return urllib.parse.urlparse(value).path == expected


def run() -> dict:
    value = {
        "contract_id": CONTRACT,
        "mode": "POSTCHECK",
        "status": "BLOCKED",
        "production_write": False,
        "crm_db_write": False,
        "started_at_utc": installer.utc_now(),
        "errors": [],
        "public": {},
    }
    try:
        install = json.loads(installer.read_bytes(INSTALL_RECEIPT, 8_000_000).decode())
        installer.require(install.get("contract_id") == CONTRACT, "INSTALL_CONTRACT")
        installer.require(install.get("status") == "PASS", "INSTALL_NOT_PASS")
        before = install.get("before") or {}
        repaired = before.get("repair_targets") or []
        database = installer.database_snapshot()
        installer.require(database == before.get("database"), "POSTCHECK_DATABASE_CHANGED")
        installer.require(
            installer.code_snapshot() == install.get("candidate_sha256"),
            "POSTCHECK_CODE_CHANGED",
        )
        value["local_public"] = installer.validate_local_public(database, repaired)

        catalog_response = public_get("/video/katalog.html")
        installer.require(catalog_response["status"] == 200, "PUBLIC_CATALOG_STATUS")
        installer.require(
            exact_path(catalog_response["final_url"], "/video/katalog.html"),
            "PUBLIC_CATALOG_REDIRECT",
        )
        catalog = catalog_response.pop("body")
        catalog_counts = {}
        for identifier in re.findall(
            r"href=['\"](?:[^'\"]*/)?(UA-[0-9]{4,})\.html(?:[?#][^'\"]*)?['\"]",
            catalog,
            re.I,
        ):
            identifier = identifier.upper()
            catalog_counts[identifier] = catalog_counts.get(identifier, 0) + 1
        for number in database["published_numbers"]:
            installer.require(
                catalog_counts.get(number, 0) == 1,
                "PUBLIC_CATALOG_HREF:%s:%d" % (number, catalog_counts.get(number, 0)),
            )
        value["public"]["catalog"] = {
            **catalog_response,
            "published_href_counts": {
                number: catalog_counts.get(number, 0)
                for number in database["published_numbers"]
            },
        }

        for number in repaired:
            primary_path = "/video/%s.html" % number
            diag_path = "/video/%s-diag.html" % number
            primary_response = public_get(primary_path)
            diag_response = public_get(diag_path)
            installer.require(primary_response["status"] == 200, "PRIMARY_STATUS:" + number)
            installer.require(diag_response["status"] == 200, "DIAG_STATUS:" + number)
            installer.require(
                exact_path(primary_response["final_url"], primary_path),
                "PRIMARY_REDIRECT:" + number,
            )
            installer.require(
                exact_path(diag_response["final_url"], diag_path),
                "DIAG_REDIRECT:" + number,
            )
            primary = primary_response.pop("body")
            diag = diag_response.pop("body")
            diag_pattern = re.compile(
                r"href=['\"](?:[^'\"]*/)?%s-diag\.html(?:[?#][^'\"]*)?['\"]"
                % re.escape(number),
                re.I,
            )
            installer.require(
                number in primary and len(diag_pattern.findall(primary)) == 1,
                "PRIMARY_ID_OR_DIAG_LINK:" + number,
            )
            installer.require(
                number in diag and "иагност" in diag.lower(),
                "DIAG_IDENTITY:" + number,
            )
            if number == installer.CANARY:
                installer.require(
                    'data-ua-stage-current="2"' in primary
                    or ('data-ua-stage="2"' in primary and "На пароме" in primary),
                    "CANARY_PUBLIC_STAGE",
                )
                marker = 'data-ua-card="%s"' % installer.CANARY
                position = catalog.find(marker)
                window = catalog[max(0, position - 500) : position + 1600]
                installer.require(
                    position >= 0 and 'data-ua-stage="2"' in window,
                    "CANARY_PUBLIC_CATALOG_STAGE",
                )
            value["public"][number] = {
                "primary": {**primary_response, "identity": True, "diag_href_count": 1},
                "diagnostics": {**diag_response, "identity": True},
            }

        value["database"] = database
        value["repaired_numbers"] = repaired
        value["status"] = "PASS"
    except Exception as exc:  # noqa: BLE001
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    value["finished_at_utc"] = installer.utc_now()
    return value


def main() -> int:
    value = run()
    installer.atomic_json(POSTCHECK_RECEIPT, value)
    print(json.dumps({"status": value["status"], "errors": value["errors"]},
                     ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
