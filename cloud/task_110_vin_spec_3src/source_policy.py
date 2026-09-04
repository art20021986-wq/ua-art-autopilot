#!/usr/bin/env python3
"""Three-source technical specification policy for UA ART.

The VIN is the trigger and identity anchor.  Public technical facts may come
only from the three sources below.  Search engines are used only to discover a
page URL and are never treated as evidence.

No purchase/auction/sale price is returned by this module.  Primary CRM fields
remain operator-owned and are intentionally absent from the output mapping.
"""
from __future__ import annotations

import dataclasses
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Callable, Iterable


POLICY_VERSION = "UA110-3SRC-V1"
SOURCE_DOMAINS = (
    "vpic.nhtsa.dot.gov",
    "auto-data.net",
    "carwiki.co.kr",
)
DISCOVERY_DOMAIN = "html.duckduckgo.com"
MAX_RESPONSE_BYTES = 2_000_000
HTTP_TIMEOUT = max(5, min(30, int(os.environ.get("UA_ART_SPEC_HTTP_TIMEOUT", "15"))))
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
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

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class SourcePolicyError(RuntimeError):
    pass


def normalize_vin(value: Any) -> str:
    vin = re.sub(r"[\s\-]+", "", str(value or "")).upper()
    if not VIN_RE.fullmatch(vin):
        raise SourcePolicyError("INVALID_VIN")
    return vin


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


def _open_bytes(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = HTTP_TIMEOUT,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> bytes:
    initial_domain = _fetch_domain(url)
    if not initial_domain:
        raise SourcePolicyError("FETCH_DOMAIN_FORBIDDEN")
    request_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; UAART-VIN-Spec/1.0)",
        "Accept-Language": "ru,en;q=0.9,ko;q=0.8",
    }
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with opener(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            final_url = str(getattr(response, "geturl", lambda: url)())
            if _fetch_domain(final_url) != initial_domain:
                raise SourcePolicyError("REDIRECT_DOMAIN_FORBIDDEN")
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except SourcePolicyError:
        raise
    except urllib.error.HTTPError as exc:
        raise SourcePolicyError("HTTP_%d" % exc.code) from exc
    except Exception as exc:
        raise SourcePolicyError("NETWORK_%s" % type(exc).__name__) from exc
    if status != 200:
        raise SourcePolicyError("HTTP_%d" % status)
    if len(body) > MAX_RESPONSE_BYTES:
        raise SourcePolicyError("RESPONSE_TOO_LARGE")
    return body


def _car_tokens(car: dict[str, Any]) -> dict[str, list[str]]:
    brand = _norm(car.get("brand") or car.get("make"))
    model = _norm(car.get("model"))
    fuel = _norm(car.get("fuel") or car.get("fuel_type"))
    year = re.sub(r"\D", "", str(car.get("year") or car.get("model_year") or ""))[:4]
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
        model_aliases += ["k5", "k 5"]
    if "b class" in model or "b класс" in model or "б класс" in model:
        model_aliases += ["b class", "b класс", "b-класс", "б класс"]
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
        "year": [year] if year else [],
    }


def _any_token(text: str, tokens: Iterable[str]) -> bool:
    return any(token and token in text for token in tokens)


def page_match_score(car: dict[str, Any], text: str, domain: str) -> float:
    normalized = _norm(text)
    tokens = _car_tokens(car)
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
    if domain == "carwiki.co.kr" and not (_any_token(normalized, tokens["year"]) and _any_token(normalized, tokens["model"])):
        return 0.0
    return min(score, 1.0)


