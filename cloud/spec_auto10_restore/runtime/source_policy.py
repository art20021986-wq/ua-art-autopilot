#!/usr/bin/env python3
"""Ten-source technical specification policy for UA ART.

The VIN is the trigger and identity anchor.  Public technical facts may come
only from the ten sources below.  Search engines are used only to discover a
page URL and are never treated as evidence.

No purchase/auction/sale price is returned by this module.  Primary CRM fields
remain operator-owned and are intentionally absent from the output mapping.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import email.utils
import html
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Callable, Iterable

import profile_library


POLICY_VERSION = "UA-ART-SPEC-AUTO10-RESTORE-V1"
SOURCE_DOMAINS = (
    "vpic.nhtsa.dot.gov",
    "auto-data.net",
    "carwiki.co.kr",
    "auto.danawa.com",
    "carisyou.com",
    "ultimatespecs.com",
    "automobile-catalog.com",
    "cars-data.com",
    "carfolio.com",
    "encycarpedia.com",
)
# Conflicts are resolved by the most reliable applicable source, never by
# averaging incompatible values.  Korean domestic catalogues outrank generic
# aggregators for Korean-market trims; vPIC remains authoritative only after
# its strict VIN identity check succeeds.
SOURCE_PRIORITY = {
    "vpic.nhtsa.dot.gov": 100,
    "auto.danawa.com": 96,
    "carwiki.co.kr": 94,
    "carisyou.com": 91,
    "auto-data.net": 90,
    "ultimatespecs.com": 82,
    "automobile-catalog.com": 80,
    "cars-data.com": 76,
    "carfolio.com": 75,
    "encycarpedia.com": 70,
}
DISCOVERY_DOMAIN = "html.duckduckgo.com"
MAX_RESPONSE_BYTES = 2_000_000
HTTP_TIMEOUT = max(5, min(30, int(os.environ.get("UA_ART_SPEC_HTTP_TIMEOUT", "15"))))
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
VIN_YEAR_CODES = {
    **{str(year - 2000): year for year in range(2001, 2010)},
    **{code: year for code, year in zip("ABCDEFGHJKLMNPRSTVWXY", range(2010, 2031))},
}
PRICE_RE = re.compile(
    r"(?:[$€£₴₽₩¥]|\b(?:usd|eur|uah|rub|krw|price|cost|auction|wholesale|"
    r"dealer|purchase|acquisition|margin|markup|sale|цена|вартість|стоимость|"
    r"закуп|себесто|оптов|аукцион|만원|가격|금액|원)\b)",
    re.IGNORECASE,
)

# These values already belong to the operator's primary CRM card.  They are
# useful for matching, but the enrichment service must never write them.
BLOCKED_PRIMARY_KEYS = {
    "brand", "make", "manufacturer", "model", "year", "model_year",
    "generation", "body", "body_type", "mileage", "odometer", "vin",
    "fuel", "fuel_type", "engine", "engine_cc", "engine_volume",
    "transmission", "gearbox", "drive", "drivetrain", "color", "price",
    "status", "stage", "container", "eta", "arrival_date", "description",
}
profile_library.validate_library(SOURCE_DOMAINS, BLOCKED_PRIMARY_KEYS)

CACHE_MAX_ENTRIES = 64
BODY_CACHE_TTL_SECONDS = 3600
FAILURE_BACKOFF_SECONDS = 30
FAILURE_BACKOFF_MAX_SECONDS = 900
_CACHE_LOCK = threading.RLock()


@dataclasses.dataclass(frozen=True)
class _CachedBody:
    body: bytes
    expires_at: float
    fetched_at: str


@dataclasses.dataclass(frozen=True)
class _FetchFailure:
    code: str
    retry_at: float
    attempts: int


_BODY_CACHE: dict[str, _CachedBody] = {}
_FETCH_FAILURE_CACHE: dict[str, _FetchFailure] = {}


class _FetchedBody(bytes):
    """Bytes carrying retrieval provenance without changing parser callers."""

    def __new__(cls, body: bytes, origin: str, fetched_at: str) -> "_FetchedBody":
        result = super().__new__(cls, body)
        result.evidence_origin = origin
        result.retrieved_at = fetched_at
        return result


@dataclasses.dataclass(frozen=True)
class Fact:
    field_key: str
    label_ru: str
    category: str
    display_value: str
    unit: str
    confidence: float
    source_domain: str
    source_url: str
    evidence_origin: str = "supplied_page"
    retrieved_at: str = ""
    curated_audited_on: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class SourcePolicyError(RuntimeError):
    pass


def normalize_vin(value: Any) -> str:
    vin = re.sub(r"[\s\-]+", "", str(value or "")).upper()
    if not VIN_RE.fullmatch(vin):
        raise SourcePolicyError("INVALID_VIN")
    return vin


def normalize_identity(value: Any) -> str:
    """Recognize VIN or a narrow frame-number syntax; never infer a trim.

    Frame recognition only permits storage and review.  It does not establish
    fuel, equipment or a catalogue match, and must never be sent to vPIC.
    """
    value = re.sub(r"\s+", "", str(value or "")).upper()
    try:
        return normalize_vin(value)
    except SourcePolicyError:
        if re.fullmatch(r"(?:NHP10|HE12|E12|SNE12|E13|ZVW30|ZVW35|ZVW50|ZVW51|ZVW55)-[0-9]{6,7}", value):
            return value
        raise SourcePolicyError("INVALID_VIN_OR_UNRECOGNIZED_FRAME") from None


def vin_model_year(value: Any) -> int | None:
    """Return a modern VIN model year when position 10 is year-coded.

    Some European-market VINs use a numeric character in this position for a
    chassis attribute rather than a model year.  Numeric years that would be
    implausibly old for the card are therefore ignored by ``lookup_years``.
    The result is lookup metadata only and is never written to the CRM.
    """
    vin = normalize_vin(value)
    return VIN_YEAR_CODES.get(vin[9])


def lookup_years(car: dict[str, Any]) -> list[str]:
    crm_match = re.search(r"(?:19|20)\d{2}", str(car.get("year") or car.get("model_year") or ""))
    crm_year = int(crm_match.group(0)) if crm_match else None
    try:
        decoded = vin_model_year(car.get("vin"))
    except SourcePolicyError:
        decoded = None
    years: list[int] = []
    # A VIN model year may legitimately differ from the production/calendar
    # year by one.  A large discrepancy is retained as a lookup candidate only
    # for alphabetic modern year codes (for example the current UA-0016 card),
    # while the operator-owned CRM value remains unchanged.
    if decoded and (not crm_year or decoded >= 2010 or abs(decoded - crm_year) <= 1):
        years.append(decoded)
    if crm_year:
        years.extend((crm_year, crm_year - 1, crm_year + 1))
    return [str(year) for year in dict.fromkeys(years) if 1980 <= year <= 2035]


def source_domain(url: str) -> str | None:
    try:
        parsed = urllib.parse.urlsplit(str(url))
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    for allowed in SOURCE_DOMAINS:
        if host == allowed or host.endswith("." + allowed):
            return allowed
    return None


def _fetch_domain(url: str) -> str | None:
    domain = source_domain(url)
    if domain:
        return domain
    try:
        parsed = urllib.parse.urlsplit(str(url))
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme == "https" and not parsed.username and not parsed.password and host == DISCOVERY_DOMAIN:
        return DISCOVERY_DOMAIN
    return None


def _clean(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _norm(value: Any) -> str:
    text = _clean(value).casefold().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-яіїєґ가-힣]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_profile(car: dict[str, Any]) -> dict[str, Any] | None:
    """Return one exact audited profile, never a fuzzy make/model guess."""
    try:
        vin = normalize_vin(car.get("vin"))
    except SourcePolicyError:
        return None
    # The initial fleet was individually audited.  A complete VIN is a
    # stronger identity anchor than free-text CRM labels (LPi is commonly
    # entered as either gas or petrol), so these exact vehicles do not depend
    # on an operator's fuel-label spelling.
    exact = [
        profile for profile in profile_library.PROFILES
        if vin in set(profile.get("exact_vins") or ())
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise SourcePolicyError("AMBIGUOUS_EXACT_VIN_PROFILE")
    # A shared VIN prefix does not establish the year, trim or transmission
    # of a new vehicle.  New identities use discovery and page validation;
    # they never inherit the historical fleet's manually curated facts.
    return None


def identity_context_issues(car: dict[str, Any]) -> list[str]:
    """Reject demonstrated CRM/identity conflicts without replacing CRM data.

    Exact VIN membership identifies a historical profile; it cannot override a
    contradictory current make, model or year. A one-year calendar/model-year
    difference is accepted. Numeric European chassis codes are not treated as
    proof of a conflicting model year. Unknown profiles remain eligible for
    normal source discovery and its independent identity validation.
    """
    issues: list[str] = []
    profile = match_profile(car)
    aliases = {"к5": "k5", "к 5": "k5", "б класса": "b class", "б класс": "b class"}
    brand = _norm(car.get("brand"))
    model = _norm(car.get("model"))
    model = aliases.get(model, model)
    if profile:
        if brand and not any(_norm(token) in brand for token in profile["brand_tokens"]):
            issues.append("CRM_BRAND_DIFFERS_FROM_EXACT_VIN_PROFILE")
        if model and not any(_norm(token) in model for token in profile["model_tokens"]):
            issues.append("CRM_MODEL_DIFFERS_FROM_EXACT_VIN_PROFILE")
    year = re.fullmatch(r"(?:19|20)\d{2}", str(car.get("year") or car.get("model_year") or "").strip())
    try:
        vin = normalize_vin(car.get("vin"))
        inferred = vin_model_year(vin)
    except SourcePolicyError:
        vin, inferred = "", None
    if year and inferred is not None and abs(int(year.group()) - inferred) > 1 and not vin[9].isdigit():
        issues.append("CRM_YEAR_DIFFERS_FROM_INFERRED_VIN_MODEL_YEAR")
    return issues


def profile_facts(profile: dict[str, Any] | None) -> list[Fact]:
    """Expand an audited profile into source-specific facts with provenance."""
    if not profile:
        return []
    result: list[Fact] = []
    urls = profile.get("urls") or {}
    for field_key, item in (profile.get("facts") or {}).items():
        label_ru, category, unit = profile_library.FIELD_DEFS[field_key]
        for domain in item.get("sources") or ():
            source_urls = tuple(urls.get(domain) or ())
            if not source_urls:
                continue
            priority = int(SOURCE_PRIORITY.get(domain, 0))
            result.append(Fact(
                field_key=field_key,
                label_ru=label_ru,
                category=category,
                display_value=_clean(item.get("value")),
                unit=unit,
                confidence=0.94 if priority >= 90 else 0.89,
                source_domain=domain,
                source_url=str(source_urls[0]),
                evidence_origin="curated_profile",
                curated_audited_on=str(profile_library.AUDIT_DATE),
            ))
    return result


def _value_unit(value: str) -> str:
    match = re.search(
        r"(?:^|\s)(л/100\s*км|км/л|km/ℓ|g/km|mm|cm|kg|г/км|мм|см|м|кг|"
        r"л\.с\.?|лс|ps|hp|нм|nm|сек|км/ч|km/h|об\.?/мин\.?|bar|r\d{2})\b",
        value,
        re.IGNORECASE,
    )
    return _clean(match.group(1)) if match else ""


class _VisibleHTML(HTMLParser):
    """Small dependency-free visible-text and table/dl extractor."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.lines: list[str] = []
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None
        self._row: list[str] | None = None
        self._term: list[str] | None = None
        self._definition: list[str] | None = None
        self._last_term = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "form"}:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "dt":
            self._term = []
        elif tag == "dd":
            self._definition = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "form"}:
            if self.skip:
                self.skip -= 1
            return
        if self.skip:
            return
        if tag in {"td", "th"} and self._cell is not None:
            value = _clean(" ".join(self._cell))
            if value and self._row is not None:
                self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if len(self._row) >= 2:
                self.rows.append(self._row)
            self._row = None
        elif tag == "dt" and self._term is not None:
            self._last_term = _clean(" ".join(self._term))
            self._term = None
        elif tag == "dd" and self._definition is not None:
            value = _clean(" ".join(self._definition))
            if self._last_term and value:
                self.rows.append([self._last_term, value])
            self._definition = None

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        value = _clean(data)
        if not value:
            return
        self.lines.append(value)
        if self._cell is not None:
            self._cell.append(value)
        if self._term is not None:
            self._term.append(value)
        if self._definition is not None:
            self._definition.append(value)


