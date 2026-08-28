#!/usr/bin/env python3
"""Public, read-only verification for SEO-REHAB-GUARD-068."""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


CONTRACT = "SEO-REHAB-GUARD-068"
ORIGIN = "https://www.uaart.com.ua"
BASE = ORIGIN + "/video/"
REQUIRED_CTA = "Задаток 500 $"
CARD_IDS = ["UA-%04d" % number for number in range(1, 11)]
CORE_FILES = ["index.html", "katalog.html", "info.html", "podbor.html"]
OUT = pathlib.Path(__file__).resolve().parent / "evidence" / "live.json"
MAX_BYTES = 24 * 1024 * 1024
ACTION_RE = re.compile(r'(<(?P<tag>a|button)\b[^>]*>)(?P<inner>.*?)(</(?P=tag)\s*>)', re.I | re.S)
CTA_RE = re.compile(
    r'(?:Купить авто|Купити авто|Задаток\s*\$?\s*500\s*\$?'
    r'|Депозит\s*\$?\s*500\s*\$?|Забронировать авто за\s*\$?\s*500\s*\$?)',
    re.I,
)


class VerifyError(RuntimeError):
    pass


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def atomic_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    ) as handle:
        temporary = pathlib.Path(handle.name)
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
    temporary.replace(path)


def attr(tag: str, name: str) -> str:
    found = re.search(r'\b' + re.escape(name) + r'\s*=\s*(["\'])(.*?)\1', tag, re.I | re.S)
    return found.group(2) if found else ""


def strip_tags(value: str) -> str:
    value = re.sub(r'<(?:script|style)\b.*?</(?:script|style)>', ' ', value, flags=re.I | re.S)
    value = re.sub(r'<[^>]+>', ' ', value)
    value = re.sub(r'&nbsp;|&#160;', ' ', value, flags=re.I)
    return re.sub(r'\s+', ' ', value).strip()


