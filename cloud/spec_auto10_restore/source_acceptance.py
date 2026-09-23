#!/usr/bin/env python3
"""Bounded, read-only acceptance of the ten approved source adapters.

Default: validate the exact plan and print NOT_RUN without opening the network.
--network is an execution switch, not a grant of network permission. The caller
must use an already authorized environment; do not change routes on denial.
No application imports, CRM reads, report writes, retries or discovery engines.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import signal
import socket
import ssl
import sys
import time
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCHEMA = "UA-ART-SOURCE10-ACCEPTANCE-1"
MAX_BODY = 2_000_000
MAX_PLAN = 100_000
PER_REQUEST_SECONDS = 8
TOTAL_SECONDS = 90
MAX_REDIRECTS = 2
RUNTIME_FILES = ("profile_library.py", "source_policy.py")


class AcceptanceError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PLAN:
        raise AcceptanceError("INPUT_NOT_BOUNDED_REGULAR_FILE")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise AcceptanceError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise AcceptanceError("INVALID_JSON") from None


def load_runtime(directory, expected):
    directory = Path(directory).resolve(strict=True)
    if set(expected) != set(RUNTIME_FILES):
        raise AcceptanceError("RUNTIME_MANIFEST_INVALID")
    captured = {}
    for name in RUNTIME_FILES:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise AcceptanceError("RUNTIME_HASH_MISMATCH:" + name)
        raw = path.read_bytes()
        if sha(raw) != expected[name]:
            raise AcceptanceError("RUNTIME_HASH_MISMATCH:" + name)
        captured[name] = raw
    # Only the two hash-pinned pure modules are loaded; no production modules.
    sys.dont_write_bytecode = True
    for name in RUNTIME_FILES:
        module_name = Path(name).stem
        module = types.ModuleType(module_name)
        module.__file__ = str(directory / name)
        sys.modules[module_name] = module
        # Execute the bytes whose hash was checked, never re-open between
        # validation and execution (a replaced file must not enter this run).
        exec(compile(captured[name], str(directory / name), "exec"), module.__dict__)
    return sys.modules["source_policy"]


def validate_plan(plan, policy):
    if not isinstance(plan, dict) or set(plan) != {
        "schema", "runtime_sha256", "sources", "limits", "scope"
    } or plan["schema"] != SCHEMA:
        raise AcceptanceError("PLAN_SCHEMA_INVALID")
    if plan["scope"] != "READ_ONLY_SOURCE_ADAPTERS_NO_CRM_NO_PUBLICATION":
        raise AcceptanceError("PLAN_SCOPE_INVALID")
    if plan["limits"] != {
        "request_seconds": PER_REQUEST_SECONDS, "total_seconds": TOTAL_SECONDS,
        "max_response_bytes": MAX_BODY, "max_redirects_per_source": MAX_REDIRECTS,
        "retries": 0, "max_sources": 10
    }:
        raise AcceptanceError("PLAN_LIMITS_INVALID")
    sources = plan["sources"]
    if not isinstance(sources, list) or len(sources) != 10:
        raise AcceptanceError("SOURCE_COUNT_INVALID")
    if not all(isinstance(item, dict) for item in sources) or [item.get("domain") for item in sources] != list(policy.SOURCE_DOMAINS):
        raise AcceptanceError("ORIGINAL_TEN_SOURCE_ORDER_REQUIRED")
    for item in sources:
        if set(item) != {"domain", "url", "mode", "control", "control_review"}:
            raise AcceptanceError("SOURCE_SCHEMA_INVALID")
        url = item["url"]
        try:
            parsed = urllib.parse.urlsplit(url)
            port = parsed.port
        except (TypeError, ValueError):
            raise AcceptanceError("SOURCE_URL_INVALID") from None
        if (policy.source_domain(url) != item["domain"] or port not in (None, 443)
                or parsed.fragment or len(url) > 2048):
            raise AcceptanceError("SOURCE_URL_INVALID")
        mode = item["mode"]
        if item["domain"] == "vpic.nhtsa.dot.gov":
            if mode == "api_schema":
                if url != "https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMake/kia?format=json" or item["control"]:
                    raise AcceptanceError("VPIC_SCHEMA_REQUEST_INVALID")
            elif mode == "vin_decode":
                control = item["control"]
                if url != "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/" or not isinstance(control, dict) or set(control) != {"vin_sha256", "car"}:
                    raise AcceptanceError("VPIC_CONTROL_INVALID")
                if not re.fullmatch(r"[0-9a-f]{64}", str(control["vin_sha256"])):
                    raise AcceptanceError("VPIC_CONTROL_INVALID")
                validate_car(control["car"])
                if not valid_review(item["control_review"]):
                    raise AcceptanceError("VPIC_CONTROL_REVIEW_REQUIRED")
            else:
                raise AcceptanceError("VPIC_MODE_INVALID")
        elif mode == "inspect_identity":
            if item["control"] or item["control_review"]:
                raise AcceptanceError("UNREVIEWED_INSPECTION_MUST_NOT_CLAIM_IDENTITY")
        elif mode == "model_adapter":
            validate_car(item["control"])
            if not valid_review(item["control_review"]):
                raise AcceptanceError("MODEL_CONTROL_REVIEW_REQUIRED")
        else:
            raise AcceptanceError("SOURCE_MODE_INVALID")
        # VINs must never be embedded into public model-page requests or plans.
        if re.search(r"(?<![A-HJ-NPR-Z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-HJ-NPR-Z0-9])", urllib.parse.unquote(url), re.I):
            raise AcceptanceError("VIN_IN_PUBLIC_URL")


def valid_review(value):
    return (isinstance(value, dict) and set(value) == {"reference", "sha256"}
            and isinstance(value["reference"], str) and 1 <= len(value["reference"]) <= 300
            and bool(re.fullmatch(r"[0-9a-f]{64}", str(value["sha256"]))))


def validate_car(car):
    if not isinstance(car, dict) or set(car) != {"brand", "model", "year", "fuel", "engine_cc"}:
        raise AcceptanceError("CONTROL_IDENTITY_INVALID")
    if not all(isinstance(car[key], str) and 1 <= len(car[key]) <= 100 for key in ("brand", "model", "year", "fuel")):
        raise AcceptanceError("CONTROL_IDENTITY_INVALID")
    if not re.fullmatch(r"(?:19|20)\d{2}", car["year"]) or type(car["engine_cc"]) is not int or not 100 <= car["engine_cc"] <= 10000:
        raise AcceptanceError("CONTROL_IDENTITY_INVALID")


def transport_reason(exc):
    """Safe categories only; exception messages may contain URLs or secrets."""
    value = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(value, (TimeoutError, socket.timeout)):
        return "TIMEOUT"
    if isinstance(value, ssl.SSLError):
        return "TLS"
    if isinstance(value, socket.gaierror):
        return "DNS"
    if isinstance(value, PermissionError):
        return "ACCESS_DENIED"
    return "TRANSPORT_UNAVAILABLE"


class DomainRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, policy, domain):
        super().__init__()
        self.policy, self.domain, self.count = policy, domain, 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        parsed = urllib.parse.urlsplit(newurl)
        if self.count > MAX_REDIRECTS or self.policy.source_domain(newurl) != self.domain or parsed.port not in (None, 443):
            raise AcceptanceError("REDIRECT_NOT_ALLOWED")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def request_body(policy, item, url, opener=None):
    fetch = opener or urllib.request.build_opener(DomainRedirects(policy, item["domain"])).open
    request = urllib.request.Request(url, method="GET", headers={
        "User-Agent": "UAART-Source-Acceptance/1.0", "Accept-Language": "en,ko;q=0.9,ru;q=0.8"
    })
    with fetch(request, timeout=PER_REQUEST_SECONDS) as response:
        status = int(response.status)
        final = str(response.geturl())
        parsed = urllib.parse.urlsplit(final)
        if policy.source_domain(final) != item["domain"] or parsed.port not in (None, 443):
            raise AcceptanceError("REDIRECT_NOT_ALLOWED")
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise AcceptanceError("RESPONSE_TOO_LARGE")
        if status != 200:
            raise AcceptanceError("HTTP_" + str(status))
        return body, status, final


def evaluate_body(policy, item, body, private_vin=None):
    mode = item["mode"]
    if mode == "inspect_identity":
        lines, rows = policy.parse_html(body)
        return {"adapter": "NOT_VERIFIED", "identity": "CONTROL_REVIEW_REQUIRED",
                "visible_text_sample": " ".join(lines)[:2000], "table_row_count": len(rows),
                "field_count": 0}
    if mode == "api_schema":
        payload = json.loads(body.decode("utf-8"))
        rows = payload.get("Results") if isinstance(payload, dict) else None
        valid = isinstance(rows, list) and any(isinstance(row, dict) and
            policy._norm(row.get("Make_Name")) == "kia" and policy._clean(row.get("Model_Name")) for row in rows)
        return {"adapter": "API_SCHEMA_ONLY" if valid else "FAIL_SCHEMA",
                "identity": "VIN_NOT_TESTED", "field_count": 0}
    if mode == "vin_decode":
        payload = json.loads(body.decode("utf-8"))
        rows = payload.get("Results") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            return {"adapter": "FAIL_SCHEMA", "identity": "NOT_VERIFIED", "field_count": 0}
        row = rows[0]
        car = dict(item["control"]["car"], vin=private_vin)
        exact = policy.normalize_vin(row.get("VIN")) == private_vin
        identity_ok = exact and policy.vpic_identity_matches(car, row)
        # Use the exact candidate decoder with an in-memory copy of this response.
        import io
        class CapturedResponse(io.BytesIO):
            status = 200
            def geturl(self):
                return "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"
        _, facts = policy.decode_vpic(car, opener=lambda request, **kwargs: CapturedResponse(body))
        clean = policy.deduplicate(facts) if identity_ok else []
        return {"adapter": "PASS" if identity_ok and clean else "FAIL_IDENTITY_OR_FACTS",
                "identity": "EXACT_VIN_MAKE_MODEL_YEAR" if identity_ok else "MISMATCH",
                "field_count": len(clean), "fields": sorted(f["field_key"] for f in clean)}
    score, facts = policy.extract_page_facts(item["control"], item["url"], body)
    clean = policy.deduplicate(facts)
    return {"adapter": "PASS" if len(clean) >= 4 else "FAIL_CONTENT_OR_IDENTITY",
            "identity": "MODEL_CONTEXT_MATCH" if clean else "NOT_VERIFIED", "match_score": score,
            "field_count": len(clean), "fields": sorted(f["field_key"] for f in clean)}


def run(plan, policy, *, network=False, origin="offline", authorization_ref="", private_vin=None, opener=None):
    validate_plan(plan, policy)
    vin_items = [i for i in plan["sources"] if i["mode"] == "vin_decode"]
    if vin_items:
        if not isinstance(private_vin, str) or not private_vin or policy.normalize_vin(private_vin) != private_vin or sha(private_vin.encode()) != vin_items[0]["control"]["vin_sha256"]:
            raise AcceptanceError("EXACT_APPROVED_VIN_REQUIRED")
    elif private_vin is not None:
        raise AcceptanceError("UNREQUESTED_VIN_INPUT")
    if network and (not authorization_ref.strip() or not origin.strip() or origin == "offline"):
        raise AcceptanceError("AUTHORIZED_EXECUTION_CONTEXT_REQUIRED")
    report = {"schema": SCHEMA, "plan_sha256": sha(canonical(plan)), "started_at": utc(),
              "execution_origin": origin, "authorization_reference": authorization_ref,
              "runtime_sha256": plan["runtime_sha256"], "network_requested": network,
              "vin_request_attempted": False, "vin_transmitted": False,
              "production_touched": False, "sources": [],
              "network_calls_started": 0, "gate_b": "NOT_EVALUATED"}
    stopped = "NETWORK_NOT_REQUESTED" if not network else ""
    deadline = time.monotonic() + TOTAL_SECONDS
    for item in plan["sources"]:
        entry = {"domain": item["domain"], "probe_url": item["url"], "mode": item["mode"],
                 "access": "NOT_RUN", "adapter": "NOT_RUN", "identity": "NOT_VERIFIED"}
        report["sources"].append(entry)
        if not stopped and time.monotonic() >= deadline:
            stopped = "TOTAL_TIME_BUDGET_EXHAUSTED"
        if stopped:
            entry["reason"] = stopped
            continue
        started = time.monotonic()
        try:
            url = item["url"]
            if item["mode"] == "vin_decode":
                url += private_vin + "?" + urllib.parse.urlencode({"format": "json", "modelyear": item["control"]["car"]["year"]})
                report["vin_request_attempted"] = True
            report["network_calls_started"] += 1
            body, status, final = request_body(policy, item, url, opener)
            if item["mode"] == "vin_decode":
                report["vin_transmitted"] = True
            entry.update({"access": "HTTP_RESPONSE", "http_status": status, "response_sha256": sha(body),
                          "response_bytes": len(body), "retrieved_at": utc(),
                          "final_url": item["url"] if item["mode"] == "vin_decode" else final})
            entry.update(evaluate_body(policy, item, body, private_vin))
        except urllib.error.HTTPError as exc:
            if item["mode"] == "vin_decode":
                report["vin_transmitted"] = True
            entry.update({"access": "HTTP_RESPONSE", "http_status": exc.code, "adapter": "NOT_VERIFIED"})
            if exc.code == 429:
                entry["retry_after_seconds"] = policy._retry_after_seconds(exc.headers)
        except (urllib.error.URLError, OSError) as exc:
            stopped = transport_reason(exc)
            if item["mode"] == "vin_decode":
                report["vin_transmitted"] = "UNKNOWN_AFTER_TRANSPORT_ERROR"
            entry.update({"access": "TRANSPORT_UNAVAILABLE", "reason": stopped})
        except AcceptanceError as exc:
            entry.update({"adapter": "NOT_VERIFIED", "reason": str(exc)})
        except (ValueError, KeyError, TypeError, policy.SourcePolicyError):
            entry.update({"adapter": "FAIL_SCHEMA_OR_IDENTITY", "reason": "RESPONSE_REJECTED"})
        entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report.update({"finished_at": utc(), "stop_reason": stopped,
                   "adapter_pass_count": sum(i["adapter"] == "PASS" for i in report["sources"]),
                   "source_count": len(report["sources"]),
                   "sources_with_http_response": sum(i["access"] == "HTTP_RESPONSE" for i in report["sources"])})
    report["all_ten_adapters_pass"] = report["adapter_pass_count"] == 10
    report["probe_execution_complete"] = bool(network and not stopped and report["network_calls_started"] == 10)
    report["limitations"] = ["Model pages do not prove factory options of an individual VIN.",
        "This read-only run cannot erase last-good CRM facts and does not test production preservation.",
        "A source-level failure is retained explicitly; API_SCHEMA_ONLY is never adapter PASS.",
        "The plan and authorization reference do not bypass environment network permissions."]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--network", action="store_true")
    parser.add_argument("--execution-origin", default="offline")
    parser.add_argument("--authorization-ref", default="")
    parser.add_argument("--private-vin-input", help="Private JSON with only the pre-approved VIN; never printed")
    args = parser.parse_args()
    try:
        plan = read_json(args.plan)
        if not isinstance(plan, dict):
            raise AcceptanceError("PLAN_SCHEMA_INVALID")
        if sha(canonical(plan)) != args.plan_sha256:
            raise AcceptanceError("PLAN_HASH_MISMATCH")
        policy = load_runtime(args.runtime, plan.get("runtime_sha256", {}))
        private_vin = None
        if args.private_vin_input:
            vin_input = read_json(args.private_vin_input)
            if not isinstance(vin_input, dict) or set(vin_input) != {"vin"}:
                raise AcceptanceError("PRIVATE_VIN_INPUT_INVALID")
            private_vin = vin_input["vin"]
        # A hard process deadline also bounds a server that drip-feeds bytes.
        def expired(signum, frame):
            raise TimeoutError("SOURCE_ACCEPTANCE_TOTAL_DEADLINE")
        if args.network:
            signal.signal(signal.SIGALRM, expired)
            signal.setitimer(signal.ITIMER_REAL, TOTAL_SECONDS)
        try:
            report = run(plan, policy, network=args.network, origin=args.execution_origin,
                         authorization_ref=args.authorization_ref, private_vin=private_vin)
        finally:
            if args.network:
                signal.setitimer(signal.ITIMER_REAL, 0)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not args.network or report["all_ten_adapters_pass"] else 2
    except AcceptanceError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "REFUSED_INVALID_INPUT_OR_RUNTIME",
                          "reason": str(exc), "production_touched": False}))
        return 3
    except (OSError, ValueError, TypeError):
        # Never expose exception payloads; they may include a private request.
        print(json.dumps({"schema": SCHEMA, "status": "REFUSED_INVALID_INPUT_OR_RUNTIME", "production_touched": False}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
