"""Approved source boundaries. Importing this module never performs network I/O.

Non-vPIC imports are a trusted operator/adapter boundary, not an HTML scraper.
Supplier rights and document review must be supplied out of band by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit, urlunsplit
import copy
import hashlib
import ipaddress
import json
import math
import re
import time

APPROVED_IDS = frozenset({"kia_kr", "hyundai_kr", "mercedes_archive", "audi_official",
    "danawa", "carisyou", "auto_data", "cars_data", "ultimate_specs", "vpic"})
MAX_RESPONSE_BYTES = 1_000_000
MAX_FACTS = 256
MAX_REDIRECTS = 2
MAX_TOTAL_SECONDS = 15.0
IDENTITY_FIELDS = ("make", "model", "year", "market", "fuel", "gearbox")
OPTIONAL_IDENTITY_FIELDS = ("generation", "engine", "engine_cc", "trim")
POSITIVE_FIELDS = frozenset({"length_mm", "width_mm", "height_mm", "wheelbase_mm",
    "engine_cc", "engine_displacement_l", "power_hp", "power_kw", "torque_nm",
    "doors", "seats", "cylinders", "curb_weight_kg", "fuel_tank_l", "model_year"})
UNKNOWN = frozenset({"", "unknown", "n/a", "null", "none", "невідомо", "неизвестно", "-", "—"})
SENSITIVE_QUERY = re.compile(r"(?:key|token|secret|password|passwd|credential|authorization|signature)", re.I)
KEY = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
VIN = re.compile(r"[A-HJ-NPR-Z0-9]{17}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class SourceError(ValueError):
    """Stable safe code only: never reflect an untrusted URL/body/credential."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    origin_group: str
    kind: str
    allowed_routes: Mapping[str, tuple[str, ...]]
    adapter: str
    provisioning: str
    live_acceptance: str
    documentation: str
    requirements: str


def load_registry(path: str | Path | None = None) -> dict[str, Source]:
    raw = json.loads(Path(path or Path(__file__).with_name("sources.json")).read_text("utf-8"))
    if raw.get("schema_version") != 1 or raw.get("selection_approved") is not True:
        raise SourceError("REGISTRY_SCHEMA_INVALID")
    rows = raw.get("sources", [])
    if len(rows) != 10 or {r.get("id") for r in rows} != APPROVED_IDS:
        raise SourceError("REGISTRY_MUST_CONTAIN_EXACT_APPROVED_TEN")
    result = {}
    for row in rows:
        if row["id"] in result or row.get("live_acceptance") != "NOT_TESTED":
            raise SourceError("REGISTRY_BASELINE_INVALID")
        if row["id"] != "vpic" and row.get("provisioning") != "NOT_PROVISIONED":
            raise SourceError("REGISTRY_MUST_NOT_SELF_PROVISION")
        routes = row.get("allowed_routes")
        if not isinstance(routes, dict) or not routes:
            raise SourceError("REGISTRY_ROUTES_INVALID")
        for host, paths in routes.items():
            if not re.fullmatch(r"[a-z0-9.-]+", host) or not isinstance(paths, list) or not paths:
                raise SourceError("REGISTRY_ROUTES_INVALID")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise SourceError("REGISTRY_ROUTES_INVALID")
            if any(not isinstance(p, str) or not p.startswith("/") or ".." in p for p in paths):
                raise SourceError("REGISTRY_ROUTES_INVALID")
        result[row["id"]] = Source(**{k: row[k] for k in (
            "id", "name", "origin_group", "kind", "adapter", "provisioning",
            "live_acceptance", "documentation", "requirements")},
            allowed_routes={h: tuple(p) for h, p in routes.items()})
    if any(not KEY.fullmatch(s.origin_group) for s in result.values()):
        raise SourceError("REGISTRY_ORIGIN_GROUPS_INVALID")
    return result


def _source(source_id: str, registry: Mapping[str, Source] | None) -> Source:
    try:
        return (registry or load_registry())[source_id]
    except (KeyError, TypeError):
        raise SourceError("SOURCE_NOT_APPROVED") from None


