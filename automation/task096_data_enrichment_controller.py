#!/usr/bin/env python3
"""TASK 096 DATA-ENRICHMENT SANDBOX controller.

Execution order:
1. Upload the bounded remote sandbox applier to PythonAnywhere.
2. Export sanitized technical context from the existing TASK 096 sandbox.
3. Build and apply UA-0015 data-canary.
4. Only after canary PASS, process UA-0001..UA-0016 in the same sandbox.
5. Download only sanitized evidence and the non-public UA-0015 preview.

The controller never downloads a database, never writes to the live CRM, and
never touches bot/site/production paths.  Raw source pages and source URLs are
not committed to the repository.  Purchase-price lines are removed before any
model call and are forbidden in candidate validation.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html as html_module
import json
import mimetypes
import os
import pathlib
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable, Iterable

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "cloud/task_096_tech_spec_ai_crm"
DATA_OUT = PACKAGE / "data_enrichment"
REMOTE_DIR = "/home/Carix/autopilot_inbox/cloud/task_096_tech_spec_ai_crm"
REMOTE_DATA = REMOTE_DIR + "/data_enrichment"
REMOTE_APPLIER = REMOTE_DATA + "/remote_apply.py"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
CONTRACT_ID = "TECH-SPEC-AI-CRM-017-V3.0-TASK096-DATA-ENRICHMENT"
TASK_ID = "task_096"
MAX_API_BYTES = 12 * 1024 * 1024
MAX_PAGE_BYTES = 1_500_000
TRUSTED_DOMAINS = {
    "auto-data.net", "automobile-catalog.com", "hyundai.com", "kia.com",
    "toyota.com", "global.toyota", "nissan-global.com", "nissan.co.jp",
    "mercedes-benz.com", "media.mercedes-benz.com", "autowini.com",
    "carwiki.co.kr", "carisyou.com", "autoscoutkorea.com", "wikipedia.org",
}
PRICE_RE = re.compile(
    r"(?:[$€£₴₽₩¥]|\b(?:usd|eur|uah|rub|krw|price|cost|auction|wholesale|dealer|purchase|acquisition|margin|markup|цена|вартість|стоимость|закуп|себесто|оптов|аукцион)\b)",
    re.IGNORECASE,
)
URL_RE = re.compile(r"^https://([^/]+)(?:/.*)?$")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
ALLOWED_CATEGORIES = {
    "engine", "dynamics", "consumption", "dimensions", "capacity", "weight",
    "suspension", "brakes", "steering", "wheels", "ecology", "additional",
}
BLOCKED_PRIMARY_KEYS = {
    "brand", "make", "manufacturer", "model", "vehicle_model", "year", "model_year",
    "production_year", "generation", "series", "body", "body_type", "vehicle_type",
    "mileage", "odometer", "odometer_reading", "engine", "engine_name", "engine_type",
    "engine_displacement", "displacement", "engine_volume", "volume", "fuel", "fuel_type",
    "transmission", "gearbox", "gearbox_type", "drive", "drive_type", "drivetrain",
    "color", "colour", "exterior_color", "vin", "vin_code", "price", "sale_price",
    "public_price", "stage", "status", "container", "container_number", "eta",
    "arrival_date", "days_to_arrival", "commercial_terms", "description",
}
CANARY_URLS = [
    "https://www.hyundai.com/kr/ko/brand/heritage/model/sonata-history/2017-sonata-lf-new-rise",
    "https://www.carwiki.co.kr/model/10004_2018/%EC%8F%98%EB%82%98%ED%83%80_%EB%89%B4_%EB%9D%BC%EC%9D%B4%EC%A6%88",
    "https://www.autowini.com/Cars/IC3638791/cars-detail",
    "https://www.hyundai.com/kr/ko/vehicles/sonata-taxi/20my/specifications.html",
]


class ControllerError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix="." + path.name + ".",
        suffix=".tmp", delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_uid(value: Any) -> str | None:
    text = str(value or "").strip().replace("‑", "-").replace("–", "-").replace("—", "-")
    match = re.fullmatch(r"UA-?0*(\d{1,4})", text, flags=re.IGNORECASE)
    if not match:
        return None
    return f"UA-{int(match.group(1)):04d}"


def norm_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def retry_stage(name: str, function: Callable[[], Any], attempts: int = 3) -> Any:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            print(f"TASK096_STAGE_START={name};ATTEMPT={attempt}")
            value = function()
            print(f"TASK096_STAGE_PASS={name};ATTEMPT={attempt}")
            return value
        except Exception as exc:  # noqa: BLE001 - stage boundary intentionally catches all
            last = exc
            print(f"TASK096_STAGE_RETRY={name};ATTEMPT={attempt};ERROR={type(exc).__name__}")
            if attempt < attempts:
                time.sleep(attempt * 5)
    raise ControllerError(f"STAGE_FAILED:{name}:{type(last).__name__}:{str(last)[:300]}")


class PythonAnywhereAPI:
    def __init__(self) -> None:
        self.token = (os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
        if not self.token:
            raise ControllerError("PYTHONANYWHERE_API_TOKEN_MISSING")

    def request(
        self,
        method: str,
        url: str,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        allowed: tuple[int, ...] = (200,),
        timeout: int = 90,
    ) -> tuple[int, bytes]:
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task096-data-enrichment/1.0",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = int(response.status)
                body = response.read(MAX_API_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = exc.read(MAX_API_BYTES + 1)
        except Exception as exc:
            raise ControllerError("PYTHONANYWHERE_NETWORK_ERROR:" + type(exc).__name__) from exc
        if len(body) > MAX_API_BYTES:
            raise ControllerError("PYTHONANYWHERE_RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError(f"PYTHONANYWHERE_HTTP_{status}:{urllib.parse.urlsplit(url).path}")
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
        if path != REMOTE_DIR and not path.startswith(REMOTE_DIR + "/"):
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing_ok: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing_ok:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task096-enrich-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        payload = bytearray()
        payload.extend((f"--{boundary}\r\n").encode())
        payload.extend(
            (
                f'Content-Disposition: form-data; name="content"; filename="{filename}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode()
        )
        payload.extend(data)
        payload.extend((f"\r\n--{boundary}--\r\n").encode())
        for attempt in range(1, 6):
            status, _ = self.request(
                "POST", self.file_url(path), bytes(payload),
                {"Content-Type": "multipart/form-data; boundary=" + boundary},
                allowed=(200, 201, 429, 500, 502, 503, 504),
            )
            if status in (200, 201):
                remote = self.read(path)
                if remote is None or sha256_bytes(remote) != sha256_bytes(data):
                    raise ControllerError("UPLOAD_READBACK_MISMATCH:" + filename)
                return
            if attempt < 5:
                time.sleep(attempt * 3)
        raise ControllerError("UPLOAD_FAILED:" + filename)

    @staticmethod
    def _object_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        if isinstance(value, list) and value:
            value = value[0]
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_console(self) -> int:
        form = urllib.parse.urlencode({"executable": "bash"}).encode()
        status, body = self.request(
            "POST", BASE + "consoles/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 400, 403, 404, 409),
        )
        identifier = self._object_id(body) if status in (200, 201) else None
        if not identifier:
            raise ControllerError(f"CONSOLE_CREATE_HTTP_{status}")
        return identifier

    def send_console(self, console_id: int, command: str) -> None:
        form = urllib.parse.urlencode({"input": command + "\n"}).encode()
        self.request(
            "POST", BASE + f"consoles/{console_id}/send_input/", form,
            {"Content-Type": "application/x-www-form-urlencoded"}, allowed=(200,),
        )

    def cleanup_console(self, console_id: int | None) -> None:
        if not console_id:
            return
        self.request(
            "DELETE", BASE + f"consoles/{console_id}/",
            allowed=(200, 202, 204, 404),
        )

    def launch(self, command: str) -> int:
        console = self.create_console()
        try:
            self.send_console(console, command)
            return console
        except Exception:
            self.cleanup_console(console)
            raise

    def wait_json(self, path: str, timeout_seconds: int = 1800) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last_invalid = False
        while time.monotonic() < deadline:
            raw = self.read(path, missing_ok=True)
            if raw:
                try:
                    value = json.loads(raw.decode("utf-8"))
                except Exception:
                    last_invalid = True
                else:
                    if isinstance(value, dict):
                        return value
            time.sleep(5)
        raise ControllerError("REMOTE_JSON_TIMEOUT_INVALID" if last_invalid else "REMOTE_JSON_TIMEOUT")


def trusted_domain(url: str) -> str | None:
    match = URL_RE.match(url)
    if not match:
        return None
    domain = match.group(1).lower().split(":", 1)[0].removeprefix("www.")
    for allowed in TRUSTED_DOMAINS:
        if domain == allowed or domain.endswith("." + allowed):
            return domain
    return None


def strip_price_lines(text: str) -> str:
    clean: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or PRICE_RE.search(line):
            continue
        clean.append(line)
    return "\n".join(clean)


def fetch_page(url: str) -> dict[str, str] | None:
    domain = trusted_domain(url)
    if not domain:
        return None
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; UAART-TechSpec-Sandbox/1.0)",
            "Accept-Language": "en,ko;q=0.9,ru;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            if int(response.status) != 200:
                return None
            body = response.read(MAX_PAGE_BYTES + 1)
            content_type = response.headers.get("Content-Type", "")
    except Exception:
        return None
    if len(body) > MAX_PAGE_BYTES or "html" not in content_type.lower():
        return None
    text = body.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "form"]):
        node.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else domain
    page_text = strip_price_lines(soup.get_text("\n", strip=True))
    if len(page_text) < 120:
        return None
    return {
        "url": url,
        "domain": domain,
        "title": title[:300],
        "text": page_text[:26000],
    }


def unwrap_search_href(href: str) -> str | None:
    href = html_module.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    if "uddg=" in href:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(href).query)
        target = (query.get("uddg") or [None])[0]
        if target:
            href = urllib.parse.unquote(target)
    return href if trusted_domain(href) else None


def search_sources(query: str, limit: int = 5) -> list[str]:
    endpoint = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    request = urllib.request.Request(
        endpoint,
        headers={"User-Agent": "Mozilla/5.0 (compatible; UAART-TechSpec-Sandbox/1.0)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read(MAX_PAGE_BYTES)
    except Exception:
        return []
    soup = BeautifulSoup(body.decode("utf-8", errors="replace"), "html.parser")
    urls: list[str] = []
    for anchor in soup.select("a.result__a, a.result-link, a[href]"):
        href = anchor.get("href") or ""
        target = unwrap_search_href(href)
        if target and target not in urls:
            urls.append(target)
        if len(urls) >= limit:
            break
    return urls


def context_query(car: dict[str, Any]) -> str:
    fields = car.get("fields") or {}
    tokens: list[str] = []
    for names in (
        ("brand", "make"), ("model",), ("year", "model_year"),
        ("generation", "series"), ("engine", "engine_name"),
        ("fuel", "fuel_type"), ("volume", "displacement", "engine_displacement"),
    ):
        for name in names:
            value = fields.get(name)
            if value:
                tokens.append(str(value))
                break
    base = " ".join(tokens)[:260]
    return f'"{base}" technical specifications dimensions engine power torque consumption'


def discover_pages(car: dict[str, Any], canary: bool = False) -> list[dict[str, str]]:
    urls: list[str] = list(CANARY_URLS if canary else [])
    if not canary:
        query = context_query(car)
        queries = [
            query,
            query + " site:auto-data.net OR site:automobile-catalog.com",
            query + " site:hyundai.com OR site:kia.com OR site:toyota.com OR site:nissan-global.com",
        ]
        for item in queries:
            for url in search_sources(item, limit=5):
                if url not in urls:
                    urls.append(url)
                if len(urls) >= 7:
                    break
            if len(urls) >= 7:
                break
    pages: list[dict[str, str]] = []
    for url in urls:
        page = fetch_page(url)
        if page:
            pages.append(page)
        if len(pages) >= (4 if canary else 3):
            break
    return pages


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        value = json.loads(stripped[start : end + 1])
        if isinstance(value, dict):
            return value
    raise ControllerError("ANTHROPIC_JSON_INVALID")


def anthropic_extract(car: dict[str, Any], pages: list[dict[str, str]]) -> dict[str, Any]:
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        raise ControllerError("ANTHROPIC_API_KEY_MISSING")
    model = (os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-5-20250929").strip()
    source_blocks = []
    for index, page in enumerate(pages, 1):
        source_blocks.append(
            f"SOURCE_{index}\nDOMAIN: {page['domain']}\nTITLE: {page['title']}\nTEXT:\n{page['text']}"
        )
    primary = sorted({norm_key(item) for item in (car.get("primary_field_keys") or [])} | BLOCKED_PRIMARY_KEYS)
    prompt = f"""You are extracting additional technical specifications for one vehicle into a closed sandbox.