def _discovery_query(car: dict[str, Any], domain: str) -> str:
    brand = _clean(car.get("brand") or car.get("make"))
    model = _clean(car.get("model"))
    year = _clean(car.get("year") or car.get("model_year"))
    fuel = _clean(car.get("fuel") or car.get("fuel_type"))
    cc = _clean(car.get("engine_cc") or car.get("displacement"))
    if domain == "carwiki.co.kr":
        korean_brand = "기아" if _norm(brand) in {"kia", "киа"} else "현대" if "hyundai" in _norm(brand) else brand
        korean_model = "쏘나타" if "sonata" in _norm(model) else model
        return f'site:{domain}/model "{year}" "{korean_brand}" "{korean_model}" "{fuel}" "{cc}" 제원'
    return f'site:{domain}/ru "{brand}" "{model}" "{year}" "{fuel}" "{cc}" технические характеристики'


def known_urls(car: dict[str, Any], domain: str) -> list[str]:
    """Small audited seeds for exact high-priority fleet matches.

    Seeds remove search-engine availability as a single point of failure.  The
    normal page matcher and all fact guards still run before any value is used.
    """
    tokens = _car_tokens(car)
    brand = " ".join(tokens["brand"])
    model = " ".join(tokens["model"])
    fuel = " ".join(tokens["fuel"])
    year = (tokens["year"] or [""])[0]
    try:
        cc = int(car.get("engine_cc") or 0)
    except (TypeError, ValueError):
        cc = 0
    transmission = _norm(car.get("transmission") or car.get("gearbox"))
    if (
        domain == "auto-data.net" and "mercedes" in brand
        and ("b class" in model or "b 180" in model)
        and year in {"2011", "2012", "2013"} and 1700 <= cc <= 1850
        and any(item in fuel for item in ("diesel", "дизель", "cdi"))
    ):
        suffix = "7g-dct-18833" if any(item in transmission for item in ("auto", "автомат", "dct")) else "18637"
        return [
            "https://www.auto-data.net/ru/mercedes-benz-b-class-w246-b-180-1.8-cdi-109hp-" + suffix
        ]
    if domain == "carwiki.co.kr" and "kia" in brand and "k5" in model and year == "2018":
        return [
            "https://www.carwiki.co.kr/model/10032_2018/%EB%8D%94_%EB%89%B4_K5_2%EC%84%B8%EB%8C%80"
        ]
    return []


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
    "объем топливного бака": ("fuel_tank_capacity", "Объём топливного бака", "capacity"),
    "длина": ("length", "Длина", "dimensions"),
    "ширина": ("width", "Ширина", "dimensions"),
    "высота": ("height", "Высота", "dimensions"),
    "колесная база": ("wheelbase", "Колёсная база", "dimensions"),
    "колея передняя": ("front_track", "Передняя колея", "dimensions"),
    "колея задняя": ("rear_track", "Задняя колея", "dimensions"),
    "коэффициент аэродинамический лобового сопротивления c x": ("drag_coefficient", "Коэффициент аэродинамического сопротивления", "dynamics"),
    "диаметр разворота": ("turning_circle", "Диаметр разворота", "steering"),
    "тип передней подвески": ("front_suspension", "Передняя подвеска", "suspension"),
    "тип задней подвески": ("rear_suspension", "Задняя подвеска", "suspension"),
    "передние тормоза": ("front_brakes", "Передние тормоза", "brakes"),
    "задние тормоза": ("rear_brakes", "Задние тормоза", "brakes"),
    "тип рулевого управления": ("steering_type", "Рулевое управление", "steering"),
    "усилитель руля": ("power_steering", "Усилитель руля", "steering"),
    "размер шин": ("tyre_size", "Размер шин", "wheels"),
    "размер дисков": ("wheel_size", "Размер дисков", "wheels"),
    # Auto-Data English labels (the site may canonicalize a localized URL).
    "fuel consumption economy urban": ("urban_fuel_consumption", "Расход в городе", "consumption"),
    "fuel consumption economy extra urban": ("highway_fuel_consumption", "Расход на трассе", "consumption"),
    "fuel consumption economy combined": ("combined_fuel_consumption", "Смешанный расход", "consumption"),
    "co2 emissions": ("co2_emissions", "Выбросы CO₂", "ecology"),
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
    "fuel tank capacity": ("fuel_tank_capacity", "Объём топливного бака", "capacity"),
    "length": ("length", "Длина", "dimensions"),
    "width": ("width", "Ширина", "dimensions"),
    "height": ("height", "Высота", "dimensions"),
    "wheelbase": ("wheelbase", "Колёсная база", "dimensions"),
    "front track": ("front_track", "Передняя колея", "dimensions"),
    "rear back track": ("rear_track", "Задняя колея", "dimensions"),
    "drag coefficient": ("drag_coefficient", "Коэффициент аэродинамического сопротивления", "dynamics"),
    "minimum turning circle": ("turning_circle", "Диаметр разворота", "steering"),
    "front suspension": ("front_suspension", "Передняя подвеска", "suspension"),
    "rear suspension": ("rear_suspension", "Задняя подвеска", "suspension"),
    "front brakes": ("front_brakes", "Передние тормоза", "brakes"),
    "rear brakes": ("rear_brakes", "Задние тормоза", "brakes"),
    "steering type": ("steering_type", "Рулевое управление", "steering"),
    "power steering": ("power_steering", "Усилитель руля", "steering"),
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
    "타이어": ("tyre_size", "Размер шин", "wheels"),
}