def validate_source_url(source_id: str, url: str,
                        registry: Mapping[str, Source] | None = None) -> str:
    source = _source(source_id, registry)
    if not isinstance(url, str) or len(url) > 2048 or re.search(r"[\x00-\x20\x7f\\]", url):
        raise SourceError("URL_INVALID")
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None:
            raise SourceError("URL_HTTPS_WITHOUT_CREDENTIALS_REQUIRED")
        if parsed.port not in (None, 443) or parsed.fragment:
            raise SourceError("URL_PORT_OR_FRAGMENT_FORBIDDEN")
        host = (parsed.hostname or "").lower()
    except SourceError:
        raise
    except (ValueError, UnicodeError):
        raise SourceError("URL_INVALID") from None
    if host not in source.allowed_routes or parsed.netloc.lower() not in (host, host + ":443"):
        raise SourceError("URL_HOST_NOT_APPROVED")
    path = parsed.path or "/"
    # Decode repeatedly so a later intermediary cannot introduce traversal/separators.
    decoded = path
    for _ in range(4):
        next_path = unquote(decoded)
        if next_path == decoded:
            break
        decoded = next_path
    if "%" in decoded or "\\" in decoded or re.search(r"[\x00-\x20\x7f]", decoded):
        raise SourceError("URL_PATH_INVALID")
    if any(x in (".", "..") for x in decoded.split("/")) or "//" in decoded:
        raise SourceError("URL_PATH_INVALID")
    if not any(decoded.startswith(p) if p.endswith("/") else decoded == p
               for p in source.allowed_routes[host]):
        raise SourceError("URL_PATH_NOT_APPROVED")
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if SENSITIVE_QUERY.search(key) or re.search(r"[\x00-\x1f\x7f]", key + value):
            raise SourceError("URL_QUERY_CREDENTIAL_OR_CONTROL_FORBIDDEN")
        if key.lower() in ("url", "uri", "redirect", "redirect_uri", "next", "callback", "jsonp"):
            raise SourceError("URL_QUERY_REDIRECT_FORBIDDEN")
    return urlunsplit(("https", host, path, parsed.query, ""))


@dataclass(frozen=True)
class VehicleIdentity:
    vin: str = ""
    make: str = ""
    model: str = ""
    year: int | None = None
    market: str = ""
    fuel: str = ""
    gearbox: str = ""
    generation: str = ""
    engine: str = ""
    engine_cc: int | None = None
    trim: str = ""


def _identity(value: VehicleIdentity | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, VehicleIdentity):
        return vars(value).copy()
    if not isinstance(value, Mapping):
        raise SourceError("IDENTITY_INVALID")
    return dict(value)


def _norm(value: Any) -> str:
    return " ".join(str(value).strip().casefold().split()) if value is not None else ""


def validate_identity(candidate: VehicleIdentity | Mapping[str, Any],
                      target: VehicleIdentity | Mapping[str, Any], *, vehicle=False) -> None:
    candidate, target = _identity(candidate), _identity(target)
    for key in IDENTITY_FIELDS:
        if not _norm(target.get(key)) or not _norm(candidate.get(key)):
            raise SourceError("IDENTITY_INCOMPLETE")
        if _norm(candidate[key]) != _norm(target[key]):
            raise SourceError("IDENTITY_MISMATCH")
    for key in OPTIONAL_IDENTITY_FIELDS:
        if _norm(target.get(key)) and _norm(candidate.get(key)) != _norm(target[key]):
            raise SourceError("IDENTITY_MISMATCH")
    cv, tv = str(candidate.get("vin", "")).upper(), str(target.get("vin", "")).upper()
    if cv and (not VIN.fullmatch(cv) or cv != tv):
        raise SourceError("VIN_MISMATCH")
    if vehicle and (not VIN.fullmatch(tv) or cv != tv):
        raise SourceError("VEHICLE_EVIDENCE_REQUIRES_EXACT_VIN")


@dataclass(frozen=True)
class AccessGrant:
    source_id: str
    automated_access: bool = False
    permanent_storage: bool = False
    public_display: bool = False
    reference: str = ""
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)