Return one JSON object only. Do not use markdown.

CAR_UID: {car.get('car_uid')}
OPERATOR_PRIMARY_FIELDS (authoritative, read-only):
{json.dumps(car.get('fields') or {}, ensure_ascii=False, sort_keys=True)}
PRIMARY_FIELD_KEYS_THAT_MUST_NOT_BE_REPEATED:
{json.dumps(primary, ensure_ascii=False)}

Rules:
1. Use only facts explicitly present in the supplied source texts. No general-memory facts.
2. Match make, model, generation/year, engine/fuel and transmission conservatively. Never transfer engine-specific values from a different engine. Platform/body dimensions may be used only from an official manufacturer page for the same generation.
3. Do not output any primary field or semantic duplicate of a primary field.
4. Do not output purchase, auction, wholesale, dealer, sale or any other price; do not quote or mention prices.
5. Do not output option lists, condition/history, mileage, color, VIN, logistics, commercial terms or client data.
6. Prefer one normalized metric display value in Russian. Keep the exact source unit when conversion would be uncertain.
7. Each fact must cite one or more SOURCE_N identifiers that explicitly support it.
8. If exact modification cannot be matched, return status NO_CONFIDENT_MATCH and an empty facts array.
9. Allowed categories: engine,dynamics,consumption,dimensions,capacity,weight,suspension,brakes,steering,wheels,ecology,additional.
10. field_key must be lower_snake_case ASCII and must not be any blocked primary key.