def _pairs(lines: list[str], rows: list[list[str]]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for row in rows:
        label = _clean(row[0])
        value = _clean(" ".join(row[1:]))
        if label and value:
            found.append((label, value))
    normalized_labels = set(FIELD_MAP)
    for index, line in enumerate(lines[:-1]):
        if _norm(line) in normalized_labels:
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
    normalized_labels = set(FIELD_MAP)
    for index, line in enumerate(segment[:-1]):
        if _norm(line) in normalized_labels:
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
    if domain not in {"auto-data.net", "carwiki.co.kr"}:
        return 0.0, []
    lines, rows = parse_html(body)
    joined = "\n".join(lines)
    score = page_match_score(car, joined[:160_000], domain)
    threshold = 0.64 if domain == "auto-data.net" else 0.68
    if score < threshold:
        return score, []
    all_pairs = _pairs(lines, rows)
    exact_carwiki_pairs = _carwiki_exact_segment_pairs(car, lines) if domain == "carwiki.co.kr" else []
    exact_carwiki_signatures = {(_norm(label), _norm(value)) for label, value in exact_carwiki_pairs}
    result: list[Fact] = []
    for label, raw_value in all_pairs:
        mapping = FIELD_MAP.get(_norm(label))
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
    year = re.sub(r"\D", "", str(car.get("year") or car.get("model_year") or ""))[:4]
    url = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/%s?%s" % (
        urllib.parse.quote(vin, safe=""),
        urllib.parse.urlencode({"format": "json", "modelyear": year}) if year else "format=json",
    )
    payload = json.loads(_open_bytes(url, opener=opener).decode("utf-8"))
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
        ))
    identity = {key: _clean(data.get(key)) for key in ("Make", "Model", "ModelYear", "Manufacturer")}
    identity["ErrorCode"] = _clean(data.get("ErrorCode"))
    return identity, facts


def vpic_identity_matches(car: dict[str, Any], identity: dict[str, Any]) -> bool:
    error_code = _clean(identity.get("ErrorCode"))
    if error_code and any(part.strip() not in {"0"} for part in error_code.split(",")):
        return False
    tokens = _car_tokens(car)
    make = _norm(identity.get("Make") or identity.get("Manufacturer"))
    model = _norm(identity.get("Model"))
    year = re.sub(r"\D", "", str(identity.get("ModelYear") or ""))[:4]
    if not make or not tokens["brand"] or not _any_token(make, tokens["brand"]):
        return False
    if model and tokens["model"] and not _any_token(model, tokens["model"]):
        return False
    if year and tokens["year"] and year != tokens["year"][0]:
        return False
    return True


def deduplicate(facts: Iterable[Fact]) -> list[dict[str, Any]]:
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
            key=lambda items: (len({item.source_domain for item in items}), max(item.confidence for item in items)),
        )
        best = max(winning, key=lambda item: item.confidence)
        domains = sorted({item.source_domain for item in winning})
        urls = sorted({item.source_url for item in winning})
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
        })
    return result


