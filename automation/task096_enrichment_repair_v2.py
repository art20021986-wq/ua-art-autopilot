#!/usr/bin/env python3
"""TASK096 v2 repair: real source expansion + semantic dedup, sandbox only."""
from __future__ import annotations

import json
import os
import pathlib
import re
import urllib.error
import urllib.request

import task096_data_enrichment_controller as ctl

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLEANUP = ROOT / "cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_semantic_cleanup.py"


def _api_call(payload: dict) -> dict:
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        raise ctl.ControllerError("ANTHROPIC_API_KEY_MISSING")
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "user-agent": "ua-art-task096-repair-v2/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=210) as response:
            return json.loads(response.read(4_000_000).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise ctl.ControllerError("ANTHROPIC_WEB_SEARCH_HTTP_%d:%s" % (exc.code, detail[:300])) from exc
    except Exception as exc:
        raise ctl.ControllerError("ANTHROPIC_WEB_SEARCH_NETWORK:" + type(exc).__name__) from exc


def _result_urls(content: list[dict]) -> set[str]:
    urls: set[str] = set()
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "web_search_tool_result":
            items = block.get("content")
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict) and item.get("type") == "web_search_result":
                        url = str(item.get("url") or "")
                        if ctl.trusted_domain(url):
                            urls.add(url)
        for citation in block.get("citations") or []:
            if isinstance(citation, dict):
                url = str(citation.get("url") or "")
                if ctl.trusted_domain(url):
                    urls.add(url)
    return urls


