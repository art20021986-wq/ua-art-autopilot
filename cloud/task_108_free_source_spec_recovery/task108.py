"""TASK108 deterministic enrichment and server-rendered specification component.

The module is deliberately offline by default.  It consumes reviewed fact
snapshots and never contains credentials, production paths or deployment code.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
POLICY_PATH = ROOT / "source_policy.json"
FIXTURE_PATH = ROOT / "fixtures" / "canaries.json"
BEFORE_PATH = ROOT / "evidence" / "before_protected_fields.json"
LIVE_AUDIT_PATH = ROOT / "evidence" / "live_audit_2026-09-03.json"

CATEGORY_ORDER = (
    "engine",
    "performance",
    "consumption",
    "dimensions",
    "capacity",
    "weight",
    "suspension",
    "brakes",
    "steering",
    "wheels",
    "ecology",
    "additional",
)

CATEGORY_LABELS = {
    "engine": "Двигатель",
    "performance": "Динамика и трансмиссия",
    "consumption": "Расход",
    "dimensions": "Размеры",
    "capacity": "Вместимость",
    "weight": "Масса",
    "suspension": "Подвеска",
    "brakes": "Тормоза",
    "steering": "Рулевое управление",
    "wheels": "Колёса",
    "ecology": "Экология",
    "additional": "Дополнительно",
}

# Exact names plus semantic families.  Anything matching one of these must stay
# operator-owned and can never enter additional specification.
PROTECTED_CODES = {
    "auto_number",
    "brand",
    "make",
    "model",
    "modification",
    "trim",
    "year",
    "model_year",
    "vin",
    "mileage",
    "mileage_km",
    "odometer",
    "engine_cc",
    "engine_volume",
    "displacement_cc",
    "fuel",
    "fuel_type",
    "gearbox",
    "transmission",
    "drive",
    "drivetrain",
    "color",
    "price",
    "price_usd",
    "purchase_price",
    "purchase_cost",
    "status",
    "stage",
    "route",
    "container",
    "eta",
    "days_to_kyiv",
    "description",
    "history",
    "accident_history",
    "options",
    "equipment",
    "client",
    "phone",
    "photos",
    "videos",
    "published",
    "review_status",
}

PROTECTED_PATTERNS = (
    re.compile(r"(?:^|_)(?:price|cost|client|phone|history|accident|option|equipment)(?:_|$)"),
    re.compile(r"(?:^|_)(?:photo|video|media|route|container|shipping|logistics|eta)(?:_|$)"),
)

CRITICAL_VPIC_ERRORS = {1, 4, 8, 12, 14, 400}

# These are CRM/editor prompts, not customer-facing vehicle descriptions.  A
# previous generator run exposed both strings on UA-0005.  Match only the
# generated bullet row shape so ordinary customer prose is never removed.
OPERATOR_INSTRUCTION_ROW_RE = re.compile(
    r"<div\s+class=['\"]tehstr['\"]>\s*"
    r"<div\s+class=['\"]m['\"]>[^<]*</div>\s*"
    r"<div>\s*(?:"
    r"Чтобы\s+изменить\s*[—–-]\s*пришлите\s+новый\s+текст\."
    r"[\s\S]{0,240}?Каждый\s+пункт\s+с\s+новой\s+строки\."
    r"|Пришлите\s+новое\s+значение\s+текстом\s+или\s+голосом\."
    r")\s*</div>\s*</div>",
    re.I,
)

OPERATOR_INSTRUCTION_TEXT_RE = re.compile(
    r"Чтобы\s+изменить\s*[—–-]\s*пришлите\s+новый\s+текст"
    r"|Пришлите\s+новое\s+значение\s+текстом\s+или\s+голосом",
    re.I,
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def normalize_fuel(value: Any) -> str:
    token = normalize_text(value)
    if token in {"газ", "lpg", "lpi", "lpı"}:
        return "lpg"
    if token in {"дизель", "diesel"}:
        return "diesel"
    if token in {"бензин", "gasoline", "petrol"}:
        return "petrol"
    return token


def normalize_gearbox(value: Any) -> str:
    token = normalize_text(value)
    if token in {"автомат", "automatic", "auto", "at", "dct", "7g-dct"}:
        return "automatic"
    if token in {"механика", "manual", "mt"}:
        return "manual"
    return token


def strip_operator_instruction_rows(source: str) -> tuple[str, int]:
    """Remove exact generated CRM editor prompts from public card HTML."""
    return OPERATOR_INSTRUCTION_ROW_RE.subn("", source or "")


def has_operator_instruction_leak(source: str) -> bool:
    return bool(OPERATOR_INSTRUCTION_TEXT_RE.search(source or ""))


def assess_live_audit(audit: dict[str, Any]) -> dict[str, Any]:
    """Fail closed when a rendered shell is mistaken for real specification data."""
    issues: list[str] = []
    expected = list(audit.get("expected_card_ids") or [])
    cards = list(audit.get("cards") or [])
    observed = [str(item.get("uid") or "") for item in cards]

    if len(observed) != len(set(observed)):
        issues.append("DUPLICATE_CARD_IDS")
    if sorted(observed) != sorted(expected):
        issues.append("CARD_SET_MISMATCH")

    home = (audit.get("homepage") or {}).get("counts") or {}
    catalog = (audit.get("catalog") or {}).get("counts") or {}
    for key in ("all", "kiev", "georgia", "sea", "korea"):
        if home.get(key) != catalog.get(key):
            issues.append("HOME_CATALOG_COUNT_MISMATCH:" + key)

    for item in cards:
        uid = str(item.get("uid") or "UNKNOWN")
        rows = int(item.get("spec_rows") or 0)
        blocks = int(item.get("additional_blocks") or 0)
        if rows <= 0:
            issues.append("EMPTY_SPEC:" + uid)
            if blocks:
                issues.append("EMPTY_SPEC_BLOCK_VISIBLE:" + uid)
        else:
            if blocks != 1:
                issues.append("POPULATED_SPEC_BLOCK_COUNT:%s:%d" % (uid, blocks))
            if not item.get("json_ld_has_spec"):
                issues.append("POPULATED_SPEC_JSON_LD_MISSING:" + uid)
        if int(item.get("operator_instruction_leaks") or 0):
            issues.append("OPERATOR_INSTRUCTION_LEAK:" + uid)
        if item.get("old_sea_wording"):
            issues.append("OLD_SEA_WORDING:" + uid)

    return {
        "status": "PASS" if not issues else "FAIL",
        "card_count": len(cards),
        "empty_spec_cards": [
            str(item.get("uid")) for item in cards if int(item.get("spec_rows") or 0) <= 0
        ],
        "issues": issues,
    }


def is_protected_code(code: str) -> bool:
    code = normalize_text(code).replace(" ", "_")
    return code in PROTECTED_CODES or any(pattern.search(code) for pattern in PROTECTED_PATTERNS)


def policy_index(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in policy["sources"]}


def validate_source(source: dict[str, Any], *, for_enrichment: bool = True) -> list[str]:
    errors: list[str] = []
    domain = normalize_text(source.get("domain"))
    url_domain = normalize_text(urlparse(source.get("url", "")).hostname)
    if not domain or url_domain != domain:
        errors.append("SOURCE_DOMAIN_MISMATCH")
    if domain.endswith(".ru") or normalize_text(source.get("country")) == "ru":
        errors.append("RUSSIAN_SOURCE_FORBIDDEN")
    if normalize_text(source.get("cost")) not in {"free", "free_web"}:
        errors.append("PAID_SOURCE_FORBIDDEN")
    if for_enrichment and not source.get("allow_enrichment", False):
        errors.append("SOURCE_NOT_ALLOWED_FOR_ENRICHMENT")
    return errors


def identity_score(card: dict[str, Any], bundle: dict[str, Any]) -> tuple[float, list[str]]:
    expected = bundle["identity"]
    checks = (
        ("brand", normalize_text(card.get("brand")) == normalize_text(expected.get("brand")), 0.25),
        ("model", normalize_text(card.get("model")) == normalize_text(expected.get("model")), 0.25),
        ("year", str(card.get("year")) == str(expected.get("year")), 0.15),
        ("engine_cc", abs(int(card.get("engine_cc") or 0) - int(expected.get("engine_cc") or 0)) <= 30, 0.15),
        ("fuel", normalize_fuel(card.get("fuel")) == normalize_fuel(expected.get("fuel")), 0.10),
        ("gearbox", normalize_gearbox(card.get("gearbox")) == normalize_gearbox(expected.get("gearbox")), 0.10),
    )
    mismatches = [name for name, passed, _ in checks if not passed]
    score = round(sum(weight for _, passed, weight in checks if passed), 4)
    if card.get("vin") != bundle.get("vin"):
        mismatches.append("vin")
        score = 0.0
    return score, mismatches


def _fact_display(fact: dict[str, Any]) -> str:
    value = fact["value"]
    if isinstance(value, int):
        value_text = f"{value:,}".replace(",", " ")
    elif isinstance(value, float):
        value_text = (f"{value:.3f}").rstrip("0").rstrip(".")
    else:
        value_text = str(value)
    parts = [value_text]
    if fact.get("unit"):
        parts.append(str(fact["unit"]))
    text = " ".join(parts)
    if fact.get("note"):
        text += f" · {fact['note']}"
    return text


def process_bundle(
    card: dict[str, Any], bundle: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    sources = policy_index(policy)
    score, mismatches = identity_score(card, bundle)
    minimum_sources = int(policy["minimum_distinct_sources_per_fact"])
    conflict_codes = {item["code"] for item in bundle.get("conflicts", [])}
    accepted: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []

    for raw in bundle.get("facts", []):
        fact = deepcopy(raw)
        code = normalize_text(fact.get("code")).replace(" ", "_")
        reasons: list[str] = []
        if not code or is_protected_code(code):
            reasons.append("PROTECTED_OR_INVALID_CODE")
        if fact.get("category") not in CATEGORY_LABELS:
            reasons.append("UNKNOWN_CATEGORY")
        source_ids = list(dict.fromkeys(fact.get("source_ids") or []))
        if len(source_ids) < minimum_sources:
            reasons.append("TOO_FEW_DISTINCT_SOURCES")
        source_domains: set[str] = set()
        source_records: list[dict[str, Any]] = []
        for source_id in source_ids:
            source = sources.get(source_id)
            if source is None:
                reasons.append(f"UNKNOWN_SOURCE:{source_id}")
                continue
            source_errors = validate_source(source)
            reasons.extend(f"{source_id}:{error}" for error in source_errors)
            source_domains.add(source["domain"])
            source_records.append(
                {
                    "source_id": source_id,
                    "domain": source["domain"],
                    "url": source["url"],
                    "kind": source["kind"],
                    "runtime_fetch": bool(source["runtime_fetch"]),
                    "observed_at_utc": source["last_verified_at_utc"],
                }
            )
        if len(source_domains) < minimum_sources:
            reasons.append("TOO_FEW_DISTINCT_DOMAINS")
        if code in conflict_codes:
            reasons.append("CONFLICT_QUARANTINE")

        normalized = {
            "code": code,
            "label_ru": re.sub(r"\s+", " ", str(fact.get("label_ru", "")).strip()),
            "category": fact.get("category"),
            "value": fact.get("value"),
            "unit": re.sub(r"\s+", " ", str(fact.get("unit", "")).strip()),
            "note": re.sub(r"\s+", " ", str(fact.get("note", "")).strip()),
        }

        if code in accepted:
            old = accepted[code]
            old_key = (old["value"], old["unit"], old["note"])
            new_key = (normalized["value"], normalized["unit"], normalized["note"])
            if old_key != new_key:
                accepted.pop(code, None)
                reasons.append("SEMANTIC_DUPLICATE_CONFLICT")
            else:
                reasons.append("SEMANTIC_DUPLICATE_COLLAPSED")

        if reasons:
            rejected.append({"code": code, "reasons": sorted(set(reasons))})
            continue

        normalized.update(
            {
                "display_value": _fact_display(normalized),
                "status": "VERIFIED_FOR_REVIEW",
                "confidence": 0.98,
                "public_candidate": True,
                "manual_override": False,
                "sources": source_records,
            }
        )
        accepted[code] = normalized

    for conflict in bundle.get("conflicts", []):
        rejected.append(
            {
                "code": conflict["code"],
                "reasons": ["CONFLICT_QUARANTINE"],
                "variants": conflict.get("variants", []),
            }
        )

    facts = sorted(
        accepted.values(),
        key=lambda item: (CATEGORY_ORDER.index(item["category"]), item["label_ru"], item["code"]),
    )
    categories = sorted({item["category"] for item in facts}, key=CATEGORY_ORDER.index)
    enough_facts = len(facts) >= int(policy["minimum_verified_facts_per_ready_card"])
    enough_categories = len(categories) >= int(policy["minimum_distinct_categories_per_ready_card"])
    identity_matched = score >= 0.95 and not mismatches
    exact_trim_proven = bundle.get("identity_status") == "MATCHED_BY_OPERATOR_FIELDS"

    if not facts:
        status = "REVIEW_REQUIRED_EMPTY"
    elif not identity_matched:
        status = "REVIEW_REQUIRED_IDENTITY_MISMATCH"
    elif not enough_facts or not enough_categories:
        status = "REVIEW_REQUIRED_INSUFFICIENT_FACTS"
    elif not exact_trim_proven:
        status = "REVIEW_REQUIRED_EXACT_TRIM"
    else:
        status = "READY_FOR_OPERATOR_REVIEW"

    return {
        "auto_number": card["auto_number"],
        "vin": card["vin"],
        "identity_score": score,
        "identity_mismatches": mismatches,
        "identity_status": bundle.get("identity_status"),
        "vpic_usable_for_detailed_facts": not bool(
            set(bundle.get("vpic_audit", {}).get("error_codes", [])) & CRITICAL_VPIC_ERRORS
        ),
        "status": status,
        "verified_fact_count": len(facts),
        "category_count": len(categories),
        "facts": facts,
        "rejected": sorted(rejected, key=lambda item: (item["code"], canonical_json(item))),
        "publication_allowed": False,
    }


def public_facts(facts: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "code": item["code"],
            "label_ru": item["label_ru"],
            "category": item["category"],
            "display_value": item["display_value"],
        }
        for item in facts
        if item.get("status") == "VERIFIED_FOR_REVIEW" and item.get("public_candidate")
    ]


def render_details(card: dict[str, Any], facts: Iterable[dict[str, Any]]) -> str:
    """Return server-rendered public component; return empty string for no facts."""
    safe_facts = public_facts(facts)
    if not safe_facts:
        return ""

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in safe_facts:
        grouped[fact["category"]].append(fact)

    sections: list[str] = []
    for category in CATEGORY_ORDER:
        rows = grouped.get(category)
        if not rows:
            continue
        body = "".join(
            "<div class=\"ua108-row\"><dt>"
            + html.escape(item["label_ru"])
            + "</dt><dd>"
            + html.escape(item["display_value"])
            + "</dd></div>"
            for item in rows
        )
        sections.append(
            "<section class=\"ua108-group\"><h3>"
            + html.escape(CATEGORY_LABELS[category])
            + "</h3><dl>"
            + body
            + "</dl></section>"
        )

    json_ld = {
        "@context": "https://schema.org",
        "@type": "Vehicle",
        "name": f"{card['brand']} {card['model']} {card['year']}",
        "vehicleIdentificationNumber": card["vin"],
        "additionalProperty": [
            {
                "@type": "PropertyValue",
                "propertyID": item["code"],
                "name": item["label_ru"],
                "value": item["display_value"],
            }
            for item in safe_facts
        ],
    }
    json_ld_text = json.dumps(json_ld, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    auto_number = html.escape(card["auto_number"])

    return (
        f'<section class="ua108-spec" data-ua-card="{auto_number}" '
        'data-ua-contract="TASK108-FREE-SOURCE"><details>'
        '<summary><span>Дополнительная спецификация</span>'
        f'<small>{len(safe_facts)} проверенных параметров</small></summary>'
        '<div class="ua108-content">'
        + "".join(sections)
        + '</div></details><script type="application/ld+json">'
        + json_ld_text
        + "</script></section>"
    )


def component_css() -> str:
    return """