def _check_access(source: Source, access: AccessGrant | None) -> None:
    if source.id == "vpic" and access is None:
        return
    if not isinstance(access, AccessGrant) or access.source_id != source.id:
        raise SourceError("SUPPLIER_NOT_PROVISIONED")
    if not (access.automated_access and access.permanent_storage and access.public_display and access.reference):
        raise SourceError("SUPPLIER_RIGHTS_INCOMPLETE")


@dataclass(frozen=True)
class ImportAuthorization:
    source_id: str
    normalizer_id: str
    document_sha256: str


def _text(value: Any, max_length=160) -> str:
    if not isinstance(value, str) or len(value) > max_length or re.search(r"[<>\x00-\x1f\x7f]", value):
        raise SourceError("FACT_TEXT_INVALID")
    return value.strip()


def _fact_value(key: str, value: Any) -> Any:
    if value is None or isinstance(value, str) and _norm(value) in UNKNOWN:
        return None
    if not isinstance(value, (str, int, float, bool)):
        raise SourceError("FACT_VALUE_INVALID")
    if isinstance(value, str):
        value = _text(value, 500)
    if isinstance(value, float) and not math.isfinite(value):
        raise SourceError("FACT_VALUE_INVALID")
    if key in POSITIVE_FIELDS:
        try:
            numeric = float(value)
        except (ValueError, TypeError):
            raise SourceError("POSITIVE_FACT_REQUIRES_NUMBER") from None
        if isinstance(value, bool) or not math.isfinite(numeric) or numeric <= 0:
            raise SourceError("ZERO_OR_NEGATIVE_PLACEHOLDER_FORBIDDEN")
        return int(numeric) if numeric.is_integer() else numeric
    return value


def parse_normalized_import(source_id: str, payload: Mapping[str, Any],
        target: VehicleIdentity | Mapping[str, Any], *, access: AccessGrant | None = None,
        authorization: ImportAuthorization | None = None,
        registry: Mapping[str, Source] | None = None) -> list[dict[str, Any]]:
    """Accept only an out-of-band authorized, reviewed normalized document.

    A browser fetch/search result or payload declaring itself trusted is insufficient.
    The supplied document SHA must have been checked by the trusted normalizer.
    """
    source = _source(source_id, registry)
    _check_access(source, access)
    if source.adapter != "normalized_import_v1":
        raise SourceError("SOURCE_ADAPTER_MISMATCH")
    if (not isinstance(authorization, ImportAuthorization) or authorization.source_id != source_id
            or not authorization.normalizer_id or not SHA256.fullmatch(authorization.document_sha256)):
        raise SourceError("TRUSTED_NORMALIZER_REQUIRED")
    if not isinstance(payload, Mapping) or payload.get("schema") != "ua-art.normalized-source.v1":
        raise SourceError("IMPORT_SCHEMA_INVALID")
    if payload.get("source_id") != source_id:
        raise SourceError("SOURCE_IMPERSONATION")
    document = payload.get("document", {})
    if not isinstance(document, Mapping) or document.get("sha256") != authorization.document_sha256:
        raise SourceError("DOCUMENT_HASH_MISMATCH")
    url = validate_source_url(source_id, document.get("url"), registry)
    evidence_kind = document.get("evidence_kind")
    if evidence_kind not in ("manufacturer_document", "catalog_record", "vehicle_document"):
        raise SourceError("EVIDENCE_KIND_INVALID")
    if evidence_kind == "manufacturer_document" and source.kind != "manufacturer":
        raise SourceError("SOURCE_IMPERSONATION")
    validate_identity(payload.get("identity"), target, vehicle=evidence_kind == "vehicle_document")
    facts = payload.get("facts")
    if not isinstance(facts, list) or len(facts) > MAX_FACTS:
        raise SourceError("FACT_COUNT_INVALID")
    result, seen = [], set()
    for row in facts:
        if not isinstance(row, Mapping) or not KEY.fullmatch(str(row.get("key", ""))):
            raise SourceError("FACT_KEY_INVALID")
        if row.get("source_id", source_id) != source_id:
            raise SourceError("SOURCE_IMPERSONATION")
        if row.get("source_url", url) != url:
            raise SourceError("SOURCE_DOCUMENT_MISMATCH")
        key = row["key"]
        if key in seen:
            raise SourceError("DUPLICATE_FACT_KEY")
        seen.add(key)
        category = row.get("category", "technical")
        if category not in ("technical", "equipment", "identity"):
            raise SourceError("FACT_CATEGORY_INVALID")
        if category == "equipment" and evidence_kind != "vehicle_document":
            raise SourceError("EQUIPMENT_REQUIRES_VEHICLE_EVIDENCE")
        value = _fact_value(key, row.get("value"))
        if value is None:
            continue
        result.append({"key": key, "value": value, "unit": _text(row.get("unit", ""), 32),
            "label_uk": _text(row.get("label_uk", key)), "label_ru": _text(row.get("label_ru", key)),
            "category": category, "source_id": source_id, "source_url": url,
            "verification_status": "DOCUMENT_CANDIDATE",
            "provenance": {"origin_group": source.origin_group, "evidence_kind": evidence_kind,
                "document_sha256": authorization.document_sha256,
                "normalizer_id": _text(authorization.normalizer_id),
                "rights_reference": _text(access.reference, 240),
                "identity": _identity(payload["identity"])}})
    return result