def web_search_extract(car: dict) -> dict:
    model = (os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-5").strip()
    primary = sorted({ctl.norm_key(item) for item in (car.get("primary_field_keys") or [])} | ctl.BLOCKED_PRIMARY_KEYS)
    prompt = """Search the web for exact technical specifications of this one vehicle. You MUST use web search.
Return ONE JSON object only in the final text; no markdown and no prose outside JSON.

CAR_UID: %s
OPERATOR_PRIMARY_FIELDS (authoritative, read-only):
%s
PRIMARY KEYS THAT MUST NOT BE REPEATED:
%s

Rules:
1. Match make/model/year or generation AND engine/fuel/transmission conservatively. Do not mix another engine or generation.
2. Search official manufacturer sources first, then the allowed technical databases.
3. Only output facts directly supported by search results from the allowed domains.
4. For every fact include source_urls with the exact result URL(s) that support that fact.
5. Do not output any primary field or semantic duplicate of a primary field.
6. Never output purchase/auction/wholesale/dealer/sale price, commercial terms, VIN, mileage, color, logistics, condition/history, option lists or client data.
7. Allowed categories: engine,dynamics,consumption,dimensions,capacity,weight,suspension,brakes,steering,wheels,ecology,additional.
8. field_key: lower_snake_case ASCII. confidence >=0.78 only when the exact modification is supported.
9. If the exact modification cannot be verified, return NO_CONFIDENT_MATCH and an empty facts list.

Schema:
{"status":"MATCHED|NO_CONFIDENT_MATCH","match":{"score":0.0,"reason":"brief Russian reason"},"facts":[{"field_key":"canonical_key","label_ru":"Russian label","category":"dimensions","display_value":"value with unit","unit":"unit or empty","confidence":0.0,"source_urls":["https://..."]}]}
""" % (
        car.get("car_uid"),
        json.dumps(car.get("fields") or {}, ensure_ascii=False, sort_keys=True),
        json.dumps(primary, ensure_ascii=False),
    )
    tool = {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
        "allowed_domains": sorted(ctl.TRUSTED_DOMAINS),
        "allowed_callers": ["direct"],
    }
    messages = [{"role": "user", "content": prompt}]
    all_urls: set[str] = set()
    envelope = None
    for _ in range(3):
        envelope = _api_call({
            "model": model,
            "max_tokens": 5000,
            "temperature": 0,
            "messages": messages,
            "tools": [tool],
        })
        content = envelope.get("content") or []
        all_urls |= _result_urls(content)
        if envelope.get("stop_reason") != "pause_turn":
            break
        messages.append({"role": "assistant", "content": content})
    if not envelope:
        raise ctl.ControllerError("ANTHROPIC_WEB_SEARCH_EMPTY")
    text = "\n".join(
        str(block.get("text") or "") for block in (envelope.get("content") or [])
        if isinstance(block, dict) and block.get("type") == "text"
    )
    result = ctl.extract_json_object(text)
    for fact in result.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        requested = [str(url) for url in (fact.get("source_urls") or [])]
        fact["source_urls"] = [url for url in requested if url in all_urls and ctl.trusted_domain(url)]
    result["_web_search_result_urls"] = sorted(all_urls)
    return result


def semantic_canonical_key(key: str, label: str) -> str:
    key = ctl.norm_key(key)
    text = key + " " + ctl.norm_key(label)
    rules = (
        ("front_track", ("front_track", "track_front", "передняя_колея", "колея_передняя")),
        ("rear_track", ("rear_track", "track_rear", "задняя_колея", "колея_задняя")),
        ("wheelbase", ("wheelbase", "wheel_base", "колесная_база", "колёсная_база")),
        ("length", ("overall_length", "vehicle_length", "body_length", "габаритная_длина", "длина_автомобиля", "длина")),
        ("width", ("overall_width", "vehicle_width", "body_width", "габаритная_ширина", "ширина_автомобиля", "ширина")),
        ("height", ("overall_height", "vehicle_height", "body_height", "габаритная_высота", "высота_автомобиля", "высота")),
        ("max_power", ("max_power", "maximum_power", "engine_power", "максимальная_мощность")),
        ("max_torque", ("max_torque", "maximum_torque", "engine_torque", "максимальный_крутящий_момент")),
        ("fuel_tank_capacity", ("fuel_tank_capacity", "fuel_tank", "tank_capacity", "объем_топливного_бака", "объём_топливного_бака")),
        ("kerb_weight", ("kerb_weight", "curb_weight", "снаряженная_масса", "снаряжённая_масса")),
        ("co2_emissions", ("co2_emissions", "co2_emission", "выброс_co2", "выбросы_co2")),
    )
    for canonical, aliases in rules:
        if key == canonical or any(alias in text for alias in aliases):
            return canonical
    return key


def semantic_dedup_candidate(candidate: dict) -> dict:
    best = {}
    for fact in candidate.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        canonical = semantic_canonical_key(str(fact.get("field_key") or ""), str(fact.get("label_ru") or ""))
        fact = dict(fact)
        fact["field_key"] = canonical
        current = best.get(canonical)
        if current is None or float(fact.get("confidence") or 0) > float(current.get("confidence") or 0):
            best[canonical] = fact
    candidate = dict(candidate)
    candidate["facts"] = list(best.values())
    return candidate


def repaired_build_batch_car(car: dict):
    if car["car_uid"] == "UA-0015":
        return {
            "car_uid": "UA-0015", "status": "ALREADY_CANARY",
            "match": {"score": 1.0, "reason": "UA-0015 уже прошла data-canary."},
            "facts": [], "source_domains": [],
        }, None
    warnings = []
    pages = ctl.discover_pages(car, canary=False)
    if pages:
        try:
            raw = ctl.retry_stage("AI_PAGE_" + car["car_uid"], lambda: ctl.anthropic_extract(car, pages), 2)
            candidate = semantic_dedup_candidate(ctl.validate_extraction(car, pages, raw, canary=False))
            if candidate.get("status") == "MATCHED" and candidate.get("facts"):
                candidate["extraction_mode"] = "AI_FROM_INDEXED_SOURCES"
                return candidate, None
        except Exception as exc:
            warnings.append("page:" + type(exc).__name__)
    try:
        raw = ctl.retry_stage("AI_WEB_" + car["car_uid"], lambda: web_search_extract(car), 2)
        candidate = semantic_dedup_candidate(ctl.validate_extraction(car, [], raw, canary=False))
        if candidate.get("status") == "MATCHED" and candidate.get("facts"):
            candidate["extraction_mode"] = "CLAUDE_WEB_SEARCH_VERIFIED"
            return candidate, None
        warnings.append("web:NO_CONFIDENT_MATCH")
    except Exception as exc:
        warnings.append("web:" + type(exc).__name__)
    return {
        "car_uid": car["car_uid"], "status": "NO_CONFIDENT_MATCH",
        "match": {"score": 0.0, "reason": "Расширенный поиск не дал безопасно подтверждённого совпадения."},
        "facts": [], "source_domains": [],
    }, ";".join(warnings) if warnings else "источники не найдены"


def run_cleanup(api: ctl.PythonAnywhereAPI) -> dict:
    if not CLEANUP.is_file():
        raise ctl.ControllerError("SEMANTIC_CLEANUP_FILE_MISSING")
    remote = ctl.REMOTE_DATA + "/remote_semantic_cleanup.py"
    ctl.retry_stage("UPLOAD_SEMANTIC_CLEANUP", lambda: api.upload(remote, CLEANUP.read_bytes()), 3)
    receipt = ctl.REMOTE_DATA + "/receipt_semantic_cleanup.json"
    command = "cd '%s' && python3.10 remote_semantic_cleanup.py > semantic_cleanup_stdout.log 2>&1" % ctl.REMOTE_DATA
    value = ctl.retry_stage("SEMANTIC_DEDUP_SANDBOX", lambda: ctl.remote_command(api, command, receipt, 900), 3)
    if value.get("contract_id") != ctl.CONTRACT_ID or value.get("status") != "PASS" or value.get("semantic_dedup_pass") is not True:
        raise ctl.ControllerError("SEMANTIC_DEDUP_NOT_PASS")
    for key in (
        "production_touched", "live_crm_write", "main_fields_changed", "public_path_write",
        "bot_code_changed", "services_restarted", "autopublication", "purchase_price_extracted",
        "purchase_price_logged", "purchase_price_uploaded", "production_authorized",
    ):
        if value.get(key) is not False:
            raise ctl.ControllerError("SEMANTIC_DEDUP_SCOPE:" + key)
    preview = api.read(ctl.REMOTE_DATA + "/ua0015_preview.html")
    if preview:
        ctl.atomic_text(ctl.DATA_OUT / "ua0015_preview.html", preview.decode("utf-8", errors="strict"))
    return value


def main() -> int:
    ctl.build_batch_car = repaired_build_batch_car
    evidence = ctl.run()
    api = ctl.PythonAnywhereAPI()
    cleanup = run_cleanup(api)
    evidence["semantic_dedup_pass"] = True
    evidence["semantic_cleanup"] = cleanup
    evidence["source_expansion_mode"] = "CLAUDE_WEB_SEARCH_WITH_DOMAIN_ALLOWLIST"
    ctl.atomic_json(ctl.DATA_OUT / "evidence.json", evidence)
    report = ctl.report_text(evidence)
    report += "\n## Repair v2\n- Claude web-search source expansion: enabled\n- Semantic dedup sandbox: PASS\n- Production write: NO\n"
    ctl.atomic_text(ctl.DATA_OUT / "report.md", report)
    print(json.dumps({
        "status": evidence.get("status"),
        "semantic_dedup_pass": True,
        "cards_summary": evidence.get("cards_summary"),
        "production_touched": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