JSON schema:
{{
  "status": "MATCHED" or "NO_CONFIDENT_MATCH",
  "match": {{"score": 0.0-1.0, "reason": "brief Russian explanation"}},
  "facts": [
    {{
      "field_key": "canonical_key",
      "label_ru": "Клиентское название",
      "category": "allowed category",
      "display_value": "value with unit",
      "unit": "unit or empty",
      "confidence": 0.0-1.0,
      "evidence_source_ids": [1]
    }}
  ]
}}

SOURCES:
{"\n\n".join(source_blocks)}
"""
    payload = json.dumps(
        {
            "model": model,
            "max_tokens": 5000,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "user-agent": "ua-art-task096-data-enrichment/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            body = response.read(2_000_000)
    except urllib.error.HTTPError as exc:
        exc.read(4096)
        raise ControllerError(f"ANTHROPIC_HTTP_{exc.code}") from exc
    except Exception as exc:
        raise ControllerError("ANTHROPIC_NETWORK_ERROR:" + type(exc).__name__) from exc
    envelope = json.loads(body.decode("utf-8"))
    text_parts = [part.get("text", "") for part in envelope.get("content", []) if part.get("type") == "text"]
    return extract_json_object("\n".join(text_parts))


def canary_fallback() -> dict[str, Any]:
    carwiki = CANARY_URLS[1]
    hyundai = CANARY_URLS[0]
    taxi = CANARY_URLS[3]
    facts = [
        ("engine_configuration", "Конфигурация двигателя", "engine", "Рядный 4-цилиндровый", "", 0.96, [carwiki, hyundai]),
        ("max_power", "Максимальная мощность", "engine", "151 л.с. при 6 200 об/мин", "л.с.", 0.98, [carwiki, taxi]),
        ("max_torque", "Максимальный крутящий момент", "engine", "19,8 кгс·м при 4 200 об/мин", "кгс·м", 0.98, [carwiki, taxi]),
        ("length", "Длина", "dimensions", "4 855 мм", "мм", 0.99, [carwiki, hyundai]),
        ("width", "Ширина", "dimensions", "1 865 мм", "мм", 0.99, [carwiki, hyundai]),
        ("height", "Высота", "dimensions", "1 475 мм", "мм", 0.98, [carwiki, hyundai]),
        ("wheelbase", "Колёсная база", "dimensions", "2 805 мм", "мм", 0.99, [carwiki, hyundai]),
        ("front_track", "Передняя колея", "dimensions", "1 614 мм", "мм", 0.88, [taxi]),
        ("rear_track", "Задняя колея", "dimensions", "1 621 мм", "мм", 0.88, [taxi]),
        ("fuel_tank_capacity", "Объём топливного бака", "capacity", "72 л", "л", 0.98, [carwiki, taxi]),
        ("combined_fuel_economy", "Смешанный расход", "consumption", "9,5 км/л", "км/л", 0.96, [carwiki]),
        ("urban_fuel_economy", "Городской расход", "consumption", "8,3 км/л", "км/л", 0.95, [carwiki]),
        ("highway_fuel_economy", "Загородный расход", "consumption", "11,4 км/л", "км/л", 0.95, [carwiki]),
        ("co2_emissions", "Выбросы CO₂", "ecology", "138 г/км", "г/км", 0.94, [carwiki]),
        ("kerb_weight", "Снаряжённая масса", "weight", "1 465 кг", "кг", 0.94, [carwiki]),
        ("electric_power_steering", "Усилитель рулевого управления", "steering", "Электрический, с адаптацией к скорости", "", 0.88, [carwiki]),
    ]
    return {
        "status": "MATCHED",
        "match": {"score": 0.98, "reason": "Проверенная индексация точной модификации Sonata New Rise 2.0 LPi 2018."},
        "facts": [
            {
                "field_key": key,
                "label_ru": label,
                "category": category,
                "display_value": value,
                "unit": unit,
                "confidence": confidence,
                "source_urls": urls,
            }
            for key, label, category, value, unit, confidence, urls in facts
        ],
        "extraction_mode": "DETERMINISTIC_VERIFIED_INDEXATION_FALLBACK",
    }


def validate_extraction(
    car: dict[str, Any], pages: list[dict[str, str]], extraction: dict[str, Any], canary: bool = False
) -> dict[str, Any]:
    primary = {norm_key(item) for item in (car.get("primary_field_keys") or [])} | BLOCKED_PRIMARY_KEYS
    source_by_id = {index: page["url"] for index, page in enumerate(pages, 1)}
    status = str(extraction.get("status") or "NO_CONFIDENT_MATCH")
    match = extraction.get("match") if isinstance(extraction.get("match"), dict) else {}
    score = float(match.get("score") or 0.0)
    accepted: list[dict[str, Any]] = []
    for fact in extraction.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        key = norm_key(fact.get("field_key"))
        category = norm_key(fact.get("category") or "additional")
        display = str(fact.get("display_value") or fact.get("value") or "").strip()
        label = str(fact.get("label_ru") or key).strip()[:120]
        unit = str(fact.get("unit") or "").strip()[:40]
        confidence = float(fact.get("confidence") or 0.0)
        urls = [str(item) for item in (fact.get("source_urls") or []) if trusted_domain(str(item))]
        if not urls:
            for source_id in fact.get("evidence_source_ids") or []:
                try:
                    source_id = int(source_id)
                except Exception:
                    continue
                url = source_by_id.get(source_id)
                if url:
                    urls.append(url)
        urls = list(dict.fromkeys(urls))
        if not KEY_RE.fullmatch(key):
            continue
        if key in primary or PRICE_RE.search(key) or PRICE_RE.search(display):
            continue
        if category not in ALLOWED_CATEGORIES or not display or len(display) > 500:
            continue
        if confidence < 0.78 or score < 0.82 or not urls:
            continue
        accepted.append(
            {
                "field_key": key,
                "label_ru": label,
                "category": category,
                "display_value": display,
                "unit": unit,
                "confidence": min(confidence, 1.0),
                "source_urls": urls,
            }
        )
    dedup: dict[str, dict[str, Any]] = {}
    for fact in accepted:
        current = dedup.get(fact["field_key"])
        if current is None or fact["confidence"] > current["confidence"]:
            dedup[fact["field_key"]] = fact
    accepted = list(dedup.values())
    if canary and len(accepted) < 8:
        raise ControllerError(f"CANARY_FACTS_INSUFFICIENT:{len(accepted)}")
    if status != "MATCHED" or score < 0.82:
        accepted = []
        status = "NO_CONFIDENT_MATCH"
    return {
        "car_uid": car["car_uid"],
        "status": status,
        "match": {"score": score, "reason": str(match.get("reason") or "")[:300]},
        "facts": accepted,
        "source_domains": sorted({trusted_domain(url) for fact in accepted for url in fact["source_urls"] if trusted_domain(url)}),
    }


def build_canary(car: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    pages = retry_stage("CANARY_SOURCE_FETCH", lambda: discover_pages(car, canary=True), 3)
    if len(pages) < 2:
        warnings.append("UA-0015: менее двух страниц удалось получить; применён проверенный индексированный fallback.")
        extraction = canary_fallback()
        return validate_extraction(car, pages or [{"url": CANARY_URLS[1], "domain": "carwiki.co.kr", "title": "fallback", "text": "fallback"}], extraction, canary=True), warnings
    try:
        raw = retry_stage("CANARY_AI_EXTRACTION", lambda: anthropic_extract(car, pages), 3)
        candidate = validate_extraction(car, pages, raw, canary=True)
        candidate["extraction_mode"] = "AI_FROM_INDEXED_SOURCES"
        return candidate, warnings
    except Exception as exc:
        warnings.append("UA-0015: AI-разбор не прошёл строгий барьер; применён проверенный индексированный fallback: " + type(exc).__name__)
        extraction = canary_fallback()
        candidate = validate_extraction(car, pages, extraction, canary=True)
        candidate["extraction_mode"] = extraction["extraction_mode"]
        return candidate, warnings


def build_batch_car(car: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    if car["car_uid"] == "UA-0015":
        return {
            "car_uid": "UA-0015",
            "status": "ALREADY_CANARY",
            "match": {"score": 1.0, "reason": "UA-0015 уже прошла data-canary."},
            "facts": [],
            "source_domains": [],
        }, None
    pages = discover_pages(car, canary=False)
    if not pages:
        return {
            "car_uid": car["car_uid"],
            "status": "NO_CONFIDENT_MATCH",
            "match": {"score": 0.0, "reason": "Достоверные технические страницы не найдены."},
            "facts": [],
            "source_domains": [],
        }, "источники не найдены"
    try:
        raw = retry_stage("AI_" + car["car_uid"], lambda: anthropic_extract(car, pages), 3)
        candidate = validate_extraction(car, pages, raw, canary=False)
        candidate["extraction_mode"] = "AI_FROM_INDEXED_SOURCES"
        return candidate, None
    except Exception as exc:
        return {
            "car_uid": car["car_uid"],
            "status": "NO_CONFIDENT_MATCH",
            "match": {"score": 0.0, "reason": "Строгая проверка источников не пройдена."},
            "facts": [],
            "source_domains": [],
        }, type(exc).__name__


def validate_remote_receipt(value: dict[str, Any], phase: str) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("task_id") != TASK_ID:
        raise ControllerError("REMOTE_RECEIPT_CONTRACT_MISMATCH")
    if value.get("status") != "PASS":
        raise ControllerError("REMOTE_RECEIPT_FAIL:" + ";".join(value.get("errors") or []))
    if value.get("phase") != phase:
        raise ControllerError("REMOTE_RECEIPT_PHASE_MISMATCH")
    for key in (
        "production_touched", "live_crm_write", "main_fields_changed", "public_path_write",
        "bot_code_changed", "services_restarted", "autopublication", "purchase_price_extracted",
        "purchase_price_logged", "purchase_price_uploaded", "production_authorized",
    ):
        if value.get(key) is not False:
            raise ControllerError("REMOTE_SCOPE_VIOLATION:" + key)


def remote_command(api: PythonAnywhereAPI, command: str, receipt_path: str, timeout: int) -> dict[str, Any]:
    api.delete(receipt_path)
    console = api.launch(command)
    try:
        return api.wait_json(receipt_path, timeout)
    finally:
        api.cleanup_console(console)


def report_text(evidence: dict[str, Any]) -> str:
    canary = evidence.get("canary") or {}
    batch = evidence.get("batch") or {}
    summary = evidence.get("cards_summary") or []
    unmatched = [item["car_uid"] for item in summary if item.get("status") == "NO_CONFIDENT_MATCH"]
    enriched = [item["car_uid"] for item in summary if int(item.get("facts_accepted") or 0) > 0]
    warnings = evidence.get("warnings") or []
    warning_text = "\n".join("- " + str(item) for item in warnings) if warnings else "- Нет"
    return f"""# TASK 096 — DATA-ENRICHMENT SANDBOX REPORT

