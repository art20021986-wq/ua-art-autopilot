#!/usr/bin/env python3
"""Read-only production preflight for SEO-REHAB-GUARD-068.

The script downloads a bounded allow-list of PythonAnywhere files with GET only
and emits structural evidence. It never prints source bodies, credentials, or
database content.
"""
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


API_ROOT = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
HOME = "/home/Carix"
MAX_BYTES = 24 * 1024 * 1024
OUTPUT = pathlib.Path("cloud/seo_rehab_guard_068/evidence/preflight.json")

SOURCE_PATHS = (
    f"{HOME}/stranica.py",
    f"{HOME}/yadro.py",
    f"{HOME}/master_card.py",
)
OPTIONAL_ROUTE_PATHS = (
    "/var/www/www_uaart_com_ua_wsgi.py",
    f"{HOME}/webapp.py",
    f"{HOME}/flask_app.py",
    f"{HOME}/wsgi.py",
)
TARGET_FUNCTIONS = {
    "sobrat_kartochku", "sobrat_katalog", "karta_html", "katalog_html",
    "obrabotat_kartochku", "obrabotat_obshuyu", "proverit",
}
MARKERS = (
    "UA-CARDS-STAGE-ANCHOR-001-V1.1-MASTER-FINAL",
    "UA-CARDS-FERRY-VIN-001-V1.1-PERMANENT",
    "ua-art-diagnostics-permanent-v1",
    "UA-ART-DELIVERY-STAGES-PERMANENT-V1:START",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(path: str, *, optional: bool = False) -> bytes | None:
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
    if not token:
        raise RuntimeError("PYTHONANYWHERE_TOKEN_MISSING")
    request = urllib.request.Request(
        API_ROOT + urllib.parse.quote(path, safe="/"),
        headers={
            "Authorization": "Token " + token,
            "User-Agent": "ua-art-seo-rehab-068-preflight/1 (read-only)",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if optional and exc.code in (403, 404):
            return None
        raise
    if len(payload) > MAX_BYTES:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE:" + path)
    return payload


def function_record(source: str, node: ast.AST, ordinal: int) -> dict:
    lines = source.splitlines()
    segment = "\n".join(lines[node.lineno - 1:node.end_lineno])
    args = [item.arg for item in node.args.posonlyargs + node.args.args]
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    args.extend(item.arg for item in node.args.kwonlyargs)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    return {
        "name": node.name,
        "ordinal": ordinal,
        "async": isinstance(node, ast.AsyncFunctionDef),
        "args": args,
        "line_start": node.lineno,
        "line_end": node.end_lineno,
        "sha256": sha(segment.encode("utf-8")),
        "returns": sum(isinstance(item, ast.Return) for item in ast.walk(node)),
    }


def inspect_source(path: str, payload: bytes) -> dict:
    text = payload.decode("utf-8")
    tree = ast.parse(text, filename=path)
    found = []
    counts: dict[str, int] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in TARGET_FUNCTIONS:
            counts[node.name] = counts.get(node.name, 0) + 1
            found.append(function_record(text, node, counts[node.name]))
    route_lines = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if re.search(r"robots|sitemap|send_from_directory|send_file|redirect", line, re.I):
            route_lines.append({"line": line_number, "sha256": sha(line.strip().encode("utf-8"))})
    return {
        "path": path,
        "bytes": len(payload),
        "sha256": sha(payload),
        "markers": {marker: text.count(marker) for marker in MARKERS},
        "functions": found,
        "route_line_hashes": route_lines[:80],
    }


def html_facts(path: str, payload: bytes) -> dict:
    text = payload.decode("utf-8", errors="replace")
    canonical = re.findall(
        r'<link\b(?=[^>]*\brel=["\'][^"\']*canonical[^"\']*["\'])'
        r'(?=[^>]*\bhref=["\']([^"\']+)["\'])[^>]*>', text, re.I,
    )
    robots = re.findall(
        r'<meta\b(?=[^>]*\bname=["\']robots["\'])'
        r'(?=[^>]*\bcontent=["\']([^"\']*)["\'])[^>]*>', text, re.I,
    )
    identifier = pathlib.PurePosixPath(path).stem.upper()
    diagnostic_links = [value.upper() for value in re.findall(
        r'href=["\'](?:[^"\']*/)?(UA-[0-9]{4,}-diag\.html)(?:\?[^"\']*)?["\']', text, re.I,
    )]
    return {
        "path": path,
        "exists": True,
        "bytes": len(payload),
        "sha256": sha(payload),
        "canonical": canonical,
        "robots": robots,
        "diagnostic_links": diagnostic_links,
        "same_id_diagnostic": identifier.startswith("UA-") and diagnostic_links.count(identifier + "-DIAG.HTML") == 1,
        "legacy_cta": bool(re.search(r"Купить авто|Купити авто", text, re.I)),
        "cta_500": bool(re.search(r"Задаток\s*500\s*\$", text, re.I)),
    }


def main() -> int:
    evidence = {
        "contract": "SEO-REHAB-GUARD-068",
        "mode": "read-only-preflight",
        "production_write": False,
        "sources": [],
        "routes": [],
        "html": [],
        "errors": [],
    }
    try:
        for path in SOURCE_PATHS:
            evidence["sources"].append(inspect_source(path, fetch(path)))
        for path in OPTIONAL_ROUTE_PATHS:
            payload = fetch(path, optional=True)
            if payload is not None:
                evidence["routes"].append(inspect_source(path, payload))
        page_paths = [
            f"{HOME}/video/index.html", f"{HOME}/video/katalog.html",
            f"{HOME}/site/index.html", f"{HOME}/site/katalog.html",
        ]
        page_paths.extend(
            f"{root}/UA-{index:04d}.html"
            for root in (f"{HOME}/video", f"{HOME}/site")
            for index in range(1, 11)
        )
        for path in page_paths:
            payload = fetch(path, optional=True)
            if payload is not None:
                evidence["html"].append(html_facts(path, payload))
        if len(evidence["sources"]) != len(SOURCE_PATHS):
            raise RuntimeError("SOURCE_SET_INCOMPLETE")
        if not evidence["html"]:
            raise RuntimeError("HTML_SET_EMPTY")
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if evidence["errors"]:
        raise SystemExit("PREFLIGHT_BLOCKED:" + ";".join(evidence["errors"]))
    print("SEO_REHAB_068_PREFLIGHT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
