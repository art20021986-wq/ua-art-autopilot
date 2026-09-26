#!/usr/bin/env python3
"""Read-only probe: how card pages are served and whether their price matches CRM.

Only GET requests. Writes local evidence files only; nothing on the account,
site, CRM, cards or media changes.
"""
from __future__ import annotations

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

import probe

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
TASK_ID = "PRICE-LIVE-PROBE-20260926"
RECEIPT_REL = "state/receipts/%s.json" % TASK_ID
API = "https://www.pythonanywhere.com/api/v0/user/Carix/"
SITE = "https://www.uaart.com.ua"
DOMAIN = "www.uaart.com.ua"
WSGI = "/var/www/www_uaart_com_ua_wsgi.py"
MAX_BYTES = 8 * 1024 * 1024
SOURCE_PATTERNS = (
    r"\bvideo\b", r"\.html", r"send_file|send_from_directory|static", r"route\(",
    r"Cache-Control|max-age|ETag|Last-Modified", r"^\s*(from|import)\s", r"application\s*=",
    r"UA-", r"katalog", r"write_text|write_bytes|open\(",
)


class ProbeError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def atomic_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def required(environment: Mapping[str, str]) -> dict[str, str]:
    names = (
        "PYTHONANYWHERE_API_TOKEN", "UAART_REQUEST_PATH", "UAART_REQUEST_SHA256",
        "UAART_TASK_ID", "UAART_TASK_CLASS", "UAART_RUN_ID", "UAART_RECEIPT_PATH",
    )
    values = {name: str(environment.get(name, "")).strip() for name in names}
    missing = [name for name in names if not values[name]]
    if missing:
        raise ProbeError("MISSING_ENV:" + ",".join(missing))
    if values["UAART_TASK_ID"] != TASK_ID or values["UAART_TASK_CLASS"].upper() != "STANDARD":
        raise ProbeError("TASK_IDENTITY")
    if values["UAART_RECEIPT_PATH"] != RECEIPT_REL:
        raise ProbeError("RECEIPT_IDENTITY")
    request = ROOT / values["UAART_REQUEST_PATH"]
    if sha(request.read_bytes()) != values["UAART_REQUEST_SHA256"]:
        raise ProbeError("REQUEST_SHA")
    return values


