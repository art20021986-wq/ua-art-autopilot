"""Inert, read-only CRM/site audit. No imports from the production application.

Run explicitly after the preceding server gate passes. The only write is a new
0600 JSON report inside ROOT/spec_gate_b_restore_20260909. This is a filesystem
and SQLite audit, not an HTTP/browser check or permission to publish a draft.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit

STAGE_NAME = "spec_gate_b_restore_20260909"
UID = re.compile(r"^UA-\d{4,6}$")
VIN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.I)
START, END = "<!--UA099_ADD_SPEC_START-->", "<!--UA099_ADD_SPEC_END-->"
FIELDS = ("id", "auto_number", "vin", "brand", "model", "year", "fuel", "engine_cc", "engine", "gearbox",
          "published", "price_uah", "price_total", "photos", "drive", "mileage_km", "color", "condition_text", "status")
SPEC_COLUMNS = {
    "additional_specification": "car_uid,field_key,field_value,normalized_value,source,source_url,confidence,is_price_field",
    "additional_specification_meta": "car_uid,field_key,label_ru,category,unit,evidence_count,source_domains_json,source_urls_json,verification_status,model_match_score,is_manual,is_visible",
}
ACCEPTED = {"VERIFIED", "VERIFIED_10SRC", "MANUAL_VERIFIED", "TRUSTED", "MANUAL", "CURATED_PASS"}
PREVIOUS_SPEC_HASH = "ec45ac8ffc088f93a98857c81a6a95aac7b81ce8f7b8a466019a9a7e9e3572b3"
PREVIOUS_CRM_HASH = "ac3e8b4666c8db7d401673c1d42e1c3cc0b7e4c9e2cc528b72ce63cceede00bc"
IDENTITY_COLUMNS = FIELDS[:11]
REQUIRED_RULE = '''def missing_required(car):
    out = []
    for key in REQUIRED:
        val = car.get(key)
        if key == "photos":
            if not val:
                out.append(LABEL[key])
            continue
        if key == "published":
            continue
        if val in (None, "", 0, []):
            out.append(LABEL[key])
    return out
'''


class AuditError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def normalized(value):
    text = re.sub(r"[^0-9a-zа-яіїєґ]+", " ", str(value or "").casefold().replace("ё", "е")).strip()
    return {"к5": "k5", "к 5": "k5", "б класса": "b class", "б класс": "b class"}.get(text, text)


def safe_text(value):
    return VIN.sub("[VIN REDACTED]", re.sub(r"\s+", " ", str(value or "")))[:160]


def vin_token(value):
    value = re.sub(r"\s+", "", str(value or "")).upper()
    return {"last4": value[-4:], "sha256": hashlib.sha256(value.encode()).hexdigest(), "length": len(value)}


class Reads:
    def __init__(self, root):
        self.root = Path(os.path.abspath(root))
        self.observed = {}
        self.safe(self.root)

    def safe(self, path):
        path = Path(os.path.abspath(path))
        if path != self.root and self.root not in path.parents:
            raise AuditError("PATH_OUTSIDE_ROOT")
        for part in [*reversed(path.parents), path]:
            if part.is_symlink():
                raise AuditError("SYMLINK_REFUSED")
        return path

    def read(self, path, maximum=16 * 1024 * 1024):
        path = self.safe(path)
        if not path.exists():
            if self.observed.get(str(path)) is not None:
                raise AuditError("INPUT_CHANGED_DURING_AUDIT")
            self.observed[str(path)] = None
            return None
        if not path.is_file():
            raise AuditError("EXPECTED_REGULAR_FILE")
        with path.open("rb") as handle:
            data = handle.read(maximum + 1)
        if len(data) > maximum:
            raise AuditError("INPUT_TOO_LARGE")
        current = hashlib.sha256(data).hexdigest()
        if str(path) in self.observed and self.observed[str(path)] != current:
            raise AuditError("INPUT_CHANGED_DURING_AUDIT")
        self.observed[str(path)] = current
        return data

    def database(self, path):
        path = self.safe(path)
        if self.read(path) is None:
            return None
        for suffix in ("-wal", "-journal", "-shm"):
            data = self.read(Path(str(path) + suffix))
            if suffix != "-shm" and data:
                raise AuditError("DATABASE_REQUIRES_STABLE_SNAPSHOT")
        conn = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
        conn.execute("PRAGMA query_only=ON")
        return conn

    def verify(self):
        for path in list(self.observed):
            self.read(path)


class Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []
        style = re.sub(r"\s+", "", self.attrs.get("style", "").lower())
        self.hidden = bool(parent and parent.hidden) or tag in {"head", "script", "style", "template"} or "hidden" in self.attrs or self.attrs.get("aria-hidden") == "true" or "display:none" in style or "visibility:hidden" in style

    def text(self):
        if self.hidden:
            return ""
        return " ".join(child.text() if isinstance(child, Node) else child for child in self.children)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class Page(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def compare(a, b):
    if a is None or b is None or str(a).strip() == "" or str(b).strip() == "":
        return "UNVERIFIED"
    return "MATCH" if normalized(a) == normalized(b) else "MISMATCH"


def local_link_name(link):
    try:
        parsed = urlsplit(link)
    except ValueError:
        return None
    if parsed.scheme not in {"", "http", "https"} or (parsed.netloc and parsed.hostname not in {"uaart.com.ua", "www.uaart.com.ua"}):
        return None
    return Path(parsed.path).name


def parse_page(source, car, known_brands):
    page = Page(source)
    nodes = list(page.root.walk())
    visible = [node for node in nodes if not node.hidden]
    headings = [re.sub(r"\s+", " ", node.text()).strip() for node in visible if node.tag == "h1"]
    parsed_brand = parsed_model = parsed_year = None
    if len(headings) == 1:
        match = re.fullmatch(r"(.+?)\s+((?:19|20)\d{2})", headings[0])
        if match:
            parsed_year = match[2]
            title = normalized(match[1])
            matching = [brand for brand in known_brands if title.startswith(normalized(brand) + " ")]
            if matching:
                parsed_brand = max(matching, key=lambda item: len(normalized(item)))
                parsed_model = title[len(normalized(parsed_brand)):].strip()
    expected_vin = re.sub(r"\s+", "", str(car.get("vin") or "")).upper()
    visible_text = page.root.text().upper()
    all_vins = VIN.findall(visible_text)
    expected_count = len(re.findall(r"(?<![A-Z0-9])" + re.escape(expected_vin) + r"(?![A-Z0-9])", visible_text)) if expected_vin else None
    table_vins = []
    for row in visible:
        if row.tag == "tr":
            cells = [child for child in row.children if isinstance(child, Node) and child.tag in {"td", "th"}]
            if len(cells) == 2 and normalized(cells[0].text()) == "vin":
                table_vins.append(re.sub(r"\s+", "", cells[1].text()).upper())
    prices = [re.sub(r"\s+", " ", node.text()).strip() for node in visible if "cena" in node.attrs.get("class", "").split()]
    price = None
    if len(prices) == 1:
        match = re.fullmatch(r"([0-9][0-9\s\u00a0]*)(\s*[$€₴]|\s*(?:USD|UAH|EUR|грн))", prices[0], re.I)
        if match:
            price = {"amount": int(re.sub(r"\s", "", match[1])), "display_currency": match[2].strip()}
    blocks = [node for node in nodes if node.attrs.get("data-ua-additional-spec") == "1"]
    spec_rows = [node for block in blocks for node in block.walk() if "ua-addspec-row" in node.attrs.get("class", "").split() and not node.hidden]
    links = [node.attrs.get("href", "") for node in visible if node.tag == "a"]
    diag = any(local_link_name(link) == car["auto_number"] + "-diag.html" for link in links)
    main_vin = table_vins[0] if len(table_vins) == 1 else None
    crm_price = car.get("price_uah")
    price_comparison = "UNVERIFIED"
    if price is not None and str(crm_price or "").isdigit():
        price_comparison = "MATCH" if int(crm_price) == price["amount"] else "MISMATCH"
    return {"brand": {"parsed": safe_text(parsed_brand) if parsed_brand else None, "comparison": compare(car.get("brand"), parsed_brand)},
            "model": {"parsed": safe_text(parsed_model) if parsed_model else None, "comparison": compare(car.get("model"), parsed_model)},
            "year": {"parsed": parsed_year, "comparison": compare(car.get("year"), parsed_year)},
            "vin": {"main_table": vin_token(main_vin) if main_vin else None, "comparison": compare(expected_vin, main_vin),
                    "expected_visible_count": expected_count, "all_visible_17char_vin_count": len(all_vins),
                    "all_visible_vin_hashes": sorted(set(hashlib.sha256(v.encode()).hexdigest() for v in all_vins)),
                    "one_expected_visible_vin": expected_count == 1 and (len(all_vins) == 1 if len(expected_vin) == 17 else not all_vins),
                    "visibility_method": "static_HTML_text_not_computed_browser_CSS"},
            "price": {"parsed": price, "crm_numeric_field": "price_uah", "numeric_comparison": price_comparison, "currency_comparison": "UNVERIFIED"},
            "specification": {"canonical_marker_start_count": source.count(START), "canonical_marker_end_count": source.count(END),
                              "block_count": len(blocks), "visible_row_count": len(spec_rows),
                              "canonical_data_match": "UNVERIFIED", "field_keys": sorted({node.attrs.get("data-spec-key", "") for node in spec_rows})},
            "diagnostic_link_present": diag}


def required_rule(source):
    if source is None:
        return None
    try:
        tree = ast.parse(source)
        fields_node = next(node.value for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FIELDS" for t in node.targets))
        fields = ast.literal_eval(fields_node)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "missing_required")
        if function.body and isinstance(function.body[0], ast.Expr) and isinstance(function.body[0].value, ast.Constant) and isinstance(function.body[0].value.value, str):
            function.body.pop(0)
        if ast.dump(function, include_attributes=False) != ast.dump(ast.parse(REQUIRED_RULE).body[0], include_attributes=False):
            return None
        result = [(key, label) for key, label, _, required, _, _ in fields if required and key != "published"]
        if any(key not in FIELDS for key, _ in result):
            return None
        return result
    except (ValueError, SyntaxError, StopIteration, TypeError):
        return None


def selected_crm(reads):
    conn = reads.database(reads.root / "crm.db")
    if conn is None:
        raise AuditError("CRM_DATABASE_MISSING")
    with contextlib.closing(conn):
        available = {row[1] for row in conn.execute("PRAGMA table_info(cars)")}
        if not {"id", "auto_number", "vin", "published"} <= available:
            raise AuditError("CRM_IDENTITY_SCHEMA_UNAVAILABLE")
        fields = [field for field in FIELDS if field in available]
        rows = conn.execute("SELECT " + ",".join(fields) + " FROM cars ORDER BY auto_number,id").fetchall()
    return fields, rows


def selected_specs(reads):
    conn = reads.database(reads.root / "vin_specs_task111_v3.db")
    if conn is None:
        return None
    with contextlib.closing(conn):
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not set(SPEC_COLUMNS) <= tables:
            return None
        try:
            return {table: conn.execute("SELECT " + cols + " FROM " + table + " ORDER BY car_uid,field_key").fetchall() for table, cols in SPEC_COLUMNS.items()}
        except sqlite3.OperationalError:
            return None


def audit(root):
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    reads = Reads(root)
    fields, rows = selected_crm(reads)
    raw_specs = selected_specs(reads)
    schema = reads.read(reads.root / "cars_schema.py")
    required = required_rule(schema.decode("utf-8") if schema else None)
    cars = [dict(zip(fields, row)) for row in rows]
    identities = [tuple(car.get(key) for key in IDENTITY_COLUMNS) for car in cars]
    identity_hash = hashlib.sha256(json.dumps(identities, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
    known_brands = {str(car["brand"]) for car in cars if car.get("brand")}
    metadata = {} if raw_specs is None else {(r[0], r[1]): dict(zip(SPEC_COLUMNS["additional_specification_meta"].split(","), r)) for r in raw_specs["additional_specification_meta"]}
    catalogues = {}
    for folder in ("video", "site"):
        data = reads.read(reads.root / folder / "katalog.html")
        links = [] if data is None else [n.attrs.get("href", "") for n in Page(data.decode("utf-8")).root.walk() if n.tag == "a" and not n.hidden]
        catalogues[folder] = {"present": data is not None, "links": links}
    outputs = []
    for car in cars:
        uid = str(car["auto_number"] or "")
        if not UID.fullmatch(uid):
            outputs.append({"crm_row_id": car["id"], "uid": None, "issue": "INVALID_OR_MISSING_UID", "vin": vin_token(car.get("vin"))})
            continue
        facts = [] if raw_specs is None else [r for r in raw_specs["additional_specification"] if r[0] == uid]
        visible_meta = [m for (code, _), m in metadata.items() if code == uid and m["is_visible"]]
        visible_facts = [r for r in facts if not r[7] and (uid, r[1]) in metadata and metadata[(uid, r[1])]["is_visible"] and metadata[(uid, r[1])]["verification_status"] in ACCEPTED]
        missing = None if required is None else [{"field": key, "label": safe_text(label)} for key, label in required if (not car.get(key) if key == "photos" else car.get(key) in (None, "", 0, []))]
        result = {"uid": uid, "crm_row_id": car["id"], "published": car["published"],
                  "brand": safe_text(car.get("brand")), "model": safe_text(car.get("model")), "year": safe_text(car.get("year")),
                  "vin": vin_token(car.get("vin")), "price_fields": {key: car.get(key) if car.get(key) is None or str(car.get(key)).isdigit() else "UNVERIFIED_NON_NUMERIC_VALUE" for key in ("price_uah", "price_total") if key in car},
                  "field_filled": {key: car.get(key) not in (None, "", 0, []) for key in fields if key != "id"},
                  "required_check": {"status": "REVIEWED_SCHEMA_RULE" if required is not None else "UNVERIFIED", "missing": missing,
                                     "runtime_handler_uses_this_rule": "UNVERIFIED", "published_false_is_not_missing": True},
                  "spec_database": {"status": "OBSERVED" if raw_specs is not None else "UNVERIFIED", "stored_fact_count": len(facts),
                                    "visible_meta_count": len(visible_meta), "accepted_visible_fact_count": len(visible_facts), "active_runtime_binding": "UNVERIFIED"},
                  "roots": {}, "risks": []}
        if sum(other.get("auto_number") == uid for other in cars) != 1:
            result["risks"].append("DUPLICATE_CRM_UID")
        for folder in ("video", "site"):
            data = reads.read(reads.root / folder / (uid + ".html"))
            diag = reads.read(reads.root / folder / (uid + "-diag.html"))
            in_catalog = any(local_link_name(link) == uid + ".html" for link in catalogues[folder]["links"])
            page = {"page_present": data is not None, "diagnosis_page_present": diag is not None,
                    "catalog_present": catalogues[folder]["present"], "linked_in_catalog": in_catalog,
                    "http_status": "NOT_REQUESTED", "html_sha256": hashlib.sha256(data).hexdigest() if data else None}
            if data is not None:
                page.update(parse_page(data.decode("utf-8"), car, known_brands))
                page["specification"]["accepted_fact_count_comparison"] = ("UNVERIFIED" if raw_specs is None else "MATCH" if len(visible_facts) == page["specification"]["visible_row_count"] else "MISMATCH")
            result["roots"][folder] = page
            if car["published"] == 1 and (data is None or not in_catalog):
                result["risks"].append(folder + ":PUBLISHED_WITH_MISSING_PAGE_OR_CATALOG_LINK")
            if car["published"] == 0 and (data is not None or in_catalog):
                result["risks"].append(folder + ":DRAFT_HAS_PAGE_OR_CATALOG_LINK")
        outputs.append(result)
    fields_after, rows_after = selected_crm(reads)
    specs_after = selected_specs(reads)
    if fields != fields_after or digest(rows) != digest(rows_after) or digest(raw_specs) != digest(specs_after):
        raise AuditError("SELECTED_DATABASE_ROWS_CHANGED_DURING_AUDIT")
    reads.verify()
    report = {"status": "READ_ONLY_AUDIT_COMPLETED", "started_at_utc": started_at,
              "completed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "production_changed": False, "network_requests": 0,
              "runtime_imported": False, "root_binding": "explicit_path_not_active_process_proof", "crm_rows": len(cars),
              "published_rows": sum(car["published"] == 1 for car in cars), "draft_rows": sum(car["published"] == 0 for car in cars),
              "crm_selected_fields": fields, "crm_selected_sha256_before": digest(rows), "crm_selected_sha256_after": digest(rows_after),
              "crm_identity_sha256": identity_hash, "crm_matches_previous_verified_identity": identity_hash == PREVIOUS_CRM_HASH,
              "spec_semantic_sha256": digest(raw_specs) if raw_specs is not None else None,
              "spec_matches_previous_verified_fields": digest(raw_specs) == PREVIOUS_SPEC_HASH if raw_specs is not None else None,
              "input_files_unchanged": True, "global_atomic_snapshot": False,
              "observed_files": [{"path": str(Path(path).relative_to(reads.root)), "sha256": value} for path, value in sorted(reads.observed.items())],
              "cards": outputs,
              "limits": ["Static HTML parsing; unparsed fields remain UNVERIFIED.", "Displayed price is compared numerically to price_uah; currency semantics are not inferred.",
                         "File presence and catalog links do not establish an HTTP response or working diagnostic content.", "Draft completeness uses only the reviewed schema function; actual publication handler requirements remain UNVERIFIED."]}
    encoded = json.dumps(report, ensure_ascii=False)
    for car in cars:
        raw_vin = str(car.get("vin") or "")
        if len(raw_vin) > 4 and raw_vin in encoded:
            raise AuditError("RAW_VIN_REDACTION_FAILED")
    return report


def compact_lines(report):
    """Small terminal handoff; full details stay in the sanitized JSON file."""
    lines = [json.dumps({"status": "OK", "utc": report["completed_at_utc"], "cards": report["crm_rows"],
                         "pub": report["published_rows"], "draft": report["draft_rows"]}, separators=(",", ":")),
             "Pairs=video/site; h=page v=VIN count s=spec rows:DB facts",
             "c=brand/model/year/VIN/price: M=match X=mismatch U=unverified",
             "d=diagnosis file+link; k=catalog file+link; 1=yes 0=no ?=unknown",
             "req=missing schema fields (drafts); r=risks; -=none"]
    field_codes = {"photos": "PH", "auto_number": "ID", "brand": "BR", "model": "MD", "year": "YR", "vin": "VN",
                   "fuel": "FU", "engine_cc": "CC", "gearbox": "GB", "drive": "DR", "mileage_km": "KM", "color": "CL",
                   "condition_text": "TXT", "price_uah": "PR", "status": "ST"}
    risk_codes = {"DUPLICATE_CRM_UID": "DU", "video:PUBLISHED_WITH_MISSING_PAGE_OR_CATALOG_LINK": "VP",
                  "site:PUBLISHED_WITH_MISSING_PAGE_OR_CATALOG_LINK": "SP", "video:DRAFT_HAS_PAGE_OR_CATALOG_LINK": "VD",
                  "site:DRAFT_HAS_PAGE_OR_CATALOG_LINK": "SD"}
    used_fields, used_risks = set(), set()
    bit = lambda value: "?" if value is None else "1" if value else "0"
    mark = lambda value: {"MATCH": "M", "MISMATCH": "X"}.get(value, "U")
    for card in report["cards"]:
        if card.get("uid") is None:
            lines.append("row=" + str(card.get("crm_row_id")) + " INVALID_OR_MISSING_UID")
            continue
        pages = [card["roots"][folder] for folder in ("video", "site")]
        pairs = lambda get: "/".join(str(get(page)) for page in pages)
        comparisons = pairs(lambda page: "".join(mark(page.get(key, {}).get("comparison")) for key in ("brand", "model", "year", "vin")) + mark(page.get("price", {}).get("numeric_comparison")))
        missing = card["required_check"]["missing"] if card["published"] == 0 else []
        required = "?" if missing is None else ",".join(field_codes.get(row["field"], "OTHER") for row in missing) or "-"
        used_fields.update(row["field"] for row in missing or [])
        used_risks.update(card["risks"])
        risks = ",".join(risk_codes.get(risk, "OTHER") for risk in card["risks"]) or "-"
        stored = card["spec_database"]["stored_fact_count"] if card["spec_database"]["status"] == "OBSERVED" else "?"
        year = card["year"] if re.fullmatch(r"\d{4}", card["year"]) else "?"
        lines.append(f"{card['uid']} y{year} p{card['published']} "
                     f"h{pairs(lambda page: bit(page['page_present']))} "
                     f"v{pairs(lambda page: page.get('vin', {}).get('expected_visible_count', '?'))} "
                     f"s{pairs(lambda page: page.get('specification', {}).get('visible_row_count', '?'))}:{stored} "
                     f"c{comparisons} "
                     f"d{pairs(lambda page: bit(page['diagnosis_page_present']) + bit(page.get('diagnostic_link_present')))} "
                     f"k{pairs(lambda page: bit(page['catalog_present']) + bit(page['linked_in_catalog']))} "
                     f"req{required} r{risks}")
    for keys, prefix, codes in ((used_fields, "req", field_codes), (used_risks, "risk", risk_codes)):
        chunk_size = 1 if prefix == "risk" else 4
        for offset in range(0, len(keys), chunk_size):
            lines.append(prefix + ": " + "; ".join(codes.get(key, "OTHER") + "=" + key for key in sorted(keys)[offset:offset + chunk_size]))
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = Path(os.path.abspath(args.root)), Path(os.path.abspath(args.output))
    allowed = root / STAGE_NAME
    if allowed not in output.parents or not output.parent.is_dir() or output.exists():
        raise AuditError("OUTPUT_MUST_BE_NEW_FILE_INSIDE_EXISTING_ISOLATED_STAGE")
    Reads(root).safe(output)
    report = audit(root)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(output, flags, 0o600), "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("\n".join(compact_lines(report)))


if __name__ == "__main__":
    main()
