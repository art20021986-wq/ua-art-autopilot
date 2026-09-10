"""Bounded approved-source collection and additive specification merge.

No CRM writes, publication, legacy enqueue, destructive replacement, or schema
creation occurs here. The caller owns a durable generation/slot lease and an
identity lock. This adapter deliberately does not call legacy ``enrich`` or
``_store_facts``: their source list and overwrite semantics are incompatible.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable

import source_policy as policy
import profile_library


POLICY_VERSION = "UA-ART-SPEC-PERSIST-18-10M-001-v1"
SOURCES = (
    ("kia_korea", "Kia Korea", "kia.com"),
    ("hyundai_korea", "Hyundai Korea", "hyundai.com"),
    ("mercedes_archive", "Mercedes-Benz Public Archive", "mercedes-benz-publicarchive.com"),
    ("audi_mediacenter", "Audi MediaCenter", "audi-mediacenter.com"),
    ("danawa", "Danawa Auto", "auto.danawa.com"),
    ("carisyou", "Carisyou", "carisyou.com"),
    ("auto_data", "Auto-Data.net", "auto-data.net"),
    ("cars_data", "Cars-Data.com", "cars-data.com"),
    ("ultimatespecs", "UltimateSpecs", "ultimatespecs.com"),
    ("nhtsa_vpic", "NHTSA vPIC", "vpic.nhtsa.dot.gov"),
)
APPROVED_DOMAINS = frozenset(row[2] for row in SOURCES)
# Public catalogue pages of Auto-Data/Cars-Data are intentionally not used as
# substitutes for the approved API transports. Historical facts remain intact.
HTTP_DOMAINS = frozenset({"auto.danawa.com", "carisyou.com", "ultimatespecs.com", "vpic.nhtsa.dot.gov"})
CATALOG_DOMAINS = tuple(row[2] for row in SOURCES if row[2] in HTTP_DOMAINS and row[0] != "nhtsa_vpic")
HTTP_LIMIT = threading.BoundedSemaphore(6)
UID_RE = re.compile(r"^UA-\d{4,6}$")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
BAD_TEXT = re.compile(r"[<>]|https?://|javascript:|\b(?:affiliate|sponsored|advertisement)\b", re.I)


class CollectorError(RuntimeError):
    pass


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _identity_value(value: Any) -> str:
    """Preserve normalized Japanese chassis IDs without passing them to vPIC."""
    result = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{5,30}", result):
        raise CollectorError("INVALID_VEHICLE_IDENTITY")
    return result


def _domain(url: str) -> str | None:
    try:
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return None
        if any(ord(char) < 32 for char in url) or "\\" in url or parsed.fragment:
            return None
        if any(re.search(r"utm_|aff|redirect|token|api.?key|banner|adurl", key, re.I)
               for key in urllib.parse.parse_qs(parsed.query)):
            return None
        host = host[4:] if host.startswith("www.") else host
        return host if host in APPROVED_DOMAINS else None
    except (TypeError, ValueError):
        return None


def _transport_domain(url: str) -> str | None:
    domain = _domain(url)
    if domain not in HTTP_DOMAINS:
        return None
    path = urllib.parse.urlsplit(url).path
    prefixes = {
        "auto.danawa.com": ("/auto/",),
        "carisyou.com": ("/car/",),
        "ultimatespecs.com": ("/car-specs/",),
        "vpic.nhtsa.dot.gov": ("/api/vehicles/DecodeVinValues/",),
    }
    return domain if path.startswith(prefixes[domain]) else None


class _RedirectGuard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: Any, msg: Any, headers: Any, newurl: str) -> Any:
        if not _transport_domain(req.full_url) or _transport_domain(newurl) != _transport_domain(req.full_url):
            raise CollectorError("REDIRECT_FORBIDDEN")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _BudgetResponse:
    def __init__(self, response: Any, deadline: float):
        self.response, self.deadline = response, deadline
        self.status = getattr(response, "status", 200)

    def geturl(self) -> str:
        return str(self.response.geturl())

    def read(self, maximum: int) -> bytes:
        chunks, length = [], 0
        while length < maximum:
            if time.monotonic() >= self.deadline:
                raise CollectorError("COLLECTION_DEADLINE")
            block = self.response.read(min(64 * 1024, maximum - length))
            if not block:
                break
            chunks.append(block)
            length += len(block)
        return b"".join(chunks)

    def __enter__(self) -> "_BudgetResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        self.response.close()
        HTTP_LIMIT.release()


def _bounded_opener(deadline: float, supplied: Callable[..., Any] | None, request_timeout: float) -> Callable[..., Any]:
    transport = supplied or urllib.request.build_opener(_RedirectGuard()).open

    def open_request(request: Any, timeout: float = 8) -> Any:
        if not _transport_domain(request.full_url):
            raise CollectorError("TRANSPORT_NOT_CONFIGURED")
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not HTTP_LIMIT.acquire(timeout=max(0.0, remaining)):
            raise CollectorError("COLLECTION_DEADLINE")
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CollectorError("COLLECTION_DEADLINE")
            response = transport(request, timeout=max(0.1, min(float(timeout), request_timeout, 4.0, remaining)))
            if _transport_domain(str(response.geturl())) != _transport_domain(request.full_url):
                response.close()
                raise CollectorError("REDIRECT_FORBIDDEN")
            return _BudgetResponse(response, deadline)
        except BaseException:
            HTTP_LIMIT.release()
            raise

    return open_request


def _exact_profile(card: dict[str, Any]) -> dict[str, Any] | None:
    """Only already audited full-VIN profiles; prefixes aren't trim proof."""
    vin = _identity_value(card.get("vin"))
    profiles = [profile for profile in profile_library.PROFILES if vin in profile.get("exact_vins", ())]
    return profiles[0] if len(profiles) == 1 else None


