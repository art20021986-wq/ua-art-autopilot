#!/usr/bin/env python3
"""Read-only local and public verification for TASK 073 V5."""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

import gate_b_installer_v5 as installer


BASE_URL = "https://www.uaart.com.ua/video"
RECEIPT = installer.SAFE / "postcheck_receipt_v5.json"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_exact(url: str) -> dict:
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(
        url, headers={"User-Agent": "ua-art-task073-postcheck-v5/1"}
    )
    try:
        with opener.open(request, timeout=30) as response:
            body = response.read(2_000_001)
            status = response.status
            final_url = response.geturl()
    except urllib.error.HTTPError as exc:
        body = exc.read(2_000_001)
        status = exc.code
        final_url = exc.geturl()
    if len(body) > 2_000_000:
        raise RuntimeError("PUBLIC_BODY_TOO_LARGE:" + url)
    return {
        "url": url,
        "status": status,
        "final_url": final_url,
        "redirected": final_url != url or status in (301, 302, 303, 307, 308),
        "body": body.decode("utf-8", "replace"),
        "sha256": hashlib.sha256(body).hexdigest(),
        "size": len(body),
    }


def public_checks() -> dict:
    urls = {
        "primary": BASE_URL + "/UA-0011.html",
        "diag": BASE_URL + "/UA-0011-diag.html",
        "catalog": BASE_URL + "/katalog.html",
    }
    values = {name: fetch_exact(url) for name, url in urls.items()}
    href = re.compile(r"href=['\"]UA\-0011\.html(?:[?#][^'\"]*)?['\"]")
    diag_href = re.compile(r"href=['\"]UA\-0011\-diag\.html(?:[?#][^'\"]*)?['\"]")
    primary = values["primary"]
    diag = values["diag"]
    catalog = values["catalog"]
    checks = {
        "primary_exact_200": primary["status"] == 200 and not primary["redirected"],
        "primary_identity": "UA-0011" in primary["body"],
        "primary_diag_cta_once": len(diag_href.findall(primary["body"])) == 1,
        "diag_exact_200": diag["status"] == 200 and not diag["redirected"],
        "diag_identity": "UA-0011" in diag["body"],
        "diag_semantic": "иагност" in diag["body"].lower(),
        "catalog_exact_200": catalog["status"] == 200 and not catalog["redirected"],
        "catalog_href_once": len(href.findall(catalog["body"])) == 1,
    }
    for value in values.values():
        value.pop("body", None)
    return {"pages": values, "checks": checks}


def run() -> dict:
    value = {
        "contract_id": installer.CONTRACT,
        "mode": "POSTCHECK",
        "status": "BLOCKED",
        "production_write": False,
        "crm_db_write": False,
        "runtime_llm_tokens": 0,
        "errors": [],
    }
    try:
        install_receipt = json.loads(
            installer.read_bytes(installer.INSTALL_RECEIPT, 8_000_000).decode()
        )
        installer.require(install_receipt.get("status") == "PASS", "INSTALL_NOT_PASS")
        before = install_receipt["before"]
        current = installer.full_snapshot()
        installer.require(current["database"] == before["database"], "POSTCHECK_DATABASE")
        installer.require(
            current["protected_pages_sha256"] == before["protected_pages_sha256"],
            "POSTCHECK_PROTECTED",
        )
        installer.require(
            current["code_sha256"] == install_receipt["candidate_sha256"],
            "POSTCHECK_CODE",
        )
        value["local_public"] = installer.validate_local_public()
        value["database"] = current["database"]
        value["protected_pages_count"] = len(current["protected_pages_sha256"])
        value["public"] = public_checks()
        failed = sorted(
            name for name, passed in value["public"]["checks"].items() if not passed
        )
        installer.require(not failed, "PUBLIC_CHECKS:" + ",".join(failed))
        value["status"] = "PASS"
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    return value


def main() -> int:
    value = run()
    installer.atomic_json(RECEIPT, value)
    print(json.dumps({"status": value["status"], "errors": value["errors"]},
                     ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
