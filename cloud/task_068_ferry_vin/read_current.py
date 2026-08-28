#!/usr/bin/env python3
"""Read-only production snapshot for UA-CARDS-FERRY-VIN-001 V1.1."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import tempfile
import urllib.error
import urllib.parse
import urllib.request


API = "https://www.pythonanywhere.com/api/v0/user/Carix/"
ROOT = "/home/Carix"
REMOTE = {
    "cars_ui.py": ROOT + "/cars_ui.py",
    "master_card.py": ROOT + "/master_card.py",
    "team_bot.py": ROOT + "/team_bot.py",
    "stranica.py": ROOT + "/stranica.py",
    "yadro.py": ROOT + "/yadro.py",
    "db.py": ROOT + "/db.py",
    "start_safe.py": ROOT + "/start_safe.py",
}
CRM_PATH = ROOT + "/crm.db"
CATALOG_PATHS = {
    "video": ROOT + "/video/katalog.html",
    "site": ROOT + "/site/katalog.html",
}
OUT = pathlib.Path("cloud/task_068_ferry_vin/evidence/current.json")
MAX_FILE = 2_000_000
CARD_RE = re.compile(r"^UA-[0-9]{4,}$")
BUTTON_FILES = {"cars_ui.py", "team_bot.py"}
WANTED_DEFINITIONS = {
    "cars_ui.py": {
        "card_kb", "open_card", "edit_menu", "edit_ask", "apply_value",
        "condition_screen", "stage_menu", "stage_set", "price_screen",
        "preview", "register", "catch_message", "save_media",
    },
    "team_bot.py": {"start", "intake", "build_application"},
    "master_card.py": {"obrabotat_kartochku", "obrabotat_obshuyu", "proverit"},
    "stranica.py": {"karta", "karta_html", "sobrat_katalog", "sobrat_kartochku", "render", "zapisat", "main"},
    "yadro.py": {"karta", "karta_html", "katalog_html", "render", "zapisat", "main"},
    "db.py": {"connect", "update_card_field"},
    "start_safe.py": {"main", "apply_all"},
}
WANTED_ASSIGNMENTS = {
    "EDITABLE", "LABELS_ALL", "DNEI_GRUZIA_UKRAINA", "STAGES",
    "STATUS_LABELS", "STATUSY", "KODY",
}
STAGE_TERMS = (
    "дней до выдачи", "дни до выдачи", "дня до выдачи", "день до выдачи",
    "ориентировочная дата выдачи", "календарная дата выдачи",
    "корея", "паром", "грузия", "киев", "days_to_kyiv", "eta_manual",
    "ge_to_kyiv", "sea_container", "progress", "shkala", "шкала",
    "vin", "engine_cc", "см³", "в море", "море", "морі", "catalog-card",
)

PUBLIC_FIELDS = (
    "id", "auto_number", "published", "status", "brand", "model", "year",
    "vin", "engine_cc", "fuel", "eta_manual", "sea_date_out",
    "sea_container", "vyehal",
)
FORBIDDEN_USER_PATTERNS = (
    r"(?i)(?<![A-Za-zА-Яа-яЁёІіЇїЄє])в\s+море(?![A-Za-zА-Яа-яЁёІіЇїЄє])",
    r"(?i)(?<![A-Za-zА-Яа-яЁёІіЇїЄє])на\s+море(?![A-Za-zА-Яа-яЁёІіЇїЄє])",
    r"(?i)(?<![A-Za-zА-Яа-яЁёІіЇїЄє])у\s+мор[іi](?![A-Za-zА-Яа-яЁёІіЇїЄє])",
    r"(?i)(?<![A-Za-zА-Яа-яЁёІіЇїЄє])в\s+мор[іi](?![A-Za-zА-Яа-яЁёІіЇїЄє])",
    r"(?i)(?<![A-Za-zА-Яа-яЁёІіЇїЄє])мор(?:е|ем|ской|ська|ем)(?![A-Za-zА-Яа-яЁёІіЇїЄє])",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact(text: str) -> str:
    text = re.sub(r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b", "<redacted-token>", text)
    text = re.sub(r"(?i)(token\s*=\s*)['\"][^'\"]{20,}['\"]", r"\1'<redacted-token>'", text)
    return text


def read_remote(path: str, *, missing_ok: bool = False) -> bytes:
    request = urllib.request.Request(
        API + "files/path" + urllib.parse.quote(path, safe="/"),
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task068-ferry-vin-read/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(MAX_FILE + 1)
    except urllib.error.HTTPError as exc:
        if missing_ok and exc.code == 404:
            return b""
        raise
    if len(data) > MAX_FILE:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE:" + pathlib.PurePosixPath(path).name)
    return data


def source_segment(source: str, node: ast.AST) -> str:
    lines = source.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def parent_functions(tree: ast.AST) -> dict[int, str | None]:
    result: dict[int, str | None] = {}

    def visit(node: ast.AST, owner: str | None = None) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = node.name
        result[id(node)] = owner
        for child in ast.iter_child_nodes(node):
            visit(child, owner)

    visit(tree)
    return result


def button_inventory(source: str, tree: ast.AST) -> list[dict]:
    parents = parent_functions(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else ""
        )
        if name not in {"InlineKeyboardButton", "KeyboardButton"}:
            continue
        label = ast.get_source_segment(source, node.args[0]) if node.args else ""
        callback = ""
        url = ""
        for kw in node.keywords:
            if kw.arg == "callback_data":
                callback = ast.get_source_segment(source, kw.value) or ""
            elif kw.arg == "url":
                url = ast.get_source_segment(source, kw.value) or ""
        found.append({
            "line": node.lineno,
            "function": parents.get(id(node)),
            "label_expr": redact(label or ""),
            "callback_expr": redact(callback),
            "url_expr": redact(url),
        })
    return sorted(found, key=lambda item: item["line"])


def relevant_snippets(source: str, radius: int = 36) -> list[dict]:
    lines = source.splitlines()
    ranges = []
    for index, line in enumerate(lines):
        if any(term in line.casefold() for term in STAGE_TERMS):
            ranges.append((max(0, index - radius), min(len(lines), index + radius + 1)))
    merged = []
    for start, end in ranges:
        if merged and start <= merged[-1][1] + 3:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return [
        {"start_line": start + 1, "end_line": end, "source": redact("\n".join(lines[start:end]))}
        for start, end in merged[:18]
    ]


def inspect_python(filename: str, path: str) -> dict:
    data = read_remote(path)
    source = data.decode("utf-8")
    tree = ast.parse(source, path)
    definitions = []
    assignments = []
    inventory = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            segment = source_segment(source, node)
            wanted = node.name in WANTED_DEFINITIONS.get(filename, set())
            if filename in {"stranica.py", "yadro.py", "master_card.py"} and any(
                term in segment.casefold() for term in STAGE_TERMS
            ):
                wanted = True
            inventory.append({
                "name": node.name,
                "kind": type(node).__name__,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "sha256": sha256(segment.encode()),
                "stage_related": any(term in segment.casefold() for term in STAGE_TERMS),
            })
            if wanted:
                definitions.append({
                    "name": node.name,
                    "kind": type(node).__name__,
                    "line": node.lineno,
                    "end_line": node.end_lineno,
                    "sha256": sha256(segment.encode()),
                    "source": redact(segment[:120_000]),
                })
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = []
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
            if any(name in WANTED_ASSIGNMENTS for name in names):
                segment = source_segment(source, node)
                assignments.append({"names": names, "line": node.lineno, "source": redact(segment)})
    result = {
        "path": path,
        "sha256": sha256(data),
        "size": len(data),
        "definitions": definitions,
        "assignments": assignments,
        "definition_inventory": inventory,
        "stage_snippets": relevant_snippets(source),
    }
    if filename in BUTTON_FILES:
        result["buttons"] = button_inventory(source, tree)
    return result


def html_fragment(source: str) -> str:
    folded = source.casefold()
    positions = [folded.find(term) for term in STAGE_TERMS if folded.find(term) >= 0]
    if not positions:
        return ""
    start = max(0, min(positions) - 5500)
    end = min(len(source), max(positions) + 8500)
    return source[start:end]


def inspect_cards() -> dict:
    cards = {}
    for number in range(1, 101):
        card_id = "UA-%04d" % number
        video_path = ROOT + "/video/" + card_id + ".html"
        video = read_remote(video_path, missing_ok=True)
        if not video:
            continue
        roots = {}
        for root in ("video", "site"):
            path = ROOT + "/" + root + "/" + card_id + ".html"
            data = read_remote(path, missing_ok=True)
            if not data:
                roots[root] = {"exists": False}
                continue
            source = data.decode("utf-8", "replace")
            roots[root] = {
                "exists": True,
                "path": path,
                "sha256": sha256(data),
                "size": len(data),
                "diagnostics_links": len(re.findall(
                    re.escape(card_id) + r"-diag\.html", source, re.IGNORECASE
                )),
                "permanent_diagnostics_marker": "ua-art-diagnostics-permanent-v1" in source,
                "stage_anchor_count": source.count("UA-ART-DELIVERY-STAGES-PERMANENT-V1:START"),
                "vin_guard_count": source.count("UA-ART-VIN-GUARD-LITE-V1:START"),
                "vin_button_count": len(re.findall(r">\s*(?:🛡\s*)?Проверить VIN(?:\s*→)?\s*<", source, re.IGNORECASE)),
                "forbidden_sea_terms": sum(len(re.findall(pattern, source)) for pattern in FORBIDDEN_USER_PATTERNS),
                "fragment": html_fragment(source),
            }
        cards[card_id] = roots
    return cards


def inspect_db() -> dict:
    data = read_remote(CRM_PATH)
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
        connection = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            quick = connection.execute("PRAGMA quick_check").fetchone()[0]
            columns = [str(row[1]) for row in connection.execute("PRAGMA table_info(cars)")]
            selected = [name for name in PUBLIC_FIELDS if name in columns]
            rows = [dict(row) for row in connection.execute(
                "SELECT %s FROM cars WHERE published=1 ORDER BY id" % ",".join(selected)
            )]
        finally:
            connection.close()
    finally:
        path.unlink(missing_ok=True)
    return {
        "sha256": sha256(data),
        "size": len(data),
        "quick_check": str(quick),
        "columns": columns,
        "rows": rows,
    }


def inspect_catalogs() -> dict:
    result = {}
    for root, path in CATALOG_PATHS.items():
        data = read_remote(path, missing_ok=True)
        if not data:
            result[root] = {"exists": False}
            continue
        source = data.decode("utf-8", "replace")
        cards = []
        for match in re.finditer(
            r'<article\b[^>]*class=["\'][^"\']*catalog-card[^"\']*["\'][^>]*>.*?</article\s*>',
            source, re.IGNORECASE | re.DOTALL,
        ):
            block = match.group(0)
            identifier = (re.search(r"UA-\d{4,}", block) or [""])[0]
            engine = re.search(r"([0-9][0-9\s\u00a0]*)\s*см³", block, re.IGNORECASE)
            vin = re.search(r"\b[A-HJ-NPR-Z0-9]{17}\b", block, re.IGNORECASE)
            cards.append({
                "id": identifier,
                "engine_cc": re.sub(r"\s", "", engine.group(1)) if engine else None,
                "vin": vin.group(0).upper() if vin else None,
                "stage": (re.search(r"data-stage=[\"']([^\"']+)", block, re.IGNORECASE) or [None, None])[1],
                "vin_button_count": len(re.findall(r"Проверить VIN", block, re.IGNORECASE)),
                "forbidden_sea_terms": sum(len(re.findall(pattern, block)) for pattern in FORBIDDEN_USER_PATTERNS),
            })
        result[root] = {
            "exists": True,
            "path": path,
            "sha256": sha256(data),
            "size": len(data),
            "cards": cards,
            "forbidden_sea_terms": sum(len(re.findall(pattern, source)) for pattern in FORBIDDEN_USER_PATTERNS),
            "visible_ferry_terms": len(re.findall(r"На\s+пароме|На\s+поромі", source, re.IGNORECASE)),
        }
    return result


def main() -> None:
    evidence = {
        "task_id": "UA-CARDS-FERRY-VIN-001-V1.1",
        "mode": "READ_ONLY_FERRY_VIN_ENGINE_DISCOVERY",
        "production_touched": False,
        "llm_tokens": 0,
        "files": {},
        "cards": {},
        "catalogs": {},
        "db": {},
        "errors": [],
    }
    for filename, path in REMOTE.items():
        evidence["files"][filename] = inspect_python(filename, path)
    evidence["cards"] = inspect_cards()
    evidence["catalogs"] = inspect_catalogs()
    evidence["db"] = inspect_db()
    card_ids = sorted(evidence["cards"])
    if len(card_ids) != 10 or "UA-0009" not in card_ids:
        raise RuntimeError("PUBLISHED_CARD_SET_UNEXPECTED:" + ",".join(card_ids))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TASK068_FERRY_VIN_READ_PASS cards=%d warnings=%d" % (
        len(card_ids), len(evidence["errors"])
    ))


if __name__ == "__main__":
    main()