@dataclass(frozen=True)
class Request:
    url: str
    timeout_seconds: float
    max_bytes: int
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes = field(repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)


def fetch_source(source_id: str, url: str, *, transport: Callable[[Request], Response] | None = None,
        access: AccessGrant | None = None, registry: Mapping[str, Source] | None = None,
        max_bytes: int = MAX_RESPONSE_BYTES, timeout_seconds: float = MAX_TOTAL_SECONDS) -> Response:
    """Single bounded GET via injected transport; no retries and no built-in network.

    Transport MUST enforce request timeout and max_bytes while reading, resolve only
    public IPs, use TLS verification, and disable automatic redirects. The caller
    provisions that transport separately; exceptions never expose its diagnostics.
    """
    source = _source(source_id, registry)
    _check_access(source, access)
    current = validate_source_url(source_id, url, registry)
    if transport is None:
        raise SourceError("TRANSPORT_NOT_CONFIGURED")
    if not 1 <= max_bytes <= MAX_RESPONSE_BYTES or not 0 < timeout_seconds <= MAX_TOTAL_SECONDS:
        raise SourceError("TRANSPORT_LIMITS_INVALID")
    started, seen = time.monotonic(), set()
    initial_host = urlsplit(current).hostname
    for hop in range(MAX_REDIRECTS + 1):
        if current in seen:
            raise SourceError("REDIRECT_LOOP")
        seen.add(current)
        remaining = timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            raise SourceError("TRANSPORT_TIMEOUT")
        # Never forward credentials across a redirect, including approved Audi hosts.
        headers = dict(access.headers) if access and hop == 0 else {}
        if urlsplit(current).hostname != initial_host:
            headers = {}
        try:
            response = transport(Request(current, remaining, max_bytes, headers))
        except Exception:
            raise SourceError("TRANSPORT_FAILED") from None
        if time.monotonic() - started > timeout_seconds:
            raise SourceError("TRANSPORT_TIMEOUT")
        if not isinstance(response, Response) or not isinstance(response.body, bytes):
            raise SourceError("TRANSPORT_RESPONSE_INVALID")
        if len(response.body) > max_bytes:
            raise SourceError("RESPONSE_TOO_LARGE")
        if response.status in (301, 302, 303, 307, 308):
            if hop == MAX_REDIRECTS:
                raise SourceError("REDIRECT_LIMIT")
            location = next((v for k, v in response.headers.items() if k.lower() == "location"), None)
            if not isinstance(location, str) or not location:
                raise SourceError("REDIRECT_LOCATION_MISSING")
            current = validate_source_url(source_id, urljoin(current, location), registry)
            continue
        if response.status != 200:
            raise SourceError("SOURCE_HTTP_ERROR")
        return response
    raise SourceError("REDIRECT_LIMIT")