def enrich(
    car: dict[str, Any],
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    vin = normalize_vin(car.get("vin"))
    facts: list[Fact] = []
    sources: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    try:
        identity, vpic_facts = decode_vpic(car, opener=opener)
        if not vpic_identity_matches(car, identity):
            sources["vpic.nhtsa.dot.gov"] = {
                "status": "IDENTITY_MISMATCH", "facts": 0, "identity": identity,
            }
            warnings.append("VPIC_IDENTITY_MISMATCH")
        else:
            facts.extend(vpic_facts)
            sources["vpic.nhtsa.dot.gov"] = {"status": "PASS", "facts": len(vpic_facts), "identity": identity}
    except Exception as exc:
        sources["vpic.nhtsa.dot.gov"] = {"status": "FAIL", "error": type(exc).__name__}
        warnings.append("VPIC_UNAVAILABLE")

    for domain in SOURCE_DOMAINS[1:]:
        accepted: list[Fact] = []
        attempts: list[dict[str, Any]] = []
        try:
            urls = discover_urls(car, domain, opener=opener)
        except Exception as exc:
            urls = []
            attempts.append({"status": "DISCOVERY_FAIL", "error": type(exc).__name__})
        for url in urls:
            try:
                body = _open_bytes(url, opener=opener)
                score, page_facts = extract_page_facts(car, url, body)
                attempts.append({"url": url, "score": score, "facts": len(page_facts)})
                if page_facts:
                    accepted.extend(page_facts)
                    break
            except Exception as exc:
                attempts.append({"url": url, "status": "FETCH_FAIL", "error": type(exc).__name__})
        facts.extend(accepted)
        sources[domain] = {
            "status": "PASS" if accepted else "NO_CONFIDENT_MATCH",
            "facts": len(accepted),
            "attempts": attempts,
        }

    clean = deduplicate(facts)
    detailed_domains = [
        domain for domain in SOURCE_DOMAINS[1:]
        if sources.get(domain, {}).get("status") == "PASS"
    ]
    status = "READY" if len(clean) >= 4 and detailed_domains else "NEEDS_REVIEW"
    return {
        "policy_version": POLICY_VERSION,
        "vin": vin,
        "status": status,
        "facts": clean,
        "sources": sources,
        "warnings": warnings,
    }


def audit_sources(*, opener: Callable[..., Any] = urllib.request.urlopen) -> dict[str, Any]:
    probes = {
        "vpic.nhtsa.dot.gov": "https://vpic.nhtsa.dot.gov/api/",
        "auto-data.net": "https://www.auto-data.net/ru/mercedes-benz-b-class-w246-b-180-1.8-cdi-109hp-18637",
        "carwiki.co.kr": "https://www.carwiki.co.kr/model/10032_2018/%EB%8D%94_%EB%89%B4_K5_2%EC%84%B8%EB%8C%80",
    }
    result: dict[str, Any] = {}
    for domain, url in probes.items():
        try:
            body = _open_bytes(url, opener=opener)
            result[domain] = {"status": "PASS", "bytes": len(body)}
        except Exception as exc:
            result[domain] = {"status": "FAIL", "error": type(exc).__name__}
    return {
        "policy_version": POLICY_VERSION,
        "source_count": len(SOURCE_DOMAINS),
        "sources": result,
        "pass_count": sum(1 for item in result.values() if item["status"] == "PASS"),
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
        {"brand": "Mercedes-Benz", "model": "B 180", "year": "2013", "fuel": "Дизель", "engine_cc": 1800, "transmission": "автомат"},
        "auto-data.net",
    ) == ["https://www.auto-data.net/ru/mercedes-benz-b-class-w246-b-180-1.8-cdi-109hp-7g-dct-18833"]
    print("UA110_SOURCE_POLICY_SELFTEST_PASS")