def parse_html(value: bytes | str) -> tuple[list[str], list[list[str]]]:
    text = value.decode("utf-8", "replace") if isinstance(value, bytes) else value
    parser = _VisibleHTML()
    parser.feed(text)
    return parser.lines, parser.rows


class _AllowedRedirect(urllib.request.HTTPRedirectHandler):
    """Check the destination before urllib follows a redirect."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        if not _fetch_domain(newurl) or _fetch_domain(newurl) != _fetch_domain(req.full_url):
            raise SourcePolicyError("REDIRECT_DOMAIN_FORBIDDEN")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _retry_after_seconds(headers: Any) -> float:
    value = str((headers or {}).get("Retry-After") or "").strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt.timezone.utc)
        return max(0.0, (when - dt.datetime.now(dt.timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _remember_failure(url: str, code: str, *, retry_after: float = 0.0) -> None:
    with _CACHE_LOCK:
        previous = _FETCH_FAILURE_CACHE.get(url)
        # Limit both exponent and cache size; no background retry/sleep loop.
        attempts = min(10, previous.attempts + 1 if previous else 1)
        delay = min(FAILURE_BACKOFF_MAX_SECONDS, FAILURE_BACKOFF_SECONDS * 2 ** (attempts - 1))
        # An explicit server cooldown is honored even if longer than our cap.
        delay = max(delay, retry_after)
        if url not in _FETCH_FAILURE_CACHE and len(_FETCH_FAILURE_CACHE) >= CACHE_MAX_ENTRIES:
            _FETCH_FAILURE_CACHE.pop(next(iter(_FETCH_FAILURE_CACHE)))
        _FETCH_FAILURE_CACHE[url] = _FetchFailure(code, time.monotonic() + delay, attempts)


def clear_fetch_caches() -> None:
    """Local diagnostic/test reset; successful retries also clear failures."""
    with _CACHE_LOCK:
        _BODY_CACHE.clear()
        _FETCH_FAILURE_CACHE.clear()


def _open_bytes(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = HTTP_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> bytes:
    initial_domain = _fetch_domain(url)
    if not initial_domain:
        raise SourcePolicyError("FETCH_DOMAIN_FORBIDDEN")
    cacheable = (
        method == "GET" and data is None and (opener is None or opener is urllib.request.urlopen)
        and initial_domain != DISCOVERY_DOMAIN
    )
    if cacheable:
        with _CACHE_LOCK:
            now = time.monotonic()
            cached = _BODY_CACHE.get(url)
            if cached and now < cached.expires_at:
                return _FetchedBody(cached.body, "cached_page", cached.fetched_at)
            if cached:
                _BODY_CACHE.pop(url, None)
            failure = _FETCH_FAILURE_CACHE.get(url)
            if failure and now < failure.retry_at:
                raise SourcePolicyError("RETRY_DEFERRED:" + failure.code)
    request_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; UAART-VIN-Spec/1.0)",
        "Accept-Language": "ru,en;q=0.9,ko;q=0.8",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    fetch = (
        urllib.request.build_opener(_AllowedRedirect()).open
        if opener is None or opener is urllib.request.urlopen else opener
    )
    try:
        with fetch(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            final_url = str(getattr(response, "geturl", lambda: url)())
            if _fetch_domain(final_url) != initial_domain:
                raise SourcePolicyError("REDIRECT_DOMAIN_FORBIDDEN")
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if status != 200:
                raise SourcePolicyError("HTTP_%d" % status)
            if len(body) > MAX_RESPONSE_BYTES:
                raise SourcePolicyError("RESPONSE_TOO_LARGE")
    except SourcePolicyError as exc:
        if cacheable:
            _remember_failure(url, str(exc))
        raise
    except urllib.error.HTTPError as exc:
        if cacheable:
            _remember_failure(url, "HTTP_%d" % exc.code, retry_after=_retry_after_seconds(exc.headers))
        raise SourcePolicyError("HTTP_%d" % exc.code) from exc
    except Exception as exc:
        if cacheable:
            _remember_failure(url, "NETWORK_%s" % type(exc).__name__)
        raise SourcePolicyError("NETWORK_%s" % type(exc).__name__) from exc
    fetched_at = _utc_now()
    if cacheable:
        with _CACHE_LOCK:
            _FETCH_FAILURE_CACHE.pop(url, None)
            if url not in _BODY_CACHE and len(_BODY_CACHE) >= CACHE_MAX_ENTRIES:
                _BODY_CACHE.pop(next(iter(_BODY_CACHE)))
            _BODY_CACHE[url] = _CachedBody(body, time.monotonic() + BODY_CACHE_TTL_SECONDS, fetched_at)
    return _FetchedBody(body, "fresh_page", fetched_at)


def _car_tokens(car: dict[str, Any]) -> dict[str, list[str]]:
    brand = _norm(car.get("brand") or car.get("make"))
    model = _norm(car.get("model"))
    fuel = _norm(car.get("fuel") or car.get("fuel_type"))
    try:
        cc = int(float(str(car.get("engine_cc") or car.get("displacement") or 0).replace(" ", "")))
    except (TypeError, ValueError):
        cc = 0
    brand_aliases = [brand] if brand else []
    if "mercedes" in brand:
        brand_aliases += ["mercedes benz", "мерседес", "메르세데스"]
    if brand == "kia" or "киа" in brand:
        brand_aliases += ["kia", "киа", "기아"]
    if "hyundai" in brand or "хендай" in brand or "хюндай" in brand:
        brand_aliases += ["hyundai", "хендай", "хюндай", "현대"]
    model_aliases = [model] if model else []
    if "sonata" in model or "сонат" in model:
        model_aliases += ["sonata", "соната", "쏘나타"]
    if re.search(r"\bk\s*5\b", model):
        model_aliases += ["k5", "k 5", "optima", "оптима", "옵티마"]
    if "b class" in model or "b класс" in model or "б класс" in model:
        model_aliases += ["b class", "b класс", "b-класс", "б класс", "b 170", "b 180", "b 200"]
    if "e 220" in model or "e220" in model or "e class" in model:
        model_aliases += ["e 220", "e220", "e class", "e-class"]
    fuel_aliases = [fuel] if fuel else []
    if any(token in fuel for token in ("lpg", "lpi", "газ")):
        fuel_aliases += ["lpg", "lpi", "lp i", "газ", "엘피지"]
    if "diesel" in fuel or "диз" in fuel:
        fuel_aliases += ["diesel", "дизель", "cdi", "crdi", "e vgt", "디젤"]
    if "benz" in fuel or "бенз" in fuel:
        fuel_aliases += ["gasoline", "бензин", "가솔린"]
    cc_aliases: list[str] = []
    if cc:
        cc_aliases += [str(cc), "%.1f" % (cc / 1000.0)]
        if 1900 <= cc <= 2100:
            cc_aliases += ["2.0", "1999", "1998"]
        elif 1700 <= cc <= 1850:
            cc_aliases += ["1.8", "1796"]
        elif 1600 <= cc <= 1750:
            cc_aliases += ["1.7", "1685"]
    return {
        "brand": sorted({_norm(x) for x in brand_aliases if _norm(x)}),
        "model": sorted({_norm(x) for x in model_aliases if _norm(x)}),
        "fuel": sorted({_norm(x) for x in fuel_aliases if _norm(x)}),
        "cc": sorted({_norm(x) for x in cc_aliases if _norm(x)}),
        "year": lookup_years(car),
    }


def _any_token(text: str, tokens: Iterable[str]) -> bool:
    return any(token and token in text for token in tokens)


def page_match_score(car: dict[str, Any], text: str, domain: str) -> float:
    normalized = _norm(text)
    tokens = _car_tokens(car)
    # A weighted score alone could previously pass another model of the same
    # make (brand + year + cc + fuel = .68). Identity anchors are mandatory.
    if any(not tokens[key] or not _any_token(normalized, tokens[key]) for key in ("brand", "model", "year")):
        return 0.0
    if any(tokens[key] and not _any_token(normalized, tokens[key]) for key in ("fuel", "cc")):
        return 0.0
    score = 0.0
    if tokens["brand"] and _any_token(normalized, tokens["brand"]):
        score += 0.28
    if tokens["model"] and _any_token(normalized, tokens["model"]):
        score += 0.32
    if tokens["year"] and _any_token(normalized, tokens["year"]):
        score += 0.16
    if tokens["cc"] and _any_token(normalized, tokens["cc"]):
        score += 0.12
    if tokens["fuel"] and _any_token(normalized, tokens["fuel"]):
        score += 0.12
    if domain in {"carwiki.co.kr", "auto.danawa.com", "carisyou.com"} and not (
        _any_token(normalized, tokens["year"]) and _any_token(normalized, tokens["model"])
    ):
        return 0.0
    if domain in {"carwiki.co.kr", "auto.danawa.com", "carisyou.com"}:
        if tokens["fuel"] and not _any_token(normalized, tokens["fuel"]):
            return 0.0
        if tokens["cc"] and not _any_token(normalized, tokens["cc"]):
            return 0.0
    return min(score, 1.0)


def _discovery_query(car: dict[str, Any], domain: str) -> str:
    brand = _clean(car.get("brand") or car.get("make"))
    model = _clean(car.get("model"))
    year = (lookup_years(car) or [_clean(car.get("year") or car.get("model_year"))])[0]
    fuel = _clean(car.get("fuel") or car.get("fuel_type"))
    cc = _clean(car.get("engine_cc") or car.get("displacement"))
    if domain in {"carwiki.co.kr", "auto.danawa.com", "carisyou.com"}:
        korean_brand = "기아" if _norm(brand) in {"kia", "киа"} else "현대" if "hyundai" in _norm(brand) else brand
        korean_model = "쏘나타" if "sonata" in _norm(model) else model
        return f'site:{domain} "{year}" "{korean_brand}" "{korean_model}" "{fuel}" "{cc}" 제원'
    return f'site:{domain} "{brand}" "{model}" "{year}" "{fuel}" "{cc}" specifications'


def known_urls(car: dict[str, Any], domain: str) -> list[str]:
    """Small audited seeds for exact high-priority fleet matches.

    Seeds remove search-engine availability as a single point of failure.  The
    normal page matcher and all fact guards still run before any value is used.
    """
    profile = match_profile(car)
    return list(((profile or {}).get("urls") or {}).get(domain) or ())


def _unwrap_result(href: str) -> str | None:
    href = html.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlsplit(href)
    if "uddg=" in parsed.query:
        target = (urllib.parse.parse_qs(parsed.query).get("uddg") or [""])[0]
        href = urllib.parse.unquote(target)
    return href if source_domain(href) else None


def discover_urls(
    car: dict[str, Any],
    domain: str,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
    limit: int = 3,
) -> list[str]:
    if domain not in SOURCE_DOMAINS[1:]:
        return []
    urls = known_urls(car, domain)
    # An exact profile explicitly declares which catalogues apply.  Returning
    # here prevents a search result for another engine/trim from contaminating
    # an already identified vehicle.  Unknown future VINs still search all ten.
    if match_profile(car):
        return urls[:limit]
    endpoint = "https://%s/html/?%s" % (
        DISCOVERY_DOMAIN,
        urllib.parse.urlencode({"q": _discovery_query(car, domain)}),
    )
    try:
        body = _open_bytes(endpoint, opener=opener)
    except Exception:
        if urls:
            return urls[:limit]
        raise
    text = body.decode("utf-8", "replace")
    for href in re.findall(r"href=[\"']([^\"']+)[\"']", text, re.IGNORECASE):
        target = _unwrap_result(href)
        if target and source_domain(target) == domain and target not in urls:
            urls.append(target)
        if len(urls) >= limit:
            break
    return urls


FIELD_MAP = {
    # Auto-Data Russian labels.
    "расход топлива в городе": ("urban_fuel_consumption", "Расход в городе", "consumption"),
    "расход топлива на шоссе": ("highway_fuel_consumption", "Расход на трассе", "consumption"),
    "расход топлива смешанный цикл": ("combined_fuel_consumption", "Смешанный расход", "consumption"),
    "выбросы co2": ("co2_emissions", "Выбросы CO₂", "ecology"),
    "экологический стандарт": ("emission_standard", "Экологический стандарт", "ecology"),
    "стандарт выбросов": ("emission_standard", "Экологический стандарт", "ecology"),
    "время разгона 0 100 км ч": ("acceleration_0_100", "Разгон 0–100 км/ч", "dynamics"),
    "максимальная скорость": ("maximum_speed", "Максимальная скорость", "dynamics"),
    "мощность": ("maximum_power", "Максимальная мощность", "engine"),
    "мощность на литр рабочего объема": ("specific_power", "Удельная мощность", "engine"),
    "крутящий момент": ("maximum_torque", "Максимальный крутящий момент", "engine"),
    "компоновка двигателя": ("engine_layout", "Расположение двигателя", "engine"),
    "модель код двигателя": ("engine_code", "Код двигателя", "engine"),
    "количество цилиндров": ("cylinders", "Количество цилиндров", "engine"),
    "конфигурация двигателя": ("engine_configuration", "Конфигурация двигателя", "engine"),
    "диаметр цилиндра": ("cylinder_bore", "Диаметр цилиндра", "engine"),
    "ход поршня": ("piston_stroke", "Ход поршня", "engine"),
    "степень сжатия": ("compression_ratio", "Степень сжатия", "engine"),
    "количество клапанов на цилиндр": ("valves_per_cylinder", "Клапанов на цилиндр", "engine"),
    "система впрыска топлива": ("fuel_injection", "Система впрыска", "engine"),
    "тип наддува": ("aspiration", "Тип наддува", "engine"),
    "газораспределительный механизм": ("valvetrain", "Газораспределительный механизм", "engine"),
    "количество масла в двигателе": ("engine_oil_capacity", "Объём масла", "capacity"),
    "охлаждающая жидкость": ("coolant_capacity", "Объём охлаждающей жидкости", "capacity"),
    "снаряженная масса автомобиля": ("kerb_weight", "Снаряжённая масса", "weight"),
    "допустимая полная масса": ("gross_weight", "Допустимая полная масса", "weight"),
    "максимальная грузоподъемность": ("payload", "Грузоподъёмность", "weight"),
    "объем багажника минимальный": ("boot_capacity", "Объём багажника", "capacity"),
    "объем багажника максимальный": ("boot_capacity_maximum", "Максимальный объём багажника", "capacity"),
    "объем топливного бака": ("fuel_tank_capacity", "Объём топливного бака", "capacity"),
    "длина": ("length", "Длина", "dimensions"),
    "ширина": ("width", "Ширина", "dimensions"),
    "высота": ("height", "Высота", "dimensions"),
    "колесная база": ("wheelbase", "Колёсная база", "dimensions"),
    "колея передняя": ("front_track", "Передняя колея", "dimensions"),
    "колея задняя": ("rear_track", "Задняя колея", "dimensions"),
    "дорожный просвет": ("ground_clearance", "Дорожный просвет", "dimensions"),
    "коэффициент аэродинамический лобового сопротивления c x": ("drag_coefficient", "Коэффициент аэродинамического сопротивления", "dynamics"),
    "диаметр разворота": ("turning_circle", "Диаметр разворота", "steering"),
    "тип передней подвески": ("front_suspension", "Передняя подвеска", "suspension"),
    "тип задней подвески": ("rear_suspension", "Задняя подвеска", "suspension"),
    "передние тормоза": ("front_brakes", "Передние тормоза", "brakes"),
    "задние тормоза": ("rear_brakes", "Задние тормоза", "brakes"),
    "тип рулевого управления": ("steering_type", "Рулевое управление", "steering"),
    "усилитель руля": ("power_steering", "Усилитель руля", "steering"),
    "количество передач": ("number_of_gears", "Количество передач", "transmission_detail"),
    "размер шин": ("tyre_size", "Размер шин", "wheels"),
    "размер дисков": ("wheel_size", "Размер дисков", "wheels"),
    # Auto-Data English labels (the site may canonicalize a localized URL).
    "fuel consumption economy urban": ("urban_fuel_consumption", "Расход в городе", "consumption"),
    "fuel consumption economy extra urban": ("highway_fuel_consumption", "Расход на трассе", "consumption"),
    "fuel consumption economy combined": ("combined_fuel_consumption", "Смешанный расход", "consumption"),
    "co2 emissions": ("co2_emissions", "Выбросы CO₂", "ecology"),
    "emission standard": ("emission_standard", "Экологический стандарт", "ecology"),
    "acceleration 0 100 km h": ("acceleration_0_100", "Разгон 0–100 км/ч", "dynamics"),
    "maximum speed": ("maximum_speed", "Максимальная скорость", "dynamics"),
    "power": ("maximum_power", "Максимальная мощность", "engine"),
    "torque": ("maximum_torque", "Максимальный крутящий момент", "engine"),
    "engine layout": ("engine_layout", "Расположение двигателя", "engine"),
    "engine model code": ("engine_code", "Код двигателя", "engine"),
    "number of cylinders": ("cylinders", "Количество цилиндров", "engine"),
    "engine configuration": ("engine_configuration", "Конфигурация двигателя", "engine"),
    "cylinder bore": ("cylinder_bore", "Диаметр цилиндра", "engine"),
    "piston stroke": ("piston_stroke", "Ход поршня", "engine"),
    "compression ratio": ("compression_ratio", "Степень сжатия", "engine"),
    "number of valves per cylinder": ("valves_per_cylinder", "Клапанов на цилиндр", "engine"),
    "fuel injection system": ("fuel_injection", "Система впрыска", "engine"),
    "engine aspiration": ("aspiration", "Тип наддува", "engine"),
    "engine oil capacity": ("engine_oil_capacity", "Объём масла", "capacity"),
    "coolant": ("coolant_capacity", "Объём охлаждающей жидкости", "capacity"),
    "kerb weight": ("kerb_weight", "Снаряжённая масса", "weight"),
    "maximum weight": ("gross_weight", "Допустимая полная масса", "weight"),
    "maximum permissible weight": ("gross_weight", "Допустимая полная масса", "weight"),
    "trunk boot space minimum": ("boot_capacity", "Объём багажника", "capacity"),
    "trunk boot space maximum": ("boot_capacity_maximum", "Максимальный объём багажника", "capacity"),
    "maximum trunk space": ("boot_capacity_maximum", "Максимальный объём багажника", "capacity"),
    "fuel tank capacity": ("fuel_tank_capacity", "Объём топливного бака", "capacity"),
    "length": ("length", "Длина", "dimensions"),
    "width": ("width", "Ширина", "dimensions"),
    "height": ("height", "Высота", "dimensions"),
    "wheelbase": ("wheelbase", "Колёсная база", "dimensions"),
    "front track": ("front_track", "Передняя колея", "dimensions"),
    "rear back track": ("rear_track", "Задняя колея", "dimensions"),
    "ground clearance": ("ground_clearance", "Дорожный просвет", "dimensions"),
    "drag coefficient": ("drag_coefficient", "Коэффициент аэродинамического сопротивления", "dynamics"),
    "minimum turning circle": ("turning_circle", "Диаметр разворота", "steering"),
    "front suspension": ("front_suspension", "Передняя подвеска", "suspension"),
    "rear suspension": ("rear_suspension", "Задняя подвеска", "suspension"),
    "front brakes": ("front_brakes", "Передние тормоза", "brakes"),
    "rear brakes": ("rear_brakes", "Задние тормоза", "brakes"),
    "steering type": ("steering_type", "Рулевое управление", "steering"),
    "power steering": ("power_steering", "Усилитель руля", "steering"),
    "number of gears": ("number_of_gears", "Количество передач", "transmission_detail"),
    "gearbox number of gears": ("number_of_gears", "Количество передач", "transmission_detail"),
    "doors": ("doors", "Количество дверей", "capacity"),
    "seats": ("seats", "Количество мест", "capacity"),
    "tires size": ("tyre_size", "Размер шин", "wheels"),
    "wheel rims size": ("wheel_size", "Размер дисков", "wheels"),
    # CarWiki Korean labels.
    "전장": ("length", "Длина", "dimensions"),
    "전폭": ("width", "Ширина", "dimensions"),
    "전고": ("height", "Высота", "dimensions"),
    "축간거리": ("wheelbase", "Колёсная база", "dimensions"),
    "엔진형식": ("engine_code", "Тип двигателя", "engine"),
    "최고출력": ("maximum_power", "Максимальная мощность", "engine"),
    "최대토크": ("maximum_torque", "Максимальный крутящий момент", "engine"),
    "연료탱크": ("fuel_tank_capacity", "Объём топливного бака", "capacity"),
    "복합연비": ("combined_fuel_economy", "Смешанный расход", "consumption"),
    "도심연비": ("urban_fuel_economy", "Расход в городе", "consumption"),
    "고속도로연비": ("highway_fuel_economy", "Расход на трассе", "consumption"),
    "co2 배출량": ("co2_emissions", "Выбросы CO₂", "ecology"),
    "공차중량": ("kerb_weight", "Снаряжённая масса", "weight"),
    "변속기": ("number_of_gears", "Количество передач", "transmission_detail"),
    "도어": ("doors", "Количество дверей", "capacity"),
    "승차정원": ("seats", "Количество мест", "capacity"),
    "타이어": ("tyre_size", "Размер шин", "wheels"),
}


def _field_mapping(label: Any) -> tuple[str, str, str] | None:
    normalized = _norm(label)
    mapping = FIELD_MAP.get(normalized)
    if mapping:
        return mapping
    # Catalogues commonly suffix the test cycle or parenthetical notes.
    normalized = re.sub(r"\b(?:nedc|wltp|eu|combined cycle)\b.*$", "", normalized).strip()
    return FIELD_MAP.get(normalized)


def _pairs(lines: list[str], rows: list[list[str]]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for row in rows:
        label = _clean(row[0])
        value = _clean(" ".join(row[1:]))
        if label and value:
            found.append((label, value))
    for index, line in enumerate(lines[:-1]):
        if _field_mapping(line):
            value = _clean(lines[index + 1])
            if value:
                found.append((line, value))
    unique: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for label, value in found:
        signature = (_norm(label), _norm(value))
        if signature not in seen:
            seen.add(signature)
            unique.append((label, value))
    return unique


def _carwiki_exact_segment_pairs(
    car: dict[str, Any], lines: list[str]
) -> list[tuple[str, str]]:
    """Return pairs from one exact CarWiki powertrain section, if provable.

    A model-year page may list dozens of trims.  We anchor on the structured
    fuel row and require the displacement row in the same nearest `제원`
    (specification) section before allowing engine/economy facts.
    """
    tokens = _car_tokens(car)
    try:
        wanted_cc = int(car.get("engine_cc") or 0)
    except (TypeError, ValueError):
        wanted_cc = 0
    candidates: list[tuple[int, list[str]]] = []
    normalized = [_norm(line) for line in lines]
    for index, label in enumerate(normalized[:-1]):
        if label != "연료" or not _any_token(normalized[index + 1], tokens["fuel"]):
            continue
        start = 0
        for cursor in range(index - 1, -1, -1):
            if normalized[cursor] == "제원":
                start = cursor + 1
                break
        end = len(lines)
        for cursor in range(index + 2, len(lines)):
            if normalized[cursor] in {"기본사양", "제원"}:
                end = cursor
                break
        segment = lines[start:end]
        segment_norm = normalized[start:end]
        cc_match = wanted_cc == 0
        for cursor, item in enumerate(segment_norm[:-1]):
            if item != "배기량":
                continue
            digits = re.sub(r"\D", "", segment[cursor + 1])
            if digits:
                try:
                    cc_match = abs(int(digits[:4]) - wanted_cc) <= 60
                except ValueError:
                    cc_match = False
            if cc_match:
                break
        if cc_match:
            candidates.append((end - start, segment))
    if not candidates:
        return []
    # Prefer the tightest valid section; a wider window is more likely to
    # include the following trim on malformed legacy markup.
    _, segment = min(candidates, key=lambda item: item[0])
    found: list[tuple[str, str]] = []
    for index, line in enumerate(segment[:-1]):
        if _field_mapping(line):
            value = _clean(segment[index + 1])
            if value:
                found.append((line, value))
    return _pairs([], [[label, value] for label, value in found])


def extract_page_facts(
    car: dict[str, Any],
    url: str,
    body: bytes,
) -> tuple[float, list[Fact]]:
    domain = source_domain(url)
    if domain not in set(SOURCE_DOMAINS[1:]):
        return 0.0, []
    lines, rows = parse_html(body)
    joined = "\n".join(lines)
    score = page_match_score(car, joined[:160_000], domain)
    threshold = 0.68 if domain in {"carwiki.co.kr", "auto.danawa.com", "carisyou.com"} else 0.64
    if score < threshold:
        return score, []
    all_pairs = _pairs(lines, rows)
    exact_carwiki_pairs = _carwiki_exact_segment_pairs(car, lines) if domain == "carwiki.co.kr" else []
    exact_carwiki_signatures = {(_norm(label), _norm(value)) for label, value in exact_carwiki_pairs}
    result: list[Fact] = []
    for label, raw_value in all_pairs:
        mapping = _field_mapping(label)
        value = _clean(raw_value)
        if not mapping or not value or len(value) > 400 or PRICE_RE.search(value):
            continue
        field_key, label_ru, category = mapping
        if field_key in BLOCKED_PRIMARY_KEYS:
            continue
        # Generation-wide dimensions are safe.  Every other CarWiki value must
        # belong to the exact structured fuel+displacement segment above.
        if (
            domain == "carwiki.co.kr"
            and category != "dimensions"
            and (_norm(label), _norm(value)) not in exact_carwiki_signatures
        ):
            continue
        confidence = 0.91 if domain == "auto-data.net" else 0.88
        if category == "dimensions":
            confidence += 0.03
        result.append(Fact(
            field_key=field_key,
            label_ru=label_ru,
            category=category,
            display_value=value,
            unit=_value_unit(value),
            confidence=min(confidence, 0.97),
            source_domain=domain,
            source_url=url,
            evidence_origin=getattr(body, "evidence_origin", "supplied_page"),
            retrieved_at=getattr(body, "retrieved_at", ""),
        ))
    return score, result


VPIC_FIELD_MAP = {
    "EngineCylinders": ("cylinders", "Количество цилиндров", "engine"),
    "EngineConfiguration": ("engine_configuration", "Конфигурация двигателя", "engine"),
    "EngineModel": ("engine_code", "Код двигателя", "engine"),
    "Turbo": ("turbo", "Турбонаддув", "engine"),
    "ValveTrainDesign": ("valvetrain", "Газораспределительный механизм", "engine"),
    "PlantCountry": ("plant_country", "Страна производства", "additional"),
    "PlantCity": ("plant_city", "Город производства", "additional"),
    "BodyClass": ("body_class_detail", "Класс кузова", "additional"),
    "Doors": ("doors", "Количество дверей", "capacity"),
    "SeatRows": ("seat_rows", "Рядов сидений", "capacity"),
    "Seats": ("seats", "Количество мест", "capacity"),
    "GVWR": ("gross_weight_rating", "Категория полной массы", "weight"),
}


def decode_vpic(
    car: dict[str, Any],
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> tuple[dict[str, Any], list[Fact]]:
    vin = normalize_vin(car.get("vin"))
    year = (lookup_years(car) or [""])[0]
    url = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/%s?%s" % (
        urllib.parse.quote(vin, safe=""),
        urllib.parse.urlencode({"format": "json", "modelyear": year}) if year else "format=json",
    )
    body = _open_bytes(url, opener=opener)
    payload = json.loads(body.decode("utf-8"))
    rows = payload.get("Results") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise SourcePolicyError("VPIC_RESULT_INVALID")
    data = rows[0]
    facts: list[Fact] = []
    for source_key, mapping in VPIC_FIELD_MAP.items():
        value = _clean(data.get(source_key))
        if not value or value.lower() in {"not applicable", "0", "null"} or PRICE_RE.search(value):
            continue
        field_key, label_ru, category = mapping
        facts.append(Fact(
            field_key=field_key,
            label_ru=label_ru,
            category=category,
            display_value=value,
            unit=_value_unit(value),
            confidence=0.96,
            source_domain="vpic.nhtsa.dot.gov",
            source_url=url,
            evidence_origin=getattr(body, "evidence_origin", "supplied_page"),
            retrieved_at=getattr(body, "retrieved_at", ""),
        ))
    identity = {key: _clean(data.get(key)) for key in ("Make", "Model", "ModelYear", "Manufacturer")}
    identity["ErrorCode"] = _clean(data.get("ErrorCode"))
    return identity, facts


def vpic_identity_matches(car: dict[str, Any], identity: dict[str, Any]) -> bool:
    error_code = _clean(identity.get("ErrorCode"))
    if not error_code or any(part.strip() not in {"0"} for part in error_code.split(",")):
        return False
    tokens = _car_tokens(car)
    make = _norm(identity.get("Make") or identity.get("Manufacturer"))
    model = _norm(identity.get("Model"))
    year = re.sub(r"\D", "", str(identity.get("ModelYear") or ""))[:4]
    if not make or not tokens["brand"] or not _any_token(make, tokens["brand"]):
        return False
    if not model or not tokens["model"] or not _any_token(model, tokens["model"]):
        return False
    if not year or not tokens["year"] or year not in tokens["year"]:
        return False
    return True


def deduplicate(facts: Iterable[Fact]) -> list[dict[str, Any]]:
    origin_priority = {"fresh_page": 3, "cached_page": 2, "supplied_page": 1, "curated_profile": 0}
    grouped: dict[str, list[Fact]] = {}
    for fact in facts:
        if fact.field_key in BLOCKED_PRIMARY_KEYS or PRICE_RE.search(fact.display_value):
            continue
        grouped.setdefault(fact.field_key, []).append(fact)
    result: list[dict[str, Any]] = []
    for key in sorted(grouped):
        candidates = grouped[key]
        by_value: dict[str, list[Fact]] = {}
        for fact in candidates:
            by_value.setdefault(_norm(fact.display_value), []).append(fact)
        winning = max(
            by_value.values(),
            key=lambda items: (
                max((SOURCE_PRIORITY.get(item.source_domain, 0), origin_priority.get(item.evidence_origin, 0)) for item in items),
                len({item.source_domain for item in items}),
                max(item.confidence for item in items),
            ),
        )
        ordered = sorted(
            winning,
            key=lambda item: (SOURCE_PRIORITY.get(item.source_domain, 0), origin_priority.get(item.evidence_origin, 0), item.confidence),
            reverse=True,
        )
        best = ordered[0]
        domains = list(dict.fromkeys(item.source_domain for item in ordered))
        urls = list(dict.fromkeys(item.source_url for item in ordered))
        result.append({
            "field_key": key,
            "label_ru": best.label_ru,
            "category": best.category,
            "display_value": best.display_value,
            "unit": best.unit,
            "confidence": min(0.99, best.confidence + (0.03 if len(domains) > 1 else 0.0)),
            "evidence_count": len(domains),
            "source_domains": domains,
            "source_urls": urls,
            "evidence_origins": list(dict.fromkeys(item.evidence_origin for item in ordered)),
            "provenance": [
                {"source_domain": item.source_domain, "source_url": item.source_url,
                 "origin": item.evidence_origin, "retrieved_at": item.retrieved_at,
                 "curated_audited_on": item.curated_audited_on}
                for item in ordered
            ],
        })
    return result


def enrich(
    car: dict[str, Any],
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    vin = normalize_identity(car.get("vin"))
    if not VIN_RE.fullmatch(vin):
        return {
            "policy_version": POLICY_VERSION, "vin": vin, "profile_id": "",
            "lookup_years": [], "status": "NEEDS_REVIEW", "facts": [],
            "sources": {domain: {"status": "NOT_RUN_UNRESOLVED_IDENTITY", "facts": 0} for domain in SOURCE_DOMAINS},
            "warnings": ["JAPANESE_FRAME_REQUIRES_REVIEWED_CATALOGUE_MAPPING"],
        }
    issues = identity_context_issues(car)
    if issues:
        return {
            "policy_version": POLICY_VERSION, "vin": vin, "profile_id": "",
            "lookup_years": [], "status": "NEEDS_REVIEW", "facts": [],
            "sources": {domain: {"status": "NOT_RUN_IDENTITY_CONFLICT", "facts": 0}
                        for domain in SOURCE_DOMAINS},
            "warnings": issues, "identity_context_issues": issues,
        }
    profile = match_profile(car)
    curated = profile_facts(profile)
    facts: list[Fact] = list(curated)
    sources: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    curated_counts = {
        domain: sum(1 for fact in curated if fact.source_domain == domain)
        for domain in SOURCE_DOMAINS
    }
    crm_years = re.findall(r"(?:19|20)\d{2}", str(car.get("year") or car.get("model_year") or ""))
    decoded_year = vin_model_year(vin)
    if decoded_year and crm_years and abs(decoded_year - int(crm_years[0])) > 1:
        warnings.append("VIN_YEAR_USED_FOR_LOOKUP_ONLY")
    try:
        identity, vpic_facts = decode_vpic(car, opener=opener)
        if not vpic_identity_matches(car, identity):
            sources["vpic.nhtsa.dot.gov"] = {
                "status": "IDENTITY_MISMATCH", "facts": 0, "identity": identity,
            }
            warnings.append("VPIC_IDENTITY_MISMATCH")
        else:
            facts.extend(vpic_facts)
            sources["vpic.nhtsa.dot.gov"] = {
                "status": "PASS" if vpic_facts else "NO_TECHNICAL_FACTS",
                "facts": len(vpic_facts), "identity": identity,
                "evidence_origins": sorted({fact.evidence_origin for fact in vpic_facts}),
            }
    except Exception as exc:
        sources["vpic.nhtsa.dot.gov"] = {"status": "FAIL", "error": str(exc) if isinstance(exc, SourcePolicyError) else type(exc).__name__}
        warnings.append("VPIC_UNAVAILABLE")

    for domain in SOURCE_DOMAINS[1:]:
        accepted: list[Fact] = []
        attempts: list[dict[str, Any]] = []
        profile_urls = known_urls(car, domain)
        if profile and not profile_urls:
            sources[domain] = {
                "status": "NOT_APPLICABLE_PROFILE", "facts": 0, "attempts": [],
            }
            continue
        try:
            urls = discover_urls(car, domain, opener=opener)
        except Exception as exc:
            urls = []
            attempts.append({"status": "DISCOVERY_FAIL", "error": str(exc) if isinstance(exc, SourcePolicyError) else type(exc).__name__})
        for url in urls:
            try:
                body = _open_bytes(url, opener=opener)
                score, page_facts = extract_page_facts(car, url, body)
                attempts.append({"url": url, "score": score, "facts": len(page_facts),
                                 "evidence_origin": getattr(body, "evidence_origin", "supplied_page"),
                                 "retrieved_at": getattr(body, "retrieved_at", "")})
                if page_facts:
                    accepted.extend(page_facts)
                    break
            except Exception as exc:
                attempts.append({"url": url, "status": "FETCH_FAIL", "error": str(exc) if isinstance(exc, SourcePolicyError) else type(exc).__name__})
        facts.extend(accepted)
        curated_count = curated_counts.get(domain, 0)
        sources[domain] = {
            "status": "PASS" if accepted else "CURATED_AVAILABLE" if curated_count else "NO_CONFIDENT_MATCH",
            "facts": len({fact.field_key for fact in [*accepted, *curated] if fact.source_domain == domain}),
            "fresh_facts": sum(fact.evidence_origin == "fresh_page" for fact in accepted),
            "cached_facts": sum(fact.evidence_origin == "cached_page" for fact in accepted),
            "curated_facts": curated_count,
            "curated_audited_on": str(profile_library.AUDIT_DATE) if curated_count else "",
            "attempts": attempts,
        }
        if not accepted and curated_count:
            warnings.append("CURATED_ONLY:" + domain)

    clean = deduplicate(facts)
    detailed_domains = [
        domain for domain in SOURCE_DOMAINS[1:]
        if sources.get(domain, {}).get("status") in {"PASS", "CURATED_AVAILABLE"}
    ]
    minimum_facts = 10 if profile else 4
    status = "READY" if len(clean) >= minimum_facts and detailed_domains else "NEEDS_REVIEW"
    return {
        "policy_version": POLICY_VERSION,
        "vin": vin,
        "profile_id": str((profile or {}).get("id") or ""),
        "lookup_years": lookup_years(car),
        "status": status,
        "facts": clean,
        "sources": sources,
        "warnings": warnings,
    }


def audit_sources(
    *, opener: Callable[..., Any] | None = None, network: bool = False,
    execution_origin: str = "local environment; worker verification pending",
) -> dict[str, Any]:
    """Read-only probe; HTTP 200 alone never establishes a working adapter.

    Defaults to NOT_RUN.  Explicit network=True performs public GETs without
    VINs or any CRM data.  vPIC's generic schema check is deliberately weaker
    than a VIN decode and is never included in technical PASS counts.
    """
    probes = {
        "vpic.nhtsa.dot.gov": "https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMake/kia?format=json",
        "auto-data.net": "https://www.auto-data.net/en/mercedes-benz-b-class-w246-b-180-1.8-cdi-109hp-7g-dct-18833",
        "carwiki.co.kr": "https://www.carwiki.co.kr/model/10032_2018/%EB%8D%94_%EB%89%B4_K5_2%EC%84%B8%EB%8C%80",
        "auto.danawa.com": "https://auto.danawa.com/auto/?Lineup=42280&Model=3260%2C3151&Tab=spec&Work=model&pcUse=y",
        "carisyou.com": "https://www.carisyou.com/car/5688/Spec/54625",
        "ultimatespecs.com": "https://www.ultimatespecs.com/car-specs/Mercedes-Benz/24345/Mercedes-Benz-B-Class-%28W245%29-B180-Autotronic.html",
        "automobile-catalog.com": "https://www.automobile-catalog.com/car/2010/1549490/mercedes-benz_b_180_autotronic.html",
        "cars-data.com": "https://cars-data.com/en/mercedes-benz/b-class/w245/b-170-35607--35607/specs",
        "carfolio.com": "https://www.carfolio.com/hyundai-sonata-2.0-lpi-automatic-854447",
        "encycarpedia.com": "https://www.encycarpedia.com/mercedes/05-b-170-mpv",
    }
    samples = {
        "auto-data.net": {"brand": "Mercedes-Benz", "model": "B-Class", "year": "2013", "fuel": "diesel", "engine_cc": 1796},
        "carwiki.co.kr": {"brand": "Kia", "model": "K5", "year": "2018", "fuel": "LPI", "engine_cc": 1999},
        "auto.danawa.com": {"brand": "Kia", "model": "K5", "year": "2018", "fuel": "LPI", "engine_cc": 1999},
        "carfolio.com": {"brand": "Hyundai", "model": "Sonata", "year": "2018", "fuel": "LPI", "engine_cc": 1999},
    }
    mercedes = {"brand": "Mercedes-Benz", "model": "B-Class", "year": "2010", "fuel": "gasoline", "engine_cc": 1699}
    result: dict[str, Any] = {}
    for domain, url in probes.items():
        item: dict[str, Any] = {"status": "NOT_RUN", "probe_url": url, "facts": 0}
        result[domain] = item
        if not network:
            item["reason"] = "NETWORK_CHECK_NOT_REQUESTED_OR_UNAVAILABLE"
            continue
        if domain == "carisyou.com":
            item["reason"] = "NO_REVIEWED_IDENTITY_FOR_LEGACY_PROBE_URL"
            continue
        try:
            # Force a fresh GET for diagnostics; production cache remains intact.
            fetch = opener or urllib.request.build_opener(_AllowedRedirect()).open
            body = _open_bytes(url, opener=fetch)
            item.update({"bytes": len(body), "retrieved_at": getattr(body, "retrieved_at", "")})
            if domain == "vpic.nhtsa.dot.gov":
                payload = json.loads(body.decode("utf-8"))
                rows = payload.get("Results") if isinstance(payload, dict) else None
                valid = isinstance(rows, list) and any(
                    isinstance(row, dict) and _norm(row.get("Make_Name")) == "kia"
                    and _clean(row.get("Model_Name")) for row in rows
                )
                item.update({"status": "API_SCHEMA_ONLY" if valid else "FAIL_SCHEMA",
                             "reason": "VIN_DECODER_NOT_RUN; NO_VIN_TRANSMITTED"})
                continue
            sample = samples.get(domain, mercedes)
            score, extracted = extract_page_facts(sample, url, body)
            clean = deduplicate(extracted)
            item.update({"match_score": score, "facts": len(clean),
                         "fields": [fact["field_key"] for fact in clean],
                         "status": "PASS" if len(clean) >= 4 else "FAIL_CONTENT_OR_IDENTITY"})
        except Exception as exc:
            code = str(exc) if isinstance(exc, SourcePolicyError) else type(exc).__name__
            # A connectivity restriction is missing evidence, never a pass or
            # a claim that the upstream source itself is broken.
            unavailable = code.startswith("NETWORK_") or code.startswith("RETRY_DEFERRED:")
            item.update({"status": "NOT_RUN" if unavailable else "FAIL", "error": code})
    return {
        "policy_version": POLICY_VERSION, "audited_on": _utc_now(),
        "curated_library_audited_on": profile_library.AUDIT_DATE,
        "execution_origin": execution_origin, "network_requested": network,
        "source_count": len(SOURCE_DOMAINS), "sources": result,
        "pass_count": sum(item["status"] == "PASS" for item in result.values()),
        "not_run_count": sum(item["status"] == "NOT_RUN" for item in result.values()),
        "vin_sent": False, "production_touched": False,
        "limitations": [
            "Offline fixtures do not prove live source availability or current markup.",
            "A model-page match is not proof of factory options for an individual VIN.",
            "vPIC VIN identity decoding requires a separate approved worker check.",
            "Carisyou legacy probe has no reviewed vehicle identity and remains NOT_RUN.",
        ],
    }


if __name__ == "__main__":
    assert normalize_vin(" WDDMH0BBXDV171918 ") == "WDDMH0BBXDV171918"
    assert source_domain("https://www.auto-data.net/ru/test") == "auto-data.net"
    assert source_domain("https://example.com/?next=auto-data.net") is None
    assert PRICE_RE.search("Цена 20000 $")
    assert vpic_identity_matches(
        {"brand": "Mercedes-Benz", "model": "B-Class", "year": "2013"},
        {"Make": "MERCEDES-BENZ", "Model": "B-Class", "ModelYear": "2013", "ErrorCode": "0"},
    )
    assert not vpic_identity_matches(
        {"brand": "Kia", "model": "K5", "year": "2018"},
        {"Make": "HYUNDAI", "Model": "Sonata", "ModelYear": "2018", "ErrorCode": "0"},
    )
    assert known_urls(
        {"vin": "WDDMH0BBXDV171918", "brand": "Mercedes-Benz", "model": "B-Class", "year": "2013", "fuel": "Дизель", "engine_cc": 1800, "transmission": "автомат"},
        "auto-data.net",
    ) == ["https://www.auto-data.net/en/mercedes-benz-b-class-w246-b-180-1.8-cdi-109hp-7g-dct-18833"]
    assert vin_model_year("KNAGS416BHA141028") == 2017
    assert len(SOURCE_DOMAINS) == 10
    assert len(profile_facts(match_profile({
        "vin": "KNAGS416BLA375484", "brand": "Kia", "model": "K5",
        "year": "2019", "fuel": "LPI", "engine_cc": 2000,
    }))) >= 10
    print("UA111_SOURCE_POLICY_SELFTEST_PASS")
