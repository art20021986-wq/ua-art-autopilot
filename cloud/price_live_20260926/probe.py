"""Pure helpers for the read-only price/serving probe. No network, no writes."""
from __future__ import annotations

import html
import json
import re

SECRET_RE = re.compile(
    r"(?i)(token|secret|passw|api[_-]?key|private|credential|auth|cookie|salt|dsn|smtp"
    r"|[\w.+-]+@[\w-]+\.[\w.]+|\d{8,10}:[A-Za-z0-9_-]{30,}|[A-Za-z0-9+=_-]{40,})"
)
PRICE_START = "<!-- UA-ART-MARKET-PRICES-V1:START -->"
PRICE_END = "<!-- UA-ART-MARKET-PRICES-V1:END -->"
HEADER_NAMES = (
    "server", "content-type", "cache-control", "expires", "last-modified",
    "etag", "age", "vary", "pragma",
)


def redact_lines(source: str, patterns: tuple[str, ...], limit: int = 80) -> list[str]:
    """Return numbered lines matching any pattern; secret-looking lines are masked."""
    out = []
    for number, line in enumerate(source.splitlines(), 1):
        if any(re.search(pattern, line) for pattern in patterns):
            text = "<REDACTED>" if SECRET_RE.search(line) else line.rstrip()[:240]
            out.append("%d: %s" % (number, text))
            if len(out) >= limit:
                out.append("...")
                break
    return out


def headers_subset(headers) -> dict[str, str]:
    return {name: headers.get(name) for name in HEADER_NAMES if headers.get(name) is not None}


def crm_prices(data: dict) -> dict[str, dict[str, str]]:
    """Map car code to exact published market values from the live JSON."""
    result = {}
    for code, item in (data.get("cars") or {}).items():
        values = dict(re.findall(
            r'data-ua-market="(ukraine|georgia)"[^>]*data-ua-value="([^"]*)"', item.get("full", "")))
        result[code] = values
    return result


def _numbers(text: str) -> list[str]:
    plain = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return [re.sub(r"[\s ,.]", "", n) for n in re.findall(r"\d[\d\s ,.]{2,}\d", plain)]


def page_structure(body: str) -> dict:
    """Describe where a static page carries its price, without changing it."""
    info = {
        "bytes": len(body.encode("utf-8")),
        "marker_blocks": body.count(PRICE_START),
        "marker_end": body.count(PRICE_END),
        "class_cena": len(re.findall(r'class="[^"]*\bcena\b', body)),
        "class_cn": len(re.findall(r'class="[^"]*\bcn\b', body)),
        "class_cn_b": len(re.findall(r'class="[^"]*\bcn_b\b', body)),
        "catalog_cards": len(re.findall(r"<article\b[^>]*catalog-card", body)),
        "scripts": re.findall(r'<script[^>]+src="([^"]+)"', body),
        "jsonld_prices": re.findall(r'"price"\s*:\s*"?([\d.]+)', body),
        "meta_prices": re.findall(r'<meta[^>]+(?:price|amount)[^>]+content="([^"]+)"', body, re.I),
        "data_ua_values": re.findall(r'data-ua-market="(\w+)"[^>]*data-ua-value="([^"]*)"', body),
    }
    excerpts = []
    for pattern in (re.escape(PRICE_START), r'class="[^"]*\bcena\b', r'class="[^"]*\bcn_b\b'):
        for match in re.finditer(pattern, body):
            excerpts.append(body[max(0, match.start() - 200):match.start() + 1400])
            if len(excerpts) >= 3:
                break
    info["price_numbers"] = [_numbers(text)[:6] for text in excerpts]
    info["excerpts"] = excerpts
    return info


def compare(code: str, crm: dict[str, str], structure: dict) -> dict:
    """Flag a card whose static HTML lacks the current CRM Ukraine price."""
    ukraine = crm.get("ukraine", "")
    static_values = [value for market, value in structure["data_ua_values"] if market == "ukraine"]
    static_numbers = sorted({n for group in structure["price_numbers"] for n in group})
    found = ukraine in static_values or ukraine in static_numbers or ukraine in structure["jsonld_prices"]
    return {
        "code": code,
        "crm_ukraine": ukraine,
        "crm_georgia": crm.get("georgia", ""),
        "static_ukraine_values": static_values,
        "static_numbers": static_numbers,
        "jsonld_prices": structure["jsonld_prices"],
        "static_matches_crm": bool(ukraine) and found,
    }


def listing_summary(listing: dict) -> dict:
    names = sorted(listing)
    extensions: dict[str, int] = {}
    for name in names:
        suffix = name.rsplit(".", 1)[-1].lower() if "." in name else "<dir>"
        extensions[suffix] = extensions.get(suffix, 0) + 1
    return {
        "count": len(names),
        "extensions": extensions,
        "html": [n for n in names if n.endswith(".html")],
        "scripts_styles": [n for n in names if n.endswith((".js", ".css"))],
        "directories": [n for n in names if listing[n].get("type") == "directory"],
    }


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
