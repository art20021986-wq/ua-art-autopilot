#!/usr/bin/env python3
"""Read-only production snapshot for UA-CARDS-STAGE-ANCHOR-001 V1.1."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request


API = "https://www.pythonanywhere.com/api/v0/user/Carix/"
ROOT = "/home/Carix"
REMOTE = {
    "cars_ui.py": ROOT + "/cars_ui.py",
    "team_bot.py": ROOT + "/team_bot.py",
    "stranica.py": ROOT + "/stranica.py",
    "yadro.py": ROOT + "/yadro.py",
    "db.py": ROOT + "/db.py",
    "start_safe.py": ROOT + "/start_safe.py",
}
OUT = pathlib.Path("cloud/task_066_stage_anchor/evidence/current.json")
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
    "stranica.py": {"karta", "karta_html", "render", "zapisat", "main"},
    "yadro.py": {"karta", "karta_html", "render", "zapisat", "main"},
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
            "User-Agent": "ua-art-task066-stage-anchor-read/1",
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
            if filename in {"stranica.py", "yadro.py"} and any(
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
                "fragment": html_fragment(source),
            }
        cards[card_id] = roots
    return cards


def main() -> None:
    evidence = {
        "task_id": "UA-CARDS-STAGE-ANCHOR-001-V1.1",
        "mode": "READ_ONLY_CURRENT_STAGE_AND_KEYBOARD",
        "production_touched": False,
        "llm_tokens": 0,
        "files": {},
        "cards": {},
        "errors": [],
    }
    for filename, path in REMOTE.items():
        evidence["files"][filename] = inspect_python(filename, path)
    evidence["cards"] = inspect_cards()
    card_ids = sorted(evidence["cards"])
    if len(card_ids) != 10 or "UA-0009" not in card_ids:
        raise RuntimeError("PUBLISHED_CARD_SET_UNEXPECTED:" + ",".join(card_ids))
    if evidence["files"]["cars_ui.py"]["sha256"] != (
        "721e21f43787832b325c1fc806a64f332cb14a26bd63b297cb738c9fbb687563"
    ):
        evidence["errors"].append("cars_ui_changed_since_photo_probe")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TASK066_STAGE_ANCHOR_READ_PASS cards=%d warnings=%d" % (
        len(card_ids), len(evidence["errors"])
    ))


if __name__ == "__main__":
    main()