def _strict_vpic_identity(card: dict[str, Any], identity: dict[str, Any]) -> bool:
    # Do not accept a decoder's make-only fallback for non-US VINs.
    return bool(
        all(str(identity.get(key) or "").strip() for key in ("Make", "Model", "ModelYear"))
        and str(identity.get("ErrorCode") or "").strip() == "0"
        and card.get("brand") and card.get("model") and card.get("year")
        and policy.vpic_identity_matches(card, identity)
    )


def collect(card: dict[str, Any], *, deadline_seconds: float = 18.0,
            opener: Callable[..., Any] | None = None, request_timeout: float = 4.0,
            emit_source: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Return evidence and honest outcomes for all ten approved positions.

    Curated values are dated snapshots, never counted as a fresh HTTP success.
    Unknown VINs without an audited trim profile get vPIC identity facts only.
    Generic model-range equipment is not promoted to instance equipment.
    The supplied opener is for deterministic tests; production uses guarded
    same-domain HTTPS redirects and bypasses legacy process-lifetime caches.
    """
    uid = str(card.get("car_uid") or "")
    vin = _identity_value(card.get("vin"))
    if not UID_RE.fullmatch(uid):
        raise CollectorError("INVALID_UID")
    checked_at = _utc()
    deadline = time.monotonic() + max(1.0, min(float(deadline_seconds), 30.0))
    current_opener = _bounded_opener(deadline, opener, max(0.1, float(request_timeout)))
    profile = _exact_profile(card)
    curated = [fact for fact in policy.profile_facts(profile) if fact.source_domain in APPROVED_DOMAINS]
    facts = list(curated)
    sources: dict[str, dict[str, Any]] = {}
    for sid, name, domain in SOURCES:
        count = sum(fact.source_domain == domain for fact in curated)
        network_state = "NOT_STARTED" if domain in HTTP_DOMAINS else "NOT_CONFIGURED"
        sources[sid] = {
            "name": name, "domain": domain, "checked_at": checked_at,
            "status": "CURATED" if count else network_state,
            "network_status": network_state, "fresh_facts": 0,
            "curated_facts": count,
            "curated_at": str(profile_library.AUDIT_DATE) if count else None,
        }
    def emit(sid):
        if emit_source:
            domain = sources[sid]["domain"]
            emit_source(sid, dict(sources[sid]), policy.deduplicate(fact for fact in facts if fact.source_domain == domain))
    for sid in sources:
        emit(sid)
    vpic = sources["nhtsa_vpic"]
    try:
        if not policy.VIN_RE.fullmatch(vin):
            vpic.update(status="NOT_APPLICABLE", network_status="NO_17_CHARACTER_VIN")
        else:
            identity, found = policy.decode_vpic(card, opener=current_opener)
            if not _strict_vpic_identity(card, identity):
                vpic.update(status="NO_CONFIDENT_MATCH", network_status="IDENTITY_MISMATCH")
            else:
                facts.extend(found)
                vpic.update(status="FRESH" if found else "NO_DATA", network_status="HTTP_OK", fresh_facts=len(found))
    except Exception as exc:
        vpic.update(status="ERROR", network_status="ERROR", error=type(exc).__name__)
    emit("nhtsa_vpic")
    for sid, _name, domain in SOURCES:
        if domain not in CATALOG_DOMAINS:
            continue
        outcome = sources[sid]
        urls = list(((profile or {}).get("urls") or {}).get(domain) or ())
        if not urls:
            outcome.update(status="NO_CONFIDENT_MATCH", network_status="NO_AUDITED_TRIM_URL")
            emit(sid)
            continue
        attempts = []
        accepted = []
        for url in urls[:1]:
            if time.monotonic() >= deadline:
                attempts.append({"status": "DEADLINE"})
                break
            try:
                body = policy._open_bytes(url, opener=current_opener)
                score, candidates = policy.extract_page_facts(card, url, body)
                # Restrict the generic HTML parser to keys already audited for
                # this exact VIN and this exact source page. This excludes new
                # range-level options unrelated to the actual vehicle.
                anchored = {fact.field_key: fact.display_value for fact in curated
                            if fact.source_domain == domain and fact.source_url == url}
                accepted = [fact for fact in candidates if fact.field_key in anchored
                            and _normal(fact.display_value) == _normal(anchored[fact.field_key])]
                attempts.append({"url": url, "status": "HTTP_OK", "score": score, "facts": len(accepted)})
                facts.extend(accepted)
            except Exception as exc:
                attempts.append({"url": url, "status": "ERROR", "error": type(exc).__name__})
        outcome.update(
            status="FRESH" if accepted else "CURATED" if outcome["curated_facts"] else "NO_DATA",
            network_status=attempts[-1]["status"] if attempts else "NO_AUDITED_TRIM_URL",
            fresh_facts=len(accepted), attempts=attempts,
        )
        emit(sid)
    # Prefer curated evidence if HTTP disagrees with its audited value: the
    # merge below is conservative too, including for values accepted earlier.
    selected = policy.deduplicate(facts)
    return {"policy_version": POLICY_VERSION, "car_uid": uid, "vin": vin,
            "profile_id": str((profile or {}).get("id") or ""),
            "status": "COMPLETE" if selected else "COMPLETE_EMPTY",
            "facts": selected, "sources": sources, "collected_at": checked_at}


def collect_scheduled(card, request_timeout, emit_source):
    return collect(card, request_timeout=request_timeout, emit_source=emit_source, deadline_seconds=17.0)


def _safe_text(value: Any, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text or len(text) > limit or policy.PRICE_RE.search(text) or BAD_TEXT.search(text):
        raise CollectorError("UNSAFE_VALUE")
    return text


def _list_json(value: Any) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _normal(value: str) -> str:
    # Do not erase punctuation or units: 1.2, 12 and 1-2 must remain distinct.
    return re.sub(r"\s+", " ", value).strip().casefold().replace("ё", "е")


def _signature(label: str) -> str:
    generic = {"auto", "car", "vehicle", "body", "overall", "авто", "автомобиль",
               "автомобиля", "машина", "машины", "общий", "общая", "общее",
               "габаритный", "габаритная"}
    return " ".join(sorted(token for token in re.findall(r"[\w]+", _normal(label)) if token not in generic))


def merge_in_transaction(conn: sqlite3.Connection, card: dict[str, Any],
                         facts: Iterable[dict[str, Any]], *,
                         guard: Callable[[sqlite3.Connection, dict[str, Any]], Any]) -> dict[str, int]:
    """Add facts to the existing sidecar under caller's identity/lease lock.

    Caller must roll back if either guard fails, and commit queue result and
    facts atomically. ``guard`` must raise unless UID, VIN, generation, current
    publication and lease still match. Nothing here opens a writable CRM DB.
    All differing accepted values remain unchanged; conflicts are audited.
    """
    if not conn.in_transaction or not callable(guard):
        raise CollectorError("IDENTITY_LOCKED_TRANSACTION_REQUIRED")
    uid = str(card.get("car_uid") or "")
    if not UID_RE.fullmatch(uid) or not card.get("published"):
        raise CollectorError("PUBLISHED_CARD_REQUIRED")
    _identity_value(card.get("vin"))
    if guard(conn, card) is False:
        raise CollectorError("STALE_IDENTITY_OR_LEASE")
    counts = {"inserted": 0, "merged": 0, "conflicts": 0, "protected": 0, "rejected": 0}
    for fact in facts:
        key = str(fact.get("field_key") or "")
        try:
            if not KEY_RE.fullmatch(key) or key in policy.BLOCKED_PRIMARY_KEYS:
                raise CollectorError("PRIMARY_OR_INVALID_KEY")
            value, label = _safe_text(fact.get("display_value")), _safe_text(fact.get("label_ru"), 120)
            unit = str(fact.get("unit") or "")
            if unit:
                _safe_text(unit, 40)
            category = _safe_text(fact.get("category") or "additional", 80)
            domains = sorted(set(str(domain) for domain in fact.get("source_domains", ()) if domain in APPROVED_DOMAINS))
            urls = sorted(set(str(url) for url in fact.get("source_urls", ()) if _domain(str(url)) in domains))
            domains = sorted(set(_domain(url) for url in urls))
            if not domains or not urls:
                raise CollectorError("NO_APPROVED_PROVENANCE")
            confidence = float(fact.get("confidence") or 0)
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise CollectorError("INVALID_CONFIDENCE")
        except (CollectorError, TypeError, ValueError):
            counts["rejected"] += 1
            continue
        old = conn.execute("SELECT * FROM additional_specification WHERE car_uid=? AND field_key=?", (uid, key)).fetchone()
        meta = conn.execute("SELECT * FROM additional_specification_meta WHERE car_uid=? AND field_key=?", (uid, key)).fetchone()
        old = dict(old) if old else None
        meta = dict(meta) if meta else None
        if ((meta and (bool(meta.get("is_manual")) or not bool(meta.get("is_visible"))))
                or (old and str(old.get("source") or "").upper().startswith(("MANUAL", "USER", "OPERATOR")))):
            counts["protected"] += 1
            continue
        # A field hidden or manually edited under a legacy alias also wins.
        aliases = conn.execute("SELECT field_key,label_ru,is_manual,is_visible FROM additional_specification_meta WHERE car_uid=? AND field_key<>?", (uid, key)).fetchall()
        if any(_signature(str(row["label_ru"])) == _signature(label) for row in aliases):
            counts["protected"] += 1
            continue
        if old and (_normal(str(old["field_value"])) != _normal(value) or (meta and str(meta.get("unit") or "") != unit)):
            conn.execute("INSERT INTO additional_specification_audit(car_uid,field_key,action,old_value,new_value) VALUES(?,?,?,?,?)",
                         (uid, key, "ISSUE84_CONFLICT_RETAINED", str(old["field_value"]), value))
            counts["conflicts"] += 1
            continue
        if old and not meta:
            # An incompletely migrated row has unknown operator provenance.
            counts["protected"] += 1
            continue
        if old:
            old_domains = _list_json(meta.get("source_domains_json"))
            old_urls = _list_json(meta.get("source_urls_json"))
            all_domains, all_urls = sorted(set(old_domains + domains)), sorted(set(old_urls + urls))
            # Keep all old provenance, including retired source domains; don't
            # relabel curated snapshots as freshly verified facts.
            conn.execute("UPDATE additional_specification_meta SET evidence_count=?,source_domains_json=?,source_urls_json=?,updated_at=? WHERE car_uid=? AND field_key=?",
                         (max(int(meta.get("evidence_count") or 0), len(all_domains)), json.dumps(all_domains), json.dumps(all_urls), _utc(), uid, key))
            counts["merged"] += 1
            continue
        conn.execute("INSERT INTO additional_specification(car_uid,field_key,field_value,normalized_value,source,source_url,confidence,is_price_field) VALUES(?,?,?,?,?,?,?,0)",
                     (uid, key, value, _normal(value), "AUTO_ISSUE84", urls[0], confidence))
        conn.execute("INSERT INTO additional_specification_meta(car_uid,field_key,label_ru,category,unit,evidence_count,source_domains_json,source_urls_json,verification_status,model_match_score,is_manual,is_visible,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,0,1,?)",
                     (uid, key, label, category, unit, len(domains), json.dumps(domains), json.dumps(urls), "VERIFIED_ISSUE84", confidence, _utc()))
        counts["inserted"] += 1
    if guard(conn, card) is False:
        raise CollectorError("STALE_IDENTITY_OR_LEASE")
    return counts


class IdentityError(RuntimeError):
    pass


def ensure_identity_schema(conn: sqlite3.Connection) -> None:
    # Individual execute calls preserve an already-open caller transaction.
    conn.execute("""CREATE TABLE IF NOT EXISTS spec84_fact_bindings(
        car_uid TEXT PRIMARY KEY, vin TEXT NOT NULL, generation INTEGER NOT NULL,
        bound_at TEXT NOT NULL, CHECK(generation>=1))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS spec84_fact_history(
        id INTEGER PRIMARY KEY, car_uid TEXT NOT NULL, vin TEXT,
        generation INTEGER, facts_json TEXT NOT NULL, meta_json TEXT NOT NULL,
        reason TEXT NOT NULL, archived_at TEXT NOT NULL)""")


def _identity(card: dict[str, Any], generation: int) -> tuple[str, str, int]:
    uid = str(card.get("car_uid") or "")
    vin = str(card.get("vin") or "").strip().upper()
    if (not re.fullmatch(r"UA-\d{4,6}", uid)
            or not re.fullmatch(r"[A-Z0-9-]{5,30}", vin)
            or isinstance(generation, bool) or not isinstance(generation, int)
            or generation < 1):
        raise IdentityError("INVALID_GENERATION_IDENTITY")
    return uid, vin, generation


def ensure_binding(conn: sqlite3.Connection, card: dict[str, Any], generation: int,
                   *, legacy_vin: str | None = None) -> dict[str, Any]:
    """Bind active facts to one generation; never infer unknown legacy identity.

    ``legacy_vin`` is supplied only from an inspected existing VIN job/history
    that actually describes the active legacy facts. It must not simply be
    copied from the current CRM VIN. Missing baseline evidence with existing
    facts raises without modifying any row; the installer must resolve it.
    """
    if not conn.in_transaction:
        raise IdentityError("IDENTITY_LOCKED_TRANSACTION_REQUIRED")
    uid, vin, generation = _identity(card, generation)
    row = conn.execute("SELECT * FROM spec84_fact_bindings WHERE car_uid=?", (uid,)).fetchone()
    previous = dict(row) if row else None
    if previous:
        old_generation = int(previous["generation"])
        if generation < old_generation:
            raise IdentityError("GENERATION_REGRESSION")
        if generation == old_generation:
            if previous["vin"] != vin:
                raise IdentityError("VIN_CHANGED_WITHOUT_NEW_GENERATION")
            return {"status": "UNCHANGED", "archived_facts": 0, "archived_meta": 0}
    facts = [dict(item) for item in conn.execute(
        "SELECT * FROM additional_specification WHERE car_uid=? ORDER BY id", (uid,))]
    meta = [dict(item) for item in conn.execute(
        "SELECT * FROM additional_specification_meta WHERE car_uid=? ORDER BY field_key", (uid,))]
    old_vin = str(previous["vin"]) if previous else str(legacy_vin or "").strip().upper() or None
    if previous is None and old_vin is None and (facts or meta):
        raise IdentityError("LEGACY_FACT_IDENTITY_UNPROVEN")
    retain_baseline = previous is None and old_vin == vin
    archived_facts = archived_meta = 0
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    status = "BASELINE_RETAINED" if retain_baseline else "NEW_EMPTY_BINDING"
    if not retain_baseline and (facts or meta):
        facts_json = json.dumps(facts, ensure_ascii=False, sort_keys=True)
        meta_json = json.dumps(meta, ensure_ascii=False, sort_keys=True)
        reason = "VIN_GENERATION_CHANGED" if previous else "BASELINE_IDENTITY_UNPROVEN"
        saved = conn.execute("""INSERT INTO spec84_fact_history
            (car_uid,vin,generation,facts_json,meta_json,reason,archived_at)
            VALUES(?,?,?,?,?,?,?)""",
            (uid, old_vin, int(previous["generation"]) if previous else None,
             facts_json, meta_json, reason, now))
        readback = conn.execute("SELECT facts_json,meta_json FROM spec84_fact_history WHERE id=?",
                                (saved.lastrowid,)).fetchone()
        if readback is None or json.loads(readback[0]) != facts or json.loads(readback[1]) != meta:
            raise IdentityError("ARCHIVE_READBACK_MISMATCH")
        # These active projection rows may never remain associated with a new
        # VIN. The complete rows, including manual/hidden flags, are preserved
        # above and the entire change rolls back on any later error.
        conn.execute("DELETE FROM additional_specification_meta WHERE car_uid=?", (uid,))
        conn.execute("DELETE FROM additional_specification WHERE car_uid=?", (uid,))
        archived_facts, archived_meta = len(facts), len(meta)
        status = "ARCHIVED_NEW_EMPTY_BINDING"
    conn.execute("""INSERT INTO spec84_fact_bindings(car_uid,vin,generation,bound_at)
        VALUES(?,?,?,?) ON CONFLICT(car_uid) DO UPDATE SET
        vin=excluded.vin,generation=excluded.generation,bound_at=excluded.bound_at""",
        (uid, vin, generation, now))
    return {"status": status, "archived_facts": archived_facts, "archived_meta": archived_meta,
            "retained_facts": len(facts) if retain_baseline else 0}
