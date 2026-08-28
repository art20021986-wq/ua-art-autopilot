#!/usr/bin/env python3
"""Build a static SEO release candidate from one immutable public baseline."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
META_ROBOTS = re.compile(r"<meta\b(?=[^>]*\bname\s*=\s*['\"]robots['\"])[^>]*>\s*", re.I)
META_DESCRIPTION = re.compile(r"<meta\b(?=[^>]*\bname\s*=\s*['\"]description['\"])[^>]*>\s*", re.I)
CANONICAL = re.compile(r"<link\b(?=[^>]*\brel\s*=\s*['\"][^'\"]*canonical[^'\"]*['\"])[^>]*>\s*", re.I)
TITLE = re.compile(r"<title\b[^>]*>([\s\S]*?)</title\s*>", re.I)
BODY = re.compile(r"(<body\b[^>]*>)([\s\S]*?)(</body\s*>)", re.I)
DIAG_ANCHOR = re.compile(r"<a\b(?=[^>]*\bclass\s*=\s*['\"][^'\"]*mcf-diag-cta[^'\"]*['\"])[^>]*>[\s\S]*?</a>\s*", re.I)


DESCRIPTIONS = {
    "/video/index.html": "UA ART — авто з Кореї під ключ у Києві та Україні: підбір, доставка, діагностика й супровід угоди.",
    "/video/katalog.html": "Каталог перевірених авто з Кореї UA ART: актуальні машини, етап доставки, ціна та діагностика.",
    "/video/info.html": "Умови купівлі та доставки авто з Кореї в Україну з UA ART: етапи, оплата й супровід.",
    "/video/podbor.html": "Підбір авто з Кореї під бюджет у Києві: залиште вимоги до моделі та отримайте персональний варіант від UA ART.",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def description_for(path: str) -> str:
    match = re.search(r"UA-\d{4}", path)
    if match:
        vehicle_id = match.group(0)
        return f"{vehicle_id} — авто з Кореї від UA ART: актуальний етап, характеристики, ціна, діагностика та бронювання за $500."
    return DESCRIPTIONS[path]


def schema_for(path: str, canonical: str) -> str:
    if path != "/video/index.html":
        return ""
    payload = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "@id": "https://www.uaart.com.ua/#organization", "name": "UA ART", "url": canonical},
            {"@type": "WebSite", "@id": "https://www.uaart.com.ua/#website", "name": "UA ART", "url": canonical},
        ],
    }
    return '<script type="application/ld+json">' + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "</script>"


def insert_head(source: str, path: str, base_url: str) -> str:
    canonical = base_url.rstrip("/") + path
    cleaned = CANONICAL.sub("", META_DESCRIPTION.sub("", META_ROBOTS.sub("", source)))
    vehicle = re.search(r"UA-\d{4}", path)
    if vehicle:
        current = TITLE.search(cleaned)
        model = re.sub(r"\s*[—|-]\s*UA ART COMPANY\s*$", "", current.group(1).strip(), flags=re.I) if current else vehicle.group(0)
        unique_title = f"{model} — {vehicle.group(0)} | UA ART"
        if current:
            cleaned = TITLE.sub(f"<title>{html.escape(unique_title)}</title>", cleaned, count=1)
        else:
            cleaned = f"<title>{html.escape(unique_title)}</title>" + cleaned
    additions = (
        f'\n<link rel="canonical" href="{html.escape(canonical, quote=True)}">'
        f'\n<meta name="description" content="{html.escape(description_for(path), quote=True)}">'
        '\n<base href="https://www.uaart.com.ua/video/">'
        '\n<style id="seo-preview-guard">body::before{content:"GITHUB PREVIEW · PRODUCTION WRITE NO";'
        'position:fixed;z-index:2147483647;top:0;left:0;right:0;padding:7px 12px;text-align:center;'
        'font:700 12px system-ui;background:#7c3aed;color:#fff;pointer-events:none}</style>'
        '\n<script id="seo-preview-guard-script">addEventListener("click",function(e){if(e.target.closest('
        '"a,button,[onclick]")){e.preventDefault();e.stopImmediatePropagation();}},true);'
        'addEventListener("submit",function(e){e.preventDefault();e.stopImmediatePropagation();},true);</script>'
    )
    schema = schema_for(path, canonical)
    if schema:
        additions += "\n" + schema
    if re.search(r"</head\s*>", cleaned, re.I):
        return re.sub(r"</head\s*>", additions + "\n</head>", cleaned, count=1, flags=re.I)
    if re.search(r"<html\b[^>]*>", cleaned, re.I):
        return re.sub(r"(<html\b[^>]*>)", r"\1\n<head>" + additions + "\n</head>", cleaned, count=1, flags=re.I)
    return "<head>" + additions + "\n</head>\n" + cleaned


def patch_cta(source: str, path: str, patch_ids: set[str]) -> tuple[str, int]:
    vehicle = next((item for item in patch_ids if item in path), "")
    if not vehicle:
        return source, 0
    result, ru = re.subn(r"Купить авто", "Забронировать авто за 500$", source)
    result, uk = re.subn(r"Купити авто", "Забронировать авто за 500$", result)
    return result, ru + uk


def diagnostic_block(vehicle_id: str) -> str:
    return (
        f'<a class="mcf-diag-cta" href="{vehicle_id}-diag.html" '
        'style="display:flex;align-items:center;gap:12px;margin:14px 0;padding:15px 16px;'
        'border-radius:14px;text-decoration:none;background:linear-gradient(180deg,rgba(212,175,55,.20),'
        'rgba(212,175,55,.08));border:1px solid rgba(212,175,55,.55);color:#f4e3ae">'
        '<span style="font-size:22px;line-height:1">🔧</span><span style="flex:1">'
        '<span style="display:block;font-weight:800;font-size:16px">Открыть комплексную диагностику →</span>'
        '<span style="display:block;font-size:13px;opacity:.85;margin-top:3px">ЛКП · OBD · ходовая · фото · видео</span>'
        '</span><span style="font-size:20px;opacity:.8">›</span></a>'
    )


def ensure_diagnostic_link(source: str, path: str, verified: set[str]) -> tuple[str, int]:
    match = re.search(r"UA-\d{4}", path)
    if not match or DIAG_ANCHOR.search(source):
        return source, 0
    vehicle_id = match.group(0)
    if vehicle_id not in verified:
        return source, 0
    purchase = re.search(r"<a\b(?=[^>]*\bclass\s*=\s*['\"][^'\"]*\bkn_kupit\b[^'\"]*['\"])[^>]*>", source, re.I)
    if not purchase:
        return source, 0
    return source[:purchase.start()] + diagnostic_block(vehicle_id) + source[purchase.start():], 1


def body_text(source: str) -> str:
    match = BODY.search(source)
    return match.group(2) if match else source


def normalize_allowed_body(source: str) -> str:
    source = DIAG_ANCHOR.sub("", source)
    for value in ("Купить авто", "Купити авто", "Забронировать авто за 500$"):
        source = source.replace(value, "__APPROVED_CTA_TEXT__")
    return source


def output_path(site: Path, url_path: str) -> Path:
    return site / url_path.lstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    baseline = json.loads((args.baseline_dir / "BASELINE-SEO-001.json").read_text(encoding="utf-8"))
    by_path = {item["path"]: item for item in baseline["pages"]}
    verified_diagnostics = {
        re.search(r"UA-\d{4}", item["path"]).group(0)
        for item in baseline.get("diagnostic_pages", [])
        if item.get("status") == 200 and re.search(r"UA-\d{4}", item["path"])
    }
    site = args.output / "site"
    rollback = args.output / "rollback"
    if args.output.exists():
        shutil.rmtree(args.output)
    site.mkdir(parents=True)
    rollback.mkdir(parents=True)
    diffs = []
    manifest = []
    patch_ids = set(config["cta_patch_ids"])

    for path in config["index_paths"]:
        item = by_path[path]
        raw_path = args.baseline_dir / "raw" / item["snapshot_file"]
        raw = raw_path.read_bytes()
        source = raw.decode("utf-8", errors="replace")
        candidate = insert_head(source, path, config["base_url"])
        candidate, diagnostic_injected = ensure_diagnostic_link(candidate, path, verified_diagnostics)
        candidate, replacements = patch_cta(candidate, path, patch_ids)
        destination = output_path(site, path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = candidate.encode("utf-8")
        destination.write_bytes(data)
        original_body = normalize_allowed_body(body_text(source)).encode("utf-8")
        candidate_body = normalize_allowed_body(body_text(candidate)).encode("utf-8")
        diffs.append({
            "path": path,
            "baseline_sha256": item["sha256"],
            "candidate_sha256": sha(data),
            "protected_body_equal_after_allowlist": sha(original_body) == sha(candidate_body),
            "diagnostic_link_injected": diagnostic_injected,
            "approved_cta_replacements": replacements,
        })
        manifest.append({"path": path, "sha256": sha(data), "baseline_sha256": item["sha256"]})

    robots = "User-agent: *\nAllow: /\nDisallow: /video/preview/\nSitemap: https://www.uaart.com.ua/sitemap.xml\n"
    (site / "robots.txt").write_text(robots, encoding="utf-8")
    sitemap_urls = "".join(f"  <url><loc>{html.escape(config['base_url'].rstrip('/') + p)}</loc></url>\n" for p in config["index_paths"])
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + sitemap_urls + "</urlset>\n"
    (site / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (site / "_redirects").write_text("/ /video/index.html 301\n", encoding="utf-8")
    for special in ("robots.txt", "sitemap.xml", "_redirects"):
        data = (site / special).read_bytes()
        manifest.append({"path": "/" + special, "sha256": sha(data), "baseline_sha256": None})

    manifest.sort(key=lambda item: item["path"])
    (args.output / "CANDIDATE-MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "PROTECTED-DIFF.json").write_text(json.dumps(diffs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rollback_result = {
        "mode": "sandbox-only",
        "source_manifest_matches": all(
            sha((args.baseline_dir / "raw" / item["snapshot_file"]).read_bytes()) == item["sha256"]
            for item in baseline["pages"] + baseline.get("diagnostic_pages", []) if item["snapshot_file"]
        ),
        "production_write": False,
    }
    (rollback / "ROLLBACK-TEST.json").write_text(json.dumps(rollback_result, indent=2) + "\n", encoding="utf-8")
    (rollback / "README.md").write_text(
        "# Sandbox rollback\n\nDelete the generated candidate and rebuild it from the immutable baseline. "
        "No production rollback is authorized or performed by this package.\n",
        encoding="utf-8",
    )
    print(json.dumps({"pages": len(config["index_paths"]), "output": str(args.output), "production_write": False}))
    return 0 if rollback_result["source_manifest_matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