def fetch(url: str) -> dict:
    last = None
    for attempt in range(1, 6):
        separator = "&" if "?" in url else "?"
        target = url + separator + "seo068_verify=%d-%d" % (time.time_ns(), attempt)
        request = urllib.request.Request(
            target,
            headers={
                "User-Agent": "ua-art-seo-rehab-068-verifier/1",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                payload = response.read(MAX_BYTES + 1)
                if len(payload) > MAX_BYTES:
                    raise VerifyError("response_too_large")
                return {
                    "status": int(response.status),
                    "final_url": response.geturl(),
                    "content_type": response.headers.get("Content-Type", ""),
                    "x_robots_tag": response.headers.get("X-Robots-Tag", ""),
                    "payload": payload,
                    "attempt": attempt,
                }
        except Exception as exc:
            last = exc
            if attempt < 5:
                time.sleep(attempt * 2)
    raise VerifyError("fetch_failed:%s:%s" % (url, type(last).__name__))


def exact_destination(value: dict, expected_url: str) -> None:
    final = urllib.parse.urlsplit(value["final_url"])
    expected = urllib.parse.urlsplit(expected_url)
    if value["status"] != 200:
        raise VerifyError("http_status:%s:%s" % (expected_url, value["status"]))
    if (final.scheme, final.netloc, final.path) != (expected.scheme, expected.netloc, expected.path):
        raise VerifyError("redirected:%s:%s" % (expected_url, value["final_url"]))


def canonical_values(source: str) -> list[str]:
    return re.findall(
        r'<link\b(?=[^>]*\brel\s*=\s*["\'][^"\']*canonical[^"\']*["\'])'
        r'(?=[^>]*\bhref\s*=\s*["\']([^"\']+)["\'])[^>]*>',
        source, re.I,
    )


def robots_values(source: str) -> list[str]:
    return re.findall(
        r'<meta\b(?=[^>]*\bname\s*=\s*["\'](?:robots|googlebot)["\'])'
        r'(?=[^>]*\bcontent\s*=\s*["\']([^"\']*)["\'])[^>]*>',
        source, re.I,
    )


def primary_cta(source: str) -> list[str]:
    values = []
    for found in ACTION_RE.finditer(source):
        opening = found.group(1)
        visible = strip_tags(found.group("inner"))
        if "kn_kupit" in attr(opening, "class").split() or CTA_RE.search(visible):
            values.append(visible)
    return values


def diagnostic_hrefs(source: str) -> list[str]:
    values = []
    for tag in re.findall(r'<a\b[^>]*>', source, re.I):
        href = attr(tag, "href")
        found = re.search(r'(UA-[0-9]{4,}-diag\.html)(?:[?#]|$)', href, re.I)
        if found:
            values.append(found.group(1).upper())
    return values


def validate_indexable(value: dict, file_name: str) -> dict:
    expected_url = BASE + file_name
    exact_destination(value, expected_url)
    source = value["payload"].decode("utf-8", errors="replace")
    canonicals = canonical_values(source)
    robots = robots_values(source)
    x_robots = value["x_robots_tag"]
    if canonicals != [expected_url]:
        raise VerifyError("canonical:%s:%r" % (file_name, canonicals))
    if any(re.search(r'(?:^|[,\s])(noindex|nofollow)(?:$|[,\s])', item, re.I) for item in robots):
        raise VerifyError("robots_meta:%s:%r" % (file_name, robots))
    if re.search(r'(?:^|[,\s])(noindex|nofollow)(?:$|[,\s])', x_robots, re.I):
        raise VerifyError("x_robots_tag:%s:%s" % (file_name, x_robots))
    return {
        "url": expected_url,
        "http": value["status"],
        "canonical": canonicals[0],
        "robots_meta": robots,
        "x_robots_tag": x_robots,
        "sha256": sha(value["payload"]),
        "bytes": len(value["payload"]),
    }


def verify_public() -> dict:
    result = {
        "contract": CONTRACT,
        "status": "FAIL",
        "mode": "read-only-public-verification",
        "production_write": False,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "core": [],
        "cards": [],
        "diagnostics": [],
        "errors": [],
    }
    try:
        home = fetch(ORIGIN + "/")
        if home["status"] != 200 or urllib.parse.urlsplit(home["final_url"]).path != "/video/index.html":
            raise VerifyError("home_entry_invalid:" + home["final_url"])
        result["home_entry"] = {"http": home["status"], "final_url": home["final_url"]}

        for file_name in CORE_FILES:
            result["core"].append(validate_indexable(fetch(BASE + file_name), file_name))

        for identifier in CARD_IDS:
            file_name = identifier + ".html"
            value = fetch(BASE + file_name)
            item = validate_indexable(value, file_name)
            source = value["payload"].decode("utf-8", errors="replace")
            cta = primary_cta(source)
            diagnostics = diagnostic_hrefs(source)
            if cta != [REQUIRED_CTA]:
                raise VerifyError("cta:%s:%r" % (identifier, cta))
            if diagnostics != [identifier + "-DIAG.HTML"]:
                raise VerifyError("diagnostics:%s:%r" % (identifier, diagnostics))
            if source.count("UA-ART-DELIVERY-STAGES-PERMANENT-V1:START") != 1:
                raise VerifyError("stage_guard:%s" % identifier)
            item.update({"id": identifier, "primary_cta": cta, "diagnostic_hrefs": diagnostics})
            result["cards"].append(item)

            diag_name = identifier + "-diag.html"
            diag = fetch(BASE + diag_name)
            exact_destination(diag, BASE + diag_name)
            diag_source = diag["payload"].decode("utf-8", errors="replace").lower()
            if "<html" not in diag_source or "</html>" not in diag_source:
                raise VerifyError("diagnostic_html:%s" % identifier)
            result["diagnostics"].append({
                "id": identifier,
                "http": diag["status"],
                "sha256": sha(diag["payload"]),
                "bytes": len(diag["payload"]),
            })

        robots = fetch(ORIGIN + "/robots.txt")
        exact_destination(robots, ORIGIN + "/robots.txt")
        robots_source = robots["payload"].decode("utf-8", errors="strict")
        required_robots = (
            "User-agent: *\nAllow: /\nDisallow: /video/preview/\n"
            "Sitemap: https://www.uaart.com.ua/sitemap.xml\n"
        )
        if robots_source != required_robots or not robots["content_type"].lower().startswith("text/plain"):
            raise VerifyError("robots_contract")
        result["robots"] = {
            "http": robots["status"], "final_url": robots["final_url"],
            "content_type": robots["content_type"], "sha256": sha(robots["payload"]),
        }

        sitemap = fetch(ORIGIN + "/sitemap.xml")
        exact_destination(sitemap, ORIGIN + "/sitemap.xml")
        if "xml" not in sitemap["content_type"].lower():
            raise VerifyError("sitemap_content_type:" + sitemap["content_type"])
        tree = ET.fromstring(sitemap["payload"])
        locations = [item.text or "" for item in tree.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
        expected_locations = [BASE + name for name in CORE_FILES]
        expected_locations.extend(BASE + identifier + ".html" for identifier in CARD_IDS)
        if locations != expected_locations:
            raise VerifyError("sitemap_locations:%r" % locations)
        result["sitemap"] = {
            "http": sitemap["status"], "final_url": sitemap["final_url"],
            "content_type": sitemap["content_type"], "locations": locations,
            "sha256": sha(sitemap["payload"]),
        }
        result["page_count"] = 1 + len(result["core"]) + len(result["cards"]) + len(result["diagnostics"]) + 2
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    return result


def availability_after_rollback() -> dict:
    checks = []
    for path in ("/", "/video/katalog.html") + tuple("/video/%s.html" % identifier for identifier in CARD_IDS):
        value = fetch(ORIGIN + path)
        checks.append({"path": path, "http": value["status"], "final_url": value["final_url"]})
        if value["status"] != 200:
            raise VerifyError("rollback_availability:" + path)
    return {"status": "PASS", "checks": checks}


def main() -> int:
    value = verify_public()
    atomic_json(OUT, value)
    print("SEO_REHAB_068_LIVE_%s pages=%s" % (value["status"], value.get("page_count", 0)))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
