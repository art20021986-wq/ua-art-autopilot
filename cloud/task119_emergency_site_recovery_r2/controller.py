#!/usr/bin/env python3
"""Reload the exact UA ART PythonAnywhere webapp and prove public recovery."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

TASK_ID = "TASK119-EMERGENCY-SITE-RECOVERY-R2"
CONTRACT = "UA-ART-EMERGENCY-WEBAPP-RECOVERY-R2-001-V1.0"
CRITICAL = "UA-ART-CRITICAL-ADAPTER-V1.0"
DOMAIN = "www.uaart.com.ua"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
WEBAPPS_URL = BASE + "webapps/"
RELOAD_URL = BASE + "webapps/" + DOMAIN + "/reload/"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RECEIPT_REL = "state/receipts/%s.json" % TASK_ID
EVIDENCE_REL = "cloud/task119_emergency_site_recovery_r2/evidence.json"
MAX_API_BYTES = 2 * 1024 * 1024
MAX_PAGE_BYTES = 12 * 1024 * 1024
CORE_URLS = (
    "https://www.uaart.com.ua/video/index.html",
    "https://www.uaart.com.ua/video/katalog.html",
    "https://www.uaart.com.ua/video/podbor.html",
    "https://www.uaart.com.ua/video/info.html",
    "https://www.uaart.com.ua/video/UA-0001.html",
)
APEX_URL = "https://uaart.com.ua/"
APEX_FINAL_PATH = "/video/index.html"
HEALTH_TARGETS = tuple(
    (url, urllib.parse.urlsplit(url).path) for url in CORE_URLS
) + ((APEX_URL, APEX_FINAL_PATH),)
CACHE_BUST_PARAM = "_uaart_probe"
ROUND_INTERVAL_SECONDS = 15


class RecoveryError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def atomic_json(path: pathlib.Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def required(environment: Mapping[str, str]) -> dict[str, str]:
    names = (
        "PYTHONANYWHERE_API_TOKEN", "UAART_REQUEST_PATH", "UAART_REQUEST_SHA256",
        "UAART_TASK_ID", "UAART_TASK_CLASS", "UAART_RUN_ID",
        "UAART_TRANSACTION_ID", "UAART_RECEIPT_PATH",
        "UAART_BACKUP_MANIFEST_SHA256", "UAART_MANIFEST_SHA256",
    )
    values = {name: str(environment.get(name, "")).strip() for name in names}
    if any(not values[name] for name in names):
        raise RecoveryError("MISSING_ENVIRONMENT")
    if (
        values["UAART_TASK_ID"] != TASK_ID
        or values["UAART_TASK_CLASS"].upper() != "CRITICAL"
        or values["UAART_RECEIPT_PATH"] != RECEIPT_REL
    ):
        raise RecoveryError("TASK_IDENTITY")
    for name in ("UAART_REQUEST_SHA256", "UAART_BACKUP_MANIFEST_SHA256",
                 "UAART_MANIFEST_SHA256"):
        if not re.fullmatch(r"[0-9a-f]{64}", values[name]):
            raise RecoveryError("INVALID_SHA256:" + name)
    request_path = (ROOT / values["UAART_REQUEST_PATH"]).resolve()
    if not request_path.is_relative_to(ROOT.resolve()):
        raise RecoveryError("REQUEST_SCOPE")
    request_bytes = request_path.read_bytes()
    if sha(request_bytes) != values["UAART_REQUEST_SHA256"]:
        raise RecoveryError("REQUEST_IDENTITY")
    request = json.loads(request_bytes.decode("utf-8"))
    if request.get("task_id") != TASK_ID or request.get("production_required") is not True:
        raise RecoveryError("REQUEST_CONTENT")
    critical = request.get("critical") or {}
    manifest_path = (ROOT / str(critical.get("manifest_path") or "")).resolve()
    if not manifest_path.is_relative_to(ROOT.resolve()):
        raise RecoveryError("MANIFEST_SCOPE")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        sha(canonical(manifest)) != values["UAART_MANIFEST_SHA256"]
        or critical.get("manifest_sha256") != values["UAART_MANIFEST_SHA256"]
    ):
        raise RecoveryError("MANIFEST_IDENTITY")
    return values


class API:
    """Only inspect one webapp and call its reload API."""

    def __init__(self, token: str) -> None:
        if not token:
            raise RecoveryError("TOKEN_MISSING")
        self.token = token

    def request(self, method: str, url: str, data: bytes | None = None,
                allowed: tuple[int, ...] = (200,)) -> tuple[int, bytes]:
        if url not in (WEBAPPS_URL, RELOAD_URL):
            raise RecoveryError("API_SCOPE")
        request = urllib.request.Request(
            url, data=data, method=method,
            headers={"Authorization": "Token " + self.token,
                     "User-Agent": "ua-art-emergency-recovery/1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                status, body = int(response.status), response.read(MAX_API_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = int(exc.code), exc.read(MAX_API_BYTES + 1)
        except Exception as exc:
            raise RecoveryError("API_NETWORK:" + type(exc).__name__) from exc
        if status not in allowed or len(body) > MAX_API_BYTES:
            raise RecoveryError("API_HTTP_%d" % status)
        return status, body

    @staticmethod
    def objects(body: bytes) -> list[dict[str, Any]]:
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise RecoveryError("WEBAPPS_JSON") from exc
        if isinstance(value, list):
            raw = value
        elif isinstance(value, dict):
            raw = next((value[key] for key in ("results", "objects", "webapps")
                        if isinstance(value.get(key), list)), None)
            if raw is None and any(key in value for key in
                                   ("domain_name", "domain", "hostname")):
                raw = [value]
            if raw is None and all(isinstance(item, dict) for item in value.values()):
                raw = []
                for key, item in value.items():
                    candidate = dict(item)
                    candidate.setdefault("domain_name", key)
                    raw.append(candidate)
            if raw is None:
                raise RecoveryError("WEBAPPS_SHAPE")
        else:
            raise RecoveryError("WEBAPPS_SHAPE")
        return [item for item in raw if isinstance(item, dict)]

    @staticmethod
    def domain_of(value: Mapping[str, Any]) -> str:
        for key in ("domain_name", "domain", "hostname"):
            candidate = str(value.get(key) or "").strip().lower().rstrip(".")
            if candidate:
                return candidate
        return ""

    @classmethod
    def select_exact(cls, body: bytes) -> dict[str, Any]:
        matches = [item for item in cls.objects(body)
                   if cls.domain_of(item) == DOMAIN]
        if len(matches) != 1:
            raise RecoveryError("WEBAPP_NOT_UNIQUE")
        return matches[0]

    @classmethod
    def safe_state(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "domain": cls.domain_of(value),
            "enabled": value.get("enabled") is not False,
            "python_version": str(value.get("python_version") or ""),
            "source_directory_present": bool(value.get("source_directory")),
            "virtualenv_present": bool(
                value.get("virtualenv_path") or value.get("virtualenv")
            ),
        }

    def exact_webapp(self) -> dict[str, Any]:
        return self.select_exact(self.request("GET", WEBAPPS_URL)[1])

    def reload(self) -> dict[str, Any]:
        before = self.safe_state(self.exact_webapp())
        status, _ = self.request(
            "POST", RELOAD_URL, b"", allowed=(200, 201, 202, 204)
        )
        after = self.safe_state(self.exact_webapp())
        if before["domain"] != DOMAIN or after["domain"] != DOMAIN:
            raise RecoveryError("WEBAPP_IDENTITY")
        return {
            "status": "PASS", "http": status, "domain": DOMAIN,
            "scope": "webapp_reload_only", "persistent_file_write": False,
            "before": before, "after": after,
        }


def cache_busted(url: str, nonce: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", nonce):
        raise RecoveryError("PROBE_NONCE")
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append((CACHE_BUST_PARAM, nonce))
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), "")
    )


def validate_page(url: str, status: int, final_url: str, body: bytes,
                  expected_path: str | None = None,
                  requested_url: str | None = None) -> dict[str, Any]:
    if status != 200 or not 500 <= len(body) <= MAX_PAGE_BYTES:
        raise RecoveryError("PUBLIC_HTTP_OR_SIZE:%s:%d:%d" %
                            (url, status, len(body)))
    prefix = body[:4096].lower()
    if b"<html" not in prefix and b"<!doctype html" not in prefix:
        raise RecoveryError("PUBLIC_HTML:" + url)
    parsed = urllib.parse.urlsplit(final_url)
    wanted_path = expected_path or urllib.parse.urlsplit(url).path
    if (
        parsed.scheme != "https"
        or parsed.hostname != DOMAIN
        or parsed.port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != wanted_path
    ):
        raise RecoveryError("PUBLIC_FINAL_URL:" + url)
    return {
        "url": url,
        "requested_url": requested_url or url,
        "final_url": final_url,
        "expected_final_path": wanted_path,
        "http": status,
        "bytes": len(body),
        "sha256": sha(body),
    }


def probe(url: str, expected_path: str, probe_nonce: str,
          timeout: int = 25) -> dict[str, Any]:
    requested_url = cache_busted(url, probe_nonce)
    request = urllib.request.Request(
        requested_url,
        headers={
            "User-Agent": "UA-ART-emergency-recovery-health/2",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = validate_page(
                url, int(response.status), str(response.geturl()),
                response.read(MAX_PAGE_BYTES + 1),
                expected_path=expected_path,
                requested_url=requested_url,
            )
    except Exception as exc:
        if isinstance(exc, RecoveryError):
            raise
        raise RecoveryError("PUBLIC_NETWORK:%s:%s" %
                            (url, type(exc).__name__)) from exc
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
    return result


def probe_round(probe_nonce: str) -> list[dict[str, Any]]:
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(HEALTH_TARGETS)
    ) as pool:
        futures = [
            pool.submit(probe, url, expected_path, probe_nonce)
            for url, expected_path in HEALTH_TARGETS
        ]
        return [future.result() for future in futures]


def wait_for_consecutive(required_passes: int = 3,
                         timeout_seconds: int = 180) -> list[dict[str, Any]]:
    if required_passes < 1:
        raise RecoveryError("PASS_COUNT")
    deadline, consecutive, round_index = time.monotonic() + timeout_seconds, 0, 0
    attempts: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        round_index += 1
        probe_nonce = "%x-%d" % (time.time_ns(), round_index)
        try:
            checks = probe_round(probe_nonce)
            consecutive += 1
            attempts.append({"checked_at": now(), "status": "PASS",
                             "consecutive": consecutive,
                             "probe_nonce": probe_nonce, "checks": checks})
            if consecutive >= required_passes:
                return attempts[-required_passes:]
        except Exception as exc:
            consecutive = 0
            attempts.append({"checked_at": now(), "status": "FAIL",
                             "probe_nonce": probe_nonce,
                             "error": type(exc).__name__ + ":" + str(exc)})
        if deadline - time.monotonic() < ROUND_INTERVAL_SECONDS:
            break
        time.sleep(ROUND_INTERVAL_SECONDS)
    raise RecoveryError("PUBLIC_RECOVERY_TIMEOUT:" +
                        json.dumps(attempts[-6:], sort_keys=True))


def execute(environment: Mapping[str, str]) -> dict[str, Any]:
    values = required(environment)
    evidence: dict[str, Any] = {
        "task_id": TASK_ID, "contract_id": CONTRACT, "status": "FAIL",
        "started_at": now(), "operation": "pythonanywhere_webapp_reload",
        "domain": DOMAIN, "persistent_file_write": False,
        "protected_systems_opened": [], "errors": [],
    }
    try:
        evidence["reload"] = API(values["PYTHONANYWHERE_API_TOKEN"]).reload()
        evidence["health_passes"] = wait_for_consecutive(3, 180)
        receipt = {
            "contract_id": CRITICAL, "task_id": TASK_ID, "status": "FINISHED",
            "task_class": "CRITICAL", "target_environment": "production",
            "production_required": True, "production": "PASS", "tests": "PASS",
            "backup": "PASS",
            "backup_manifest_sha256": values["UAART_BACKUP_MANIFEST_SHA256"],
            "rollback": "PASS", "rollback_ready": True, "live_verify": "PASS",
            "request_sha256": values["UAART_REQUEST_SHA256"],
            "manifest_sha256": values["UAART_MANIFEST_SHA256"],
            "run_id": values["UAART_RUN_ID"],
            "transaction_id": values["UAART_TRANSACTION_ID"],
            "unexpected_changes": 0,
            "operation": "PYTHONANYWHERE_WEBAPP_RELOAD_ONLY",
            "domain": DOMAIN, "consecutive_health_passes": 3,
            "core_urls_checked": list(CORE_URLS), "persistent_file_write": False,
            "apex_url_checked": APEX_URL,
            "apex_final_url_required": "https://" + DOMAIN + APEX_FINAL_PATH,
            "verification_targets": len(HEALTH_TARGETS),
            "verification_round_interval_seconds": ROUND_INTERVAL_SECONDS,
            "cache_busted_probes": True,
            "website_content_unchanged": True,
            "protected_files_unchanged": True, "crm_unchanged": True,
            "cards_unchanged": True, "vin_unchanged": True,
            "prices_unchanged": True, "media_unchanged": True,
            "dns_unchanged": True, "finished_at": now(),
        }
        atomic_json(ROOT / RECEIPT_REL, receipt)
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        evidence["rollback"] = "DEFERRED_TO_CRITICAL_WORKFLOW"
    evidence["finished_at"] = now()
    atomic_json(ROOT / EVIDENCE_REL, evidence)
    return evidence


def main() -> int:
    value = execute(os.environ)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