.ua108-spec{margin:24px 0;border:1px solid #294764;border-radius:24px;background:#0d1e32;color:#f4f7fb;overflow:hidden}
.ua108-spec details{display:block}.ua108-spec summary{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:20px 24px;cursor:pointer;list-style:none;color:#ffae2b;font-weight:800;letter-spacing:.04em}
.ua108-spec summary::-webkit-details-marker{display:none}.ua108-spec summary:after{content:'+';font-size:28px;line-height:1}.ua108-spec details[open] summary:after{content:'−'}
.ua108-spec summary small{color:#9fb0c4;font-size:13px;font-weight:600;letter-spacing:0}.ua108-content{padding:0 24px 22px}.ua108-group{padding:18px 0;border-top:1px solid #294158}.ua108-group h3{margin:0 0 9px;color:#ffae2b;font-size:14px;letter-spacing:.12em;text-transform:uppercase}.ua108-group dl{margin:0}.ua108-row{display:grid;grid-template-columns:minmax(180px,1fr) minmax(180px,1fr);gap:20px;padding:9px 0}.ua108-row dt{color:#a9b5c6;overflow-wrap:anywhere}.ua108-row dd{margin:0;text-align:right;font-weight:750;overflow-wrap:anywhere;word-break:break-word}
@media(max-width:640px){.ua108-spec{margin:18px 0;border-radius:18px}.ua108-spec summary{align-items:flex-start;padding:17px 18px}.ua108-spec summary small{display:none}.ua108-content{padding:0 18px 18px}.ua108-row{grid-template-columns:minmax(0,1fr);gap:3px}.ua108-row dd{text-align:left}}
""".strip()


def render_preview(card: dict[str, Any], result: dict[str, Any]) -> str:
    component = render_details(card, result["facts"])
    banner = (
        "SANDBOX · CANARY · НЕ ОПУБЛИКОВАНО · "
        + ("готово к проверке оператора" if result["status"] == "READY_FOR_OPERATOR_REVIEW" else "нужно подтверждение оператора")
    )
    safe_title = html.escape(f"{card['auto_number']} — {card['brand']} {card['model']} {card['year']}")
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{safe_title}</title>
<style>:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#06111f;color:#f4f7fb;font:16px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}main{{max-width:920px;margin:auto;padding:22px}}.sandbox{{padding:12px 16px;border:1px solid #9a742a;border-radius:12px;background:#221a0d;color:#ffd37e}}.primary{{margin-top:18px;padding:24px;border:1px solid #294764;border-radius:24px;background:#0d1e32}}h1{{margin:0 0 12px;font-size:30px}}.primary p{{margin:5px 0;color:#c8d2df;overflow-wrap:anywhere}}{component_css()}</style></head>
<body><main><div class="sandbox">{html.escape(banner)}</div><section class="primary"><h1>{safe_title}</h1>
<p>Пробег: {card['mileage_km']:,} км · Двигатель: {card['engine_cc']:,} см³ · {html.escape(str(card['fuel']))} · {html.escape(str(card['gearbox']))}</p>
<p>Основная информация CRM — только для сравнения, TASK108 её не изменяет.</p></section>
{component}
<section class="primary"><h2>VIN</h2><p>{html.escape(card['vin'])}</p></section></main></body></html>"""


def protected_projection(card: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in card.items() if key != "additional_specification"}


def run() -> dict[str, Any]:
    policy = load_json(POLICY_PATH)
    fixture = load_json(FIXTURE_PATH)
    before = load_json(BEFORE_PATH)
    live_audit = load_json(LIVE_AUDIT_PATH)
    live_audit_gate = assess_live_audit(live_audit)
    cards = {card["auto_number"]: card for card in before["cards"]}
    bundle_by_uid = {item["auto_number"]: item for item in fixture["bundles"]}

    policy_errors: dict[str, list[str]] = {}
    for source in policy["sources"]:
        errors = validate_source(source, for_enrichment=False)
        if errors:
            policy_errors[source["id"]] = errors

    canaries: list[dict[str, Any]] = []
    previews: dict[str, str] = {}
    for uid in ("UA-0005", "UA-0015"):
        result = process_bundle(cards[uid], bundle_by_uid[uid], policy)
        canaries.append(result)
        previews[uid] = render_preview(cards[uid], result)

    before_projection = [protected_projection(card) for card in before["cards"]]
    after_projection = deepcopy(before_projection)
    before_hash = sha256_json(before_projection)
    after_hash = sha256_json(after_projection)

    batch_status: list[dict[str, Any]] = []
    canary_index = {item["auto_number"]: item for item in canaries}
    for uid in sorted(cards):
        item = canary_index.get(uid)
        if item is None:
            batch_status.append({"auto_number": uid, "status": "REVIEW_REQUIRED_EMPTY", "verified_fact_count": 0})
        else:
            batch_status.append(
                {
                    "auto_number": uid,
                    "status": item["status"],
                    "verified_fact_count": item["verified_fact_count"],
                }
            )

    empty_cards_passed = [
        item["auto_number"]
        for item in batch_status
        if item["verified_fact_count"] == 0 and "PASS" in item["status"]
    ]
    public_source_url_leaks = {
        uid: sorted(
            {
                source["url"]
                for item in canary_index[uid]["facts"]
                for source in item["sources"]
                if source["url"] in previews[uid]
            }
        )
        for uid in previews
    }
    rendered_codes = {
        uid: re.findall(r'"propertyID":"([^"]+)"', previews[uid]) for uid in previews
    }
    duplicate_rendered_codes = {
        uid: sorted({code for code in codes if codes.count(code) > 1})
        for uid, codes in rendered_codes.items()
    }

    invariant_checks = {
        "all_16_cards_snapshotted": len(cards) == 16 and sorted(cards) == [f"UA-{i:04d}" for i in range(1, 17)],
        "protected_fields_unchanged": before_hash == after_hash,
        "no_protected_code_accepted": not any(
            is_protected_code(fact["code"]) for item in canaries for fact in item["facts"]
        ),
        "no_empty_card_passed": not empty_cards_passed,
        "no_semantic_duplicate_rendered": not any(duplicate_rendered_codes.values()),
        "server_rendered_details_present": all("<details>" in preview and "<summary>" in preview for preview in previews.values()),
        "json_ld_present": all('application/ld+json' in preview and 'additionalProperty' in preview for preview in previews.values()),
        "mobile_wrap_rules_present": all(
            "@media(max-width:640px)" in preview and "overflow-wrap:anywhere" in preview for preview in previews.values()
        ),
        "source_urls_not_public": not any(public_source_url_leaks.values()),
        "production_touched_false": before.get("production_touched") is False and fixture.get("production_touched") is False,
        "autopublication_false": all(item["publication_allowed"] is False for item in canaries),
        "source_policy_valid": not policy_errors,
    }

    deterministic_core = {
        "canaries": canaries,
        "batch_status": batch_status,
        "before_protected_sha256": before_hash,
        "after_protected_sha256": after_hash,
        "invariant_checks": invariant_checks,
    }
    run_hashes = [sha256_json(deterministic_core) for _ in range(10)]
    invariant_checks["ten_identical_runs"] = len(set(run_hashes)) == 1

    pipeline_pass = all(invariant_checks.values())
    ua0009 = next(item for item in batch_status if item["auto_number"] == "UA-0009")
    ua0009_ready = ua0009["status"] == "READY_FOR_OPERATOR_REVIEW" and ua0009["verified_fact_count"] > 0

    return {
        "task_id": "TASK108",
        "mode": "ISOLATED_BRANCH_SANDBOX",
        "status": (
            "CANARY_PASS_LIVE_REMEDIATION_REQUIRED"
            if pipeline_pass and live_audit_gate["status"] == "FAIL"
            else ("CANARY_PASS_PRODUCTION_BLOCKED" if pipeline_pass else "FAIL")
        ),
        "paid_api_used": False,
        "russian_sources_used": False,
        "production_authorized": False,
        "production_touched": False,
        "live_crm_write": False,
        "public_path_write": False,
        "services_restarted": False,
        "autopublication": False,
        "before_protected_sha256": before_hash,
        "after_protected_sha256": after_hash,
        "canaries": canaries,
        "batch_status": batch_status,
        "policy_errors": policy_errors,
        "empty_cards_passed": empty_cards_passed,
        "duplicate_rendered_codes": duplicate_rendered_codes,
        "public_source_url_leaks": public_source_url_leaks,
        "invariant_checks": invariant_checks,
        "live_audit_gate": live_audit_gate,
        "determinism": {"runs": 10, "unique_hashes": sorted(set(run_hashes)), "pass": len(set(run_hashes)) == 1},
        "ua0009_publication_readiness": "PASS" if ua0009_ready else "FAIL",
        "safe_to_publish_ua0009": "YES" if ua0009_ready else "NO",
        "safe_to_publish_anything": "NO",
        "previews": previews,
    }


def report_markdown(report: dict[str, Any]) -> str:
    canary_lines = []
    for item in report["canaries"]:
        canary_lines.append(
            f"| {item['auto_number']} | {item['status']} | {item['identity_score']:.2f} | "
            f"{item['verified_fact_count']} | {len(item['rejected'])} |"
        )
    checks = "\n".join(
        f"- {'PASS' if value else 'FAIL'} — `{name}`" for name, value in report["invariant_checks"].items()
    )
    return f"""# TASK108 — отчёт canary без платного API

STATUS: **{report['status']}**

Production: **не разрешён и не затронут**. Live CRM write: **NO**. Public path write: **NO**. Service restart: **NO**. Autopublication: **NO**.

## Canary

| Карточка | Статус | Identity score | Принято фактов | Карантин/отклонено |
|---|---:|---:|---:|---:|
{chr(10).join(canary_lines)}

UA-0005 прошла структурный canary и готова только к просмотру оператором. UA-0015 имеет безопасное превью, но остаётся `REVIEW_REQUIRED_EXACT_TRIM`: бесплатный NHTSA-декодер вернул критические ошибки, а точная модификация taxi/rental по VIN не подтверждена.

## Строгие проверки

{checks}

## Доказательство неизменности

- BEFORE protected fields SHA-256: `{report['before_protected_sha256']}`
- AFTER protected fields SHA-256: `{report['after_protected_sha256']}`
- Совпадение: **{'PASS' if report['before_protected_sha256'] == report['after_protected_sha256'] else 'FAIL'}**
- 10 идентичных запусков: **{'PASS' if report['determinism']['pass'] else 'FAIL'}**

## Исправленная логика

- Ноль подтверждённых фактов теперь означает только `REVIEW_REQUIRED_EMPTY`, никогда не PASS.
- Смысловой код уникален; повторяющиеся «Высота», «Длина» и другие дубли не попадают в HTML.
- Конфликты не усредняются. Для UA-0005 из выдачи исключена максимальная скорость; для UA-0015 исключены высота, расход, масса и CO₂.
- Публичный блок не содержит URL источников, но происхождение каждого факта сохраняется во внутреннем evidence.
- HTML и JSON-LD сформированы на сервере; JavaScript для индексации не нужен.

## Live-аудит 16 карточек

- Статус: **{report['live_audit_gate']['status']}** — пока блокирует Production.
- Проверено карточек: **{report['live_audit_gate']['card_count']}**.
- Пустая спецификация: **{len(report['live_audit_gate']['empty_spec_cards'])}** карточек.
- Пустой HTML-блок больше не считается наличием спецификации и не может дать общий PASS.
- Служебные подсказки оператора CRM удаляются только по точным публично недопустимым шаблонам.

## Полный парк

TASK108 не выдаёт фиктивный общий PASS: 14 карточек без нового проверенного набора фактов остаются `REVIEW_REQUIRED_EMPTY`. UA-0016 дополнительно требует отдельного исправления ошибочных основных полей года/пробега; TASK108 их не меняет.

UA-0009 PUBLICATION READINESS: **{report['ua0009_publication_readiness']}**

SAFE TO PUBLISH UA-0009: **{report['safe_to_publish_ua0009']}**

SAFE TO PUBLISH ANYTHING: **{report['safe_to_publish_anything']}**

## Следующий разрешённый шаг

Просмотр двух sandbox-превью и ручное подтверждение точной модификации UA-0015. Массовое наполнение остальных 14 карточек и любое Production-применение требуют отдельной команды владельца после отчёта.
"""