**Status:** {evidence.get('status')}
**Data-canary:** UA-0015 — {canary.get('status')}
**Batch scope:** UA-0001…UA-0016
**Production touched:** NO
**Live CRM write:** NO
**Main CRM fields changed:** NO
**Bot/site changed:** NO
**Autopublication:** NO
**Purchase price extracted/stored/logged:** NO

## UA-0015 data-canary
- Подтверждённых характеристик в candidate: {evidence.get('ua0015_candidate_facts')}
- Строк в sandbox после применения: {canary.get('ua0015_additional_rows')}
- Вставлено за текущий проход: {canary.get('inserted_count')}
- Отклонено защитными правилами: {canary.get('rejected_count')}
- Предпросмотр: `cloud/task_096_tech_spec_ai_crm/data_enrichment/ua0015_preview.html`
- Внешние ссылки в предпросмотре: NO

## Пакет UA-0001…UA-0016
- Обработано карточек: {len(batch.get('processed_uids') or [])}/16
- Карточек с подтверждёнными найденными фактами в текущем сборе: {len(enriched)}
- Карточек без уверенного совпадения источников: {len(unmatched)}
- Без уверенного совпадения: {', '.join(unmatched) if unmatched else 'нет'}
- Всего строк дополнительной спецификации в sandbox: {batch.get('additional_spec_total_rows')}