def parse_vpic(payload: bytes | str | Mapping[str, Any], target: VehicleIdentity | Mapping[str, Any],
        *, source_url: str | None = None) -> list[dict[str, Any]]:
    target = _identity(target)
    vin = str(target.get("vin", "")).upper()
    if not VIN.fullmatch(vin):
        raise SourceError("VIN_INVALID")
    if isinstance(payload, (bytes, str)):
        if len(payload) > MAX_RESPONSE_BYTES:
            raise SourceError("RESPONSE_TOO_LARGE")
        try:
            payload = json.loads(payload)
        except (ValueError, UnicodeError):
            raise SourceError("VPIC_JSON_INVALID") from None
    if not isinstance(payload, Mapping) or not isinstance(payload.get("Results"), list) or len(payload["Results"]) != 1:
        raise SourceError("VPIC_RESULT_INVALID")
    row = payload["Results"][0]
    if not isinstance(row, Mapping) or str(row.get("ErrorCode", "")) != "0":
        raise SourceError("VPIC_DECODE_INCOMPLETE")
    if str(row.get("VIN", "")).upper() != vin:
        raise SourceError("VIN_MISMATCH")
    for field_name, response_key in (("make", "Make"), ("model", "Model"), ("year", "ModelYear")):
        if _norm(target.get(field_name)) and _norm(target[field_name]) != _norm(row.get(response_key)):
            raise SourceError("IDENTITY_MISMATCH")
    url = validate_source_url("vpic", source_url or
        "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValuesExtended/" + vin + "?format=json")
    if urlsplit(url).path.rstrip("/").split("/")[-1].upper() != vin:
        raise SourceError("VIN_MISMATCH")
    fields = (("Make", "make", "Марка", "Марка", ""),
        ("Model", "model", "Модель", "Модель", ""),
        ("ModelYear", "model_year", "Модельний рік", "Модельный год", ""),
        ("BodyClass", "body_class", "Тип кузова за vPIC", "Тип кузова по vPIC", ""),
        ("DisplacementL", "engine_displacement_l", "Об’єм двигуна за vPIC", "Объём двигателя по vPIC", "л"))
    result = []
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    for raw_key, key, uk, ru, unit in fields:
        value = _fact_value(key, row.get(raw_key))
        if value is None:
            continue
        result.append({"key": key, "value": value, "unit": unit, "label_uk": uk, "label_ru": ru,
            "category": "identity", "source_id": "vpic", "source_url": url,
            "verification_status": "IDENTITY_ONLY",
            "provenance": {"origin_group": "nhtsa_vpic", "evidence_kind": "vin_identity",
                "document_sha256": digest, "identity": {"vin": vin, "make": row.get("Make"),
                    "model": row.get("Model"), "year": row.get("ModelYear")},
                "coverage": "US_REGULATORY_DATA_NON_US_COVERAGE_NOT_GUARANTEED"}})
    return result


