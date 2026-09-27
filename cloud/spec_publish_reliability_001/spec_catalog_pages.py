"""Catalogue discovery and conservative HTML evidence extraction (stdlib only)."""
from __future__ import annotations

import html
import re
import urllib.parse

import source_policy as policy
import profile_library
from spec_model_profiles import normalize, fuel_type

DISCOVERY_HOST = "html.duckduckgo.com"
NUMERIC_KEYS = frozenset(("length", "width", "height", "wheelbase", "cylinders",
    "doors", "seats", "cylinder_bore", "piston_stroke", "valves_per_cylinder"))


def discover(card, domain, read):
    """Search is URL discovery only; snippets never become vehicle facts."""
    query = " ".join(("site:" + domain, str(card.get("brand") or ""),
        normalize(card.get("model")), str(card.get("year") or ""),
        fuel_type(card.get("fuel")), str(card.get("engine_cc") or ""), "specifications"))
    url = "https://" + DISCOVERY_HOST + "/html/?" + urllib.parse.urlencode({"q": query})
    body = read(url).decode("utf-8", "replace")
    result = []
    for raw in re.findall(r'href=[\"\']([^\"\']+)', body, re.I):
        target = html.unescape(raw)
        if target.startswith("//"):
            target = "https:" + target
        parsed = urllib.parse.urlsplit(target)
        if parsed.hostname in (DISCOVERY_HOST, "duckduckgo.com"):
            target = (urllib.parse.parse_qs(parsed.query).get("uddg") or [""])[0]
            parsed = urllib.parse.urlsplit(target)
        host = (parsed.hostname or "").removeprefix("www.")
        if parsed.scheme == "https" and host == domain and target not in result:
            result.append(target)
        if len(result) == 2:
            break
    return result


def _pairs(body):
    lines, rows = policy.parse_html(body)
    pairs = policy._pairs(lines, rows)
    # The Kia archive separates engines with headings. Read only the LPI
    # technical block, not petrol/hybrid columns or marketing equipment.
    starts = [i for i, line in enumerate(lines) if line == "2.0 LPI"]
    if starts:
        part = lines[starts[0] + 1:]
        end = next((i for i, line in enumerate(part) if re.match(r"^[12]\.\d (?:LPI|가솔린|하이브리드)", line)), len(part))
        part = part[:end]
        labels = {"전장 (mm)": "length", "전폭 (mm)": "width", "전고 (mm)": "height", "축거 (mm)": "wheelbase"}
        pairs += [(labels[line], part[i + 1].replace(",", ""))
                  for i, line in enumerate(part[:-1]) if line in labels]
    return lines, pairs


def _single_variant(card, body, lines):
    """No broad model-range page can establish an unknown vehicle's trim."""
    heading = re.search(r"<h1\b[^>]*>(.*?)</h1>", body.decode("utf-8", "replace"), re.I | re.S)
    if not heading:
        return False
    title = normalize(re.sub(r"<[^>]+>", " ", html.unescape(heading[1])))
    model = normalize(card.get("model"))
    # A user supplied power/trim is needed; 'Audi A6 3.0' is still ambiguous.
    power = re.search(r"\b(\d{2,3})\s*(?:hp|ps|л\s*с)\b", model)
    if not power or model not in title or normalize(card.get("brand")) not in title:
        return False
    text = "\n".join(lines)
    score = policy.page_match_score(card, text, "auto-data.net")
    return score >= .99


def extract(card, url, body, profile):
    """Return only whitelisted facts, with source-specific evidence.

    Known model snapshots anchor candidates, so a different power/trim cannot
    overwrite them. Unknown models require a fully specified matching variant.
    Multi-column values and conflicting occurrences are rejected.
    """
    if body.startswith(b"%PDF"):
        return [], "AUDITED_PDF_ONLY"
    domain = (urllib.parse.urlsplit(url).hostname or "").removeprefix("www.")
    lines, pairs = _pairs(body)
    seeded = url in ((profile or {}).get("urls") or {}).get(domain, ())
    if not seeded and not _single_variant(card, body, lines):
        return [], "NO_CONFIDENT_VARIANT"
    expected = (profile or {}).get("facts") or {}
    by_key = {}
    for label, value in pairs:
        mapping = policy._field_mapping(label)
        if not mapping or policy.PRICE_RE.search(value):
            continue
        key = mapping[0]
        if key not in profile_library.FIELD_DEFS or len(value) > 250:
            continue
        by_key.setdefault(key, set()).add(value)
    result = []
    for key, values in by_key.items():
        item = expected.get(key)
        if profile and not item:
            continue
        # Numerical equivalence is allowed only for simple scalar fields,
        # never power, economy, dimensions with a range, or multi-engine rows.
        wanted = str(item["value"]) if item else None
        if wanted and key in NUMERIC_KEYS:
            def number(value):
                match = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*(?:mm|мм|cm|см|$)", value)
                return float(match[1].replace(",", ".")) if match else None
            target = number(wanted)
            if target is None or not values or any(number(v) != target for v in values):
                continue
            value = wanted
        elif wanted:
            if {normalize(v) for v in values} != {normalize(wanted)}:
                continue
            value = wanted
        elif len(values) == 1:
            value = next(iter(values))
        else:
            continue
        label, category, unit = profile_library.FIELD_DEFS[key]
        result.append(policy.Fact(key, label, category, value, unit, .94, domain, url))
    return result, "HTTP_OK"