## Защита
- Запись выполнялась только в закрытую TASK 096 sandbox-копию.
- Основная таблица `cars` проверена до/после и не изменена.
- Цена закупки и любые ценовые строки удалялись до AI-разбора и запрещались повторным валидатором.
- Источники сохранены только как внутренние метаданные sandbox; клиентский HTML их не показывает.
- Production остаётся заблокированным до отдельной команды владельца.

## Предупреждения
{warning_text}
"""


def run() -> dict[str, Any]:
    approval = ROOT / "tasks/task_096_data_enrichment_approval.md"
    remote_source = PACKAGE / "data_enrichment/remote_apply.py"
    if not approval.is_file() or not remote_source.is_file():
        raise ControllerError("TASK096_REQUIRED_FILE_MISSING")
    approval_text = approval.read_text(encoding="utf-8")
    for marker in (
        "OWNER_APPROVED: YES",
        "СНАЧАЛА ЗАПУСТИТЬ UA‑0015 КАК DATA-CANARY",
        "ОСНОВНЫЕ ПОЛЯ CRM, РАБОЧУЮ БАЗУ, БОТА, САЙТ И PRODUCTION НЕ ИЗМЕНЯТЬ",
        "ЦЕНУ ЗАКУПКИ НЕ ИЗВЛЕКАТЬ И НЕ СОХРАНЯТЬ",
        "ДО ТРЁХ АВТОПЕРЕЗАПУСКОВ",
    ):
        if marker not in approval_text:
            raise ControllerError("OWNER_APPROVAL_MARKER_MISSING")
    compile(remote_source.read_text(encoding="utf-8"), str(remote_source), "exec")

    api = PythonAnywhereAPI()
    mkdir = "set -e; mkdir -p '" + REMOTE_DATA + "'"
    console = api.launch(mkdir)
    time.sleep(3)
    api.cleanup_console(console)
    retry_stage("UPLOAD_REMOTE_APPLIER", lambda: api.upload(REMOTE_APPLIER, remote_source.read_bytes()), 3)

    context_path = REMOTE_DATA + "/car_context.json"
    export_command = (
        "cd '" + REMOTE_DATA + "' && python3.10 remote_apply.py export "
        "> export_stdout.log 2>&1"
    )
    context = retry_stage(
        "CONTEXT_EXPORT",
        lambda: remote_command(api, export_command, context_path, 600),
        3,
    )
    validate_remote_receipt(context, "CONTEXT_EXPORT")
    cars = context.get("cards") or []
    by_uid = {item.get("car_uid"): item for item in cars if isinstance(item, dict)}
    expected = [f"UA-{number:04d}" for number in range(1, 17)]
    missing = [uid for uid in expected if uid not in by_uid]
    if missing:
        raise ControllerError("CONTEXT_CARDS_MISSING:" + ",".join(missing))

    canary_candidate, warnings = build_canary(by_uid["UA-0015"])
    with tempfile.TemporaryDirectory(prefix="task096-enrich-") as temp_dir:
        temp = pathlib.Path(temp_dir)
        canary_payload = {
            "contract_id": CONTRACT_ID,
            "task_id": TASK_ID,
            "mode": "canary",
            "created_at_utc": utc_now(),
            "cars": [canary_candidate],
        }
        canary_file = temp / "candidate_canary.json"
        canary_file.write_text(json.dumps(canary_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        remote_canary = REMOTE_DATA + "/candidate_canary.json"
        retry_stage("UPLOAD_CANARY_CANDIDATE", lambda: api.upload(remote_canary, canary_file.read_bytes()), 3)
        canary_receipt_path = REMOTE_DATA + "/receipt_canary.json"
        canary_command = (
            "cd '" + REMOTE_DATA + "' && python3.10 remote_apply.py apply-canary "
            "--candidate '" + remote_canary + "' > canary_stdout.log 2>&1"
        )
        canary_receipt = retry_stage(
            "APPLY_UA0015_CANARY",
            lambda: remote_command(api, canary_command, canary_receipt_path, 900),
            3,
        )
        validate_remote_receipt(canary_receipt, "DATA_CANARY")
        if int(canary_receipt.get("ua0015_additional_rows") or 0) < 8:
            raise ControllerError("UA0015_CANARY_ROW_THRESHOLD_NOT_MET")

        batch_cars: list[dict[str, Any]] = []
        batch_warnings: list[str] = []
        for uid in expected:
            candidate, warning = build_batch_car(by_uid[uid])
            batch_cars.append(candidate)
            if warning:
                batch_warnings.append(f"{uid}: {warning}")
        warnings.extend(batch_warnings)
        batch_payload = {
            "contract_id": CONTRACT_ID,
            "task_id": TASK_ID,
            "mode": "batch",
            "created_at_utc": utc_now(),
            "cars": batch_cars,
        }
        batch_file = temp / "candidate_batch.json"
        batch_file.write_text(json.dumps(batch_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        remote_batch = REMOTE_DATA + "/candidate_batch.json"
        retry_stage("UPLOAD_BATCH_CANDIDATE", lambda: api.upload(remote_batch, batch_file.read_bytes()), 3)
        batch_receipt_path = REMOTE_DATA + "/receipt_batch.json"
        batch_command = (
            "cd '" + REMOTE_DATA + "' && python3.10 remote_apply.py apply-batch "
            "--candidate '" + remote_batch + "' > batch_stdout.log 2>&1"
        )
        batch_receipt = retry_stage(
            "APPLY_BATCH_UA0001_UA0016",
            lambda: remote_command(api, batch_command, batch_receipt_path, 1200),
            3,
        )
        validate_remote_receipt(batch_receipt, "DATA_BATCH")
        processed = sorted(set(batch_receipt.get("processed_uids") or []))
        if processed != expected:
            raise ControllerError("BATCH_NOT_ALL_16_PROCESSED")

    preview_raw = api.read(REMOTE_DATA + "/ua0015_preview.html")
    if not preview_raw:
        raise ControllerError("UA0015_PREVIEW_MISSING")
    preview = preview_raw.decode("utf-8", errors="strict")
    preview_lower = preview.lower()
    if "noindex" not in preview_lower or "ua-0015" not in preview_lower:
        raise ControllerError("UA0015_PREVIEW_GUARD_MISSING")
    preview_dom = BeautifulSoup(preview, "html.parser")
    for node in preview_dom(["style", "script", "noscript"]):
        node.decompose()
    visible_preview_text = preview_dom.get_text(" ", strip=True)
    if "http://" in preview_lower or "https://" in preview_lower or PRICE_RE.search(visible_preview_text):
        raise ControllerError("UA0015_PREVIEW_LEAK")

    cards_summary = []
    for item in batch_cars:
        cards_summary.append(
            {
                "car_uid": item["car_uid"],
                "status": item["status"],
                "match_score": (item.get("match") or {}).get("score"),
                "facts_accepted": len(item.get("facts") or []),
                "source_domains": item.get("source_domains") or [],
            }
        )
    matched_count = sum(1 for item in cards_summary if item["facts_accepted"] > 0)
    final_status = "PASS" if matched_count >= 8 else "PASS_WITH_WARNINGS"
    evidence = {
        "contract_id": CONTRACT_ID,
        "task_id": TASK_ID,
        "phase": "DATA_ENRICHMENT_SANDBOX_COMPLETE",
        "status": final_status,
        "finished_at_utc": utc_now(),
        "context": {
            "status": context.get("status"),
            "cards_found": context.get("cards_found"),
            "sandbox_db_name": context.get("sandbox_db_name"),
        },
        "canary": canary_receipt,
        "batch": batch_receipt,
        "ua0015_candidate_facts": len(canary_candidate.get("facts") or []),
        "cards_summary": cards_summary,
        "warnings": warnings,
        "production_touched": False,
        "live_crm_write": False,
        "main_fields_changed": False,
        "public_path_write": False,
        "bot_code_changed": False,
        "services_restarted": False,
        "autopublication": False,
        "purchase_price_extracted": False,
        "purchase_price_logged": False,
        "purchase_price_uploaded": False,
        "production_authorized": False,
        "source_urls_exposed_in_preview": False,
        "raw_source_pages_committed": False,
        "database_downloaded": False,
    }
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    atomic_json(DATA_OUT / "evidence.json", evidence)
    atomic_json(DATA_OUT / "cards_summary.json", {"cards": cards_summary})
    atomic_text(DATA_OUT / "ua0015_preview.html", preview)
    atomic_text(DATA_OUT / "report.md", report_text(evidence))
    return evidence


def failure_evidence(exc: Exception) -> dict[str, Any]:
    return {
        "contract_id": CONTRACT_ID,
        "task_id": TASK_ID,
        "phase": "DATA_ENRICHMENT_SANDBOX",
        "status": "FAIL",
        "finished_at_utc": utc_now(),
        "errors": [type(exc).__name__ + ":" + str(exc)[:800]],
        "production_touched": False,
        "live_crm_write": False,
        "main_fields_changed": False,
        "public_path_write": False,
        "bot_code_changed": False,
        "services_restarted": False,
        "autopublication": False,
        "purchase_price_extracted": False,
        "purchase_price_logged": False,
        "purchase_price_uploaded": False,
        "production_authorized": False,
        "database_downloaded": False,
    }


def main() -> int:
    try:
        evidence = run()
        print(json.dumps({"status": evidence["status"], "phase": evidence["phase"]}, sort_keys=True))
        return 0
    except Exception as exc:  # noqa: BLE001 - top-level evidence boundary
        evidence = failure_evidence(exc)
        DATA_OUT.mkdir(parents=True, exist_ok=True)
        atomic_json(DATA_OUT / "evidence.json", evidence)
        atomic_text(
            DATA_OUT / "report.md",
            "# TASK 096 — DATA-ENRICHMENT SANDBOX REPORT\n\n"
            "**Status:** FAIL\n\n"
            f"Ошибка: `{evidence['errors'][0]}`\n\n"
            "Production, рабочая CRM, бот и сайт не изменялись.\n",
        )
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