def resolve_facts(candidates: list[dict[str, Any]], target: VehicleIdentity | Mapping[str, Any],
                  registry: Mapping[str, Source] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Resolve consensus per key; conflicts stay pending and cannot replace old facts.

    One exact manufacturer document OR two catalog origin groups are required.
    An equipment claim additionally needs vehicle-specific document evidence.
    """
    registry = registry or load_registry()
    accepted, pending, rejected, grouped = [], [], [], {}
    for original in candidates:
        row = copy.deepcopy(original)
        try:
            source = _source(row.get("source_id"), registry)
            validate_source_url(source.id, row.get("source_url"), registry)
            if row.get("verification_status") == "IDENTITY_ONLY" and source.kind == "vin_identity":
                pending.append(dict(row, reason="VIN_IDENTITY_NOT_TECHNICAL_CONFIRMATION"))
                continue
            provenance = row.get("provenance", {})
            if (row.get("verification_status") != "DOCUMENT_CANDIDATE"
                    or provenance.get("origin_group") != source.origin_group
                    or not SHA256.fullmatch(str(provenance.get("document_sha256", "")))
                    or not provenance.get("normalizer_id") or not provenance.get("rights_reference")):
                raise SourceError("UNTRUSTED_CANDIDATE")
            kind = provenance.get("evidence_kind")
            if kind not in ("manufacturer_document", "catalog_record", "vehicle_document"):
                raise SourceError("EVIDENCE_KIND_INVALID")
            if kind == "manufacturer_document" and source.kind != "manufacturer":
                raise SourceError("SOURCE_IMPERSONATION")
            equipment = row.get("category") == "equipment"
            if equipment and kind != "vehicle_document":
                raise SourceError("EQUIPMENT_REQUIRES_VEHICLE_EVIDENCE")
            validate_identity(provenance.get("identity"), target, vehicle=equipment or kind == "vehicle_document")
            if not KEY.fullmatch(str(row.get("key", ""))):
                raise SourceError("FACT_KEY_INVALID")
            row["value"] = _fact_value(row["key"], row.get("value"))
            if row["value"] is None:
                raise SourceError("UNKNOWN_NOT_A_FACT")
            grouped.setdefault(row["key"], []).append(row)
        except SourceError as error:
            rejected.append({"key": row.get("key"), "source_id": row.get("source_id"), "reason": error.code})
    for key, rows in grouped.items():
        if len({row.get("category") for row in rows}) != 1:
            pending.extend(dict(row, reason="CATEGORY_CONFLICT") for row in rows)
            continue
        variants = {(json.dumps(row["value"], sort_keys=True, ensure_ascii=False), row.get("unit", "")) for row in rows}
        if len(variants) != 1:
            pending.extend(dict(row, reason="SOURCE_CONFLICT") for row in rows)
            continue
        groups = {registry[row["source_id"]].origin_group for row in rows
                  if registry[row["source_id"]].kind == "catalog"}
        manufacturer = any(registry[row["source_id"]].kind == "manufacturer"
                           and row["provenance"]["evidence_kind"] == "manufacturer_document" for row in rows)
        equipment = any(row.get("category") == "equipment" for row in rows)
        vehicle = any(row["provenance"]["evidence_kind"] == "vehicle_document" for row in rows)
        if (equipment and vehicle) or (not equipment and (manufacturer or len(groups) >= 2)):
            row = copy.deepcopy(rows[0])
            row["verification_status"] = "VEHICLE_VERIFIED" if equipment else "MODEL_VERIFIED"
            row["provenance"]["corroborating_sources"] = sorted({r["source_id"] for r in rows})
            row["provenance"]["evidence"] = [{"source_id": r["source_id"], "source_url": r["source_url"],
                "document_sha256": r["provenance"]["document_sha256"]} for r in rows]
            accepted.append(row)
        else:
            pending.extend(dict(row, reason="INSUFFICIENT_INDEPENDENT_EVIDENCE") for row in rows)
    return {"accepted": accepted, "pending": pending, "rejected": rejected}


def retain_on_failed_refresh(existing: list[dict[str, Any]], *, error: str | None = None,
                             resolved: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """A failed/empty refresh is never a delete instruction; manual facts win."""
    result = copy.deepcopy(existing)
    if error or not resolved:
        return result
    positions = {row["key"]: i for i, row in enumerate(result)}
    for row in resolved.get("accepted", []):
        if row.get("verification_status") not in ("MODEL_VERIFIED", "VEHICLE_VERIFIED"):
            continue
        index = positions.get(row["key"])
        if index is not None and (result[index].get("manual_override") or
                result[index].get("verification_status") == "MANUAL_VERIFIED"):
            continue
        if index is None:
            positions[row["key"]] = len(result)
            result.append(copy.deepcopy(row))
        else:
            result[index] = copy.deepcopy(row)
    return result


def readiness_report(registry: Mapping[str, Source] | None = None) -> dict[str, Any]:
    sources = (registry or load_registry()).values()
    return {"selected": 10, "selection_approved": True, "live_pass": 0,
        "status": "NOT_READY_FOR_LIVE_ENRICHMENT",
        "sources": [{"source_id": s.id, "provisioning": s.provisioning,
                     "live_acceptance": s.live_acceptance} for s in sources]}