def get(url: str, token: str = "", method: str = "GET") -> tuple[int, Any, bytes, float]:
    headers = {"User-Agent": "UA-ART-price-probe/1 (read-only)", "Cache-Control": "no-cache"}
    if token:
        headers["Authorization"] = "Token " + token
    request = urllib.request.Request(url, headers=headers, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status, response_headers, body = response.status, response.headers, response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        status, response_headers, body = error.code, error.headers, error.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ProbeError("RESPONSE_TOO_LARGE:" + url)
    return int(status), response_headers, body, round((time.monotonic() - started) * 1000, 1)


def api_json(token: str, relative: str) -> Any:
    status, _, body, _ = get(API + relative, token)
    if status != 200:
        return {"http_status": status}
    return json.loads(body.decode("utf-8"))


def api_file(token: str, path: str) -> str | None:
    status, _, body, _ = get(API + "files/path" + urllib.parse.quote(path, safe="/"), token)
    return body.decode("utf-8", "replace") if status == 200 else None


def attempt(result: dict, key: str, function, *args) -> Any:
    try:
        value = function(*args)
        result[key] = value
        return value
    except Exception as error:  # evidence records the failure, the probe goes on
        result[key] = {"error": type(error).__name__ + ":" + str(error)[:200]}
        return None


def serving(token: str) -> dict:
    out: dict[str, Any] = {}
    webapps = attempt(out, "webapps", api_json, token, "webapps/")
    if isinstance(webapps, list):
        out["webapps"] = [{key: app.get(key) for key in (
            "domain_name", "python_version", "source_directory", "working_directory",
            "virtualenv_path", "force_https", "enabled")} for app in webapps]
    attempt(out, "static_files", api_json, token, "webapps/%s/static_files/" % DOMAIN)
    wsgi = attempt(out, "wsgi_raw", api_file, token, WSGI)
    out.pop("wsgi_raw", None)
    modules = {}
    if isinstance(wsgi, str):
        out["wsgi"] = {"sha256": sha(wsgi.encode()), "lines": probe.redact_lines(wsgi, SOURCE_PATTERNS, 120)}
        for name in sorted(set(re.findall(r"^\s*from\s+(\w+)\s+import", wsgi, re.M))):
            source = api_file(token, "/home/Carix/%s.py" % name)
            if source is not None:
                modules[name] = {"sha256": sha(source.encode()), "bytes": len(source),
                                 "lines": probe.redact_lines(source, SOURCE_PATTERNS, 120)}
    out["wsgi_modules"] = modules
    listing = attempt(out, "video_listing_raw", api_json, token, "files/path/home/Carix/video/")
    out.pop("video_listing_raw", None)
    if isinstance(listing, dict) and "http_status" not in listing:
        out["video_listing"] = probe.listing_summary(listing)
    home = attempt(out, "home_listing_raw", api_json, token, "files/path/home/Carix/")
    out.pop("home_listing_raw", None)
    generators = {}
    if isinstance(home, dict) and "http_status" not in home:
        out["home_listing"] = probe.listing_summary(home)
        for name in sorted(home)[:120]:
            if not name.endswith(".py") or home[name].get("type") != "file":
                continue
            source = api_file(token, "/home/Carix/" + name)
            if source and len(source) < 600_000 and re.search(r"katalog\.html|UA-%s|\.html", source):
                generators[name] = {"sha256": sha(source.encode()), "bytes": len(source),
                                    "lines": probe.redact_lines(source, (r"\.html", r"katalog", r"cena|price", r"def "), 80)}
    out["html_writers"] = generators
    return out


def public(pages_out: dict) -> dict:
    out: dict[str, Any] = {}
    status, headers, body, latency = get(SITE + "/ua-art-public-prices-v1.json")
    if status != 200:
        raise ProbeError("PRICES_HTTP_%d" % status)
    data = json.loads(body.decode("utf-8"))
    pages_out["ua-art-public-prices-v1.json"] = data
    crm = probe.crm_prices(data)
    out["prices_endpoint"] = {"http": status, "ms": latency, "headers": probe.headers_subset(headers), "cars": crm}
    checks, comparisons = {}, []
    for code in ["katalog"] + sorted(crm):
        path = "/video/%s.html" % code
        status, headers, raw, latency = get(SITE + path)
        text = raw.decode("utf-8", "replace")
        pages_out[path] = text
        structure = probe.page_structure(text)
        checks[path] = {"http": status, "ms": latency, "sha256": sha(raw),
                        "headers": probe.headers_subset(headers),
                        **{k: v for k, v in structure.items() if k != "excerpts"}}
        if code != "katalog":
            comparisons.append(probe.compare(code, crm[code], structure))
    out["pages"] = checks
    out["comparisons"] = comparisons
    out["mismatches"] = [c["code"] for c in comparisons if not c["static_matches_crm"]]
    for label, path, method in (("script", "/video/ua-site-languages.js", "GET"),
                                ("missing_html", "/video/UA-9999.html", "GET"),
                                ("root", "/", "HEAD")):
        status, headers, raw, latency = get(SITE + path, method=method)
        out[label] = {"path": path, "http": status, "ms": latency, "headers": probe.headers_subset(headers),
                      "sha256": sha(raw), "head": raw[:300].decode("utf-8", "replace") if label == "missing_html" else "",
                      "fetches_prices": b"ua-art-public-prices-v1.json" in raw}
    return out


def execute(environment: Mapping[str, str]) -> dict[str, Any]:
    values = required(environment)
    pages: dict[str, Any] = {}
    evidence = {"task_id": TASK_ID, "measured_at": now(), "read_only": True}
    evidence["serving"] = serving(values["PYTHONANYWHERE_API_TOKEN"])
    evidence["public"] = public(pages)
    probe_evidence = HERE / "evidence.json"
    atomic_text(probe_evidence, probe.dumps(evidence))
    atomic_text(HERE / "pages.json", probe.dumps(pages))
    receipt = {
        "task_id": TASK_ID, "status": "FINISHED", "task_class": "STANDARD",
        "target_environment": "production_read_only", "tests": "PASS", "unexpected_changes": 0,
        "production_required": False, "read_only": True, "production_touched": False,
        "site_touched": False, "crm_vehicle_data_touched": False, "media_touched": False,
        "request_sha256": values["UAART_REQUEST_SHA256"], "run_id": values["UAART_RUN_ID"],
        "mismatches": evidence["public"]["mismatches"], "finished_at": now(),
    }
    atomic_text(ROOT / RECEIPT_REL, probe.dumps(receipt))
    return receipt


def main() -> int:
    try:
        value = execute(os.environ)
    except Exception as exc:
        value = {"task_id": TASK_ID, "status": "FAILED", "task_class": "STANDARD",
                 "production_required": False, "production_touched": False, "unexpected_changes": 0,
                 "error": type(exc).__name__ + ":" + str(exc)[:300], "finished_at": now()}
        atomic_text(ROOT / RECEIPT_REL, probe.dumps(value))
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
