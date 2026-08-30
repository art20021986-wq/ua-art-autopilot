#!/usr/bin/env python3
"""Read-only browser-rendered probe for UA ART catalog visual acceptance."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import time
from typing import Any

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "cloud/task_095_catalog_visual_repair/evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)
BASE = "https://www.uaart.com.ua"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def probe_page(browser, *, label: str, path: str, viewport: dict[str, int]) -> dict[str, Any]:
    console_errors: list[str] = []
    page_errors: list[str] = []
    request_failures: list[str] = []
    page = browser.new_page(viewport=viewport, device_scale_factor=1)
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "requestfailed",
        lambda request: request_failures.append(
            f"{request.resource_type}:{request.url}:{request.failure or 'failed'}"
        ),
    )
    url = f"{BASE}{path}?task095={int(time.time() * 1000)}"
    response = None
    navigation_error = None
    try:
        response = page.goto(url, wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(4_000)
    except Exception as exc:  # evidence must still be written
        navigation_error = f"{type(exc).__name__}:{exc}"

    data = page.evaluate(
        """
        () => {
          const css = (el) => {
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            const ancestors = [];
            let p = el;
            while (p && p !== document.documentElement) {
              const ps = getComputedStyle(p);
              if (ps.display === 'none' || ps.visibility === 'hidden' || Number(ps.opacity) === 0 || p.hidden || p.getAttribute('aria-hidden') === 'true') {
                ancestors.push({
                  tag: p.tagName,
                  id: p.id || '',
                  className: String(p.className || '').slice(0, 300),
                  display: ps.display,
                  visibility: ps.visibility,
                  opacity: ps.opacity,
                  hidden: Boolean(p.hidden),
                  ariaHidden: p.getAttribute('aria-hidden')
                });
              }
              p = p.parentElement;
            }
            const rendered = r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity) > 0 && !el.hidden;
            const inViewport = rendered && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
            return {
              display: s.display,
              visibility: s.visibility,
              opacity: s.opacity,
              position: s.position,
              overflow: s.overflow,
              overflowX: s.overflowX,
              overflowY: s.overflowY,
              width: r.width,
              height: r.height,
              top: r.top,
              left: r.left,
              bottom: r.bottom,
              right: r.right,
              rendered,
              inViewport,
              hiddenAncestors: ancestors
            };
          };
          const cardNodes = Array.from(document.querySelectorAll('article.catalog-card'));
          const cards = cardNodes.map((el) => {
            const images = Array.from(el.querySelectorAll('img')).map((img) => ({
              src: img.getAttribute('src') || '',
              currentSrc: img.currentSrc || '',
              complete: img.complete,
              naturalWidth: img.naturalWidth,
              naturalHeight: img.naturalHeight,
              loading: img.loading || '',
              style: css(img)
            }));
            return {
              id: el.getAttribute('data-ua-card') || (el.textContent.match(/UA-\d{4,}/i) || [''])[0],
              stage: el.getAttribute('data-stage') || '',
              className: String(el.className || ''),
              style: css(el),
              images,
              text: (el.innerText || '').trim().slice(0, 600)
            };
          });
          const filters = Array.from(document.querySelectorAll('[data-f]')).map((el) => ({
            key: el.getAttribute('data-f'),
            className: String(el.className || ''),
            ariaPressed: el.getAttribute('aria-pressed'),
            text: (el.innerText || '').trim(),
            style: css(el)
          }));
          const selectors = ['main', '.catalog-grid', '.catalog-list', '.catalog-results', '.catalog-result', '.catalog-content', '.catalog-wrap', '.catalog', 'footer', 'nav'];
          const containers = {};
          for (const selector of selectors) {
            const el = document.querySelector(selector);
            containers[selector] = el ? {style: css(el), className: String(el.className || ''), text: (el.innerText || '').trim().slice(0, 500)} : null;
          }
          const headings = Array.from(document.querySelectorAll('h1,h2')).map(el => ({text:(el.innerText||'').trim(), style:css(el)}));
          return {
            location: location.href,
            title: document.title,
            readyState: document.readyState,
            htmlLang: document.documentElement.lang,
            bodyText: (document.body?.innerText || '').trim().slice(0, 2500),
            bodyChildCount: document.body?.children.length || 0,
            dimensions: {
              innerWidth,
              innerHeight,
              scrollWidth: document.documentElement.scrollWidth,
              scrollHeight: document.documentElement.scrollHeight,
              bodyScrollWidth: document.body?.scrollWidth || 0,
              bodyScrollHeight: document.body?.scrollHeight || 0
            },
            cards,
            cardCount: cards.length,
            renderedCardCount: cards.filter(c => c.style.rendered).length,
            inViewportCardCount: cards.filter(c => c.style.inViewport).length,
            brokenImageCount: cards.flatMap(c => c.images).filter(img => !img.complete || img.naturalWidth === 0).length,
            filters,
            containers,
            headings,
            activeElement: document.activeElement ? document.activeElement.outerHTML.slice(0,500) : ''
          };
        }
        """
    )
    screenshot = EVIDENCE / f"{label}.png"
    html_path = EVIDENCE / f"{label}.html"
    try:
        page.screenshot(path=str(screenshot), full_page=True)
        html_path.write_text(page.content(), encoding="utf-8")
    except Exception as exc:
        data["capture_error"] = f"{type(exc).__name__}:{exc}"
    data.update(
        {
            "label": label,
            "requested_url": url,
            "http_status": response.status if response else None,
            "navigation_error": navigation_error,
            "console_errors": console_errors[:100],
            "page_errors": page_errors[:100],
            "request_failures": request_failures[:200],
            "captured_at_utc": utc_now(),
        }
    )
    page.close()
    return data


def main() -> int:
    result: dict[str, Any] = {
        "contract_id": "CATALOG-VISUAL-ACCEPTANCE-REPAIR-095-V1.0",
        "status": "FAIL",
        "production_write": False,
        "crm_write": False,
        "media_write": False,
        "started_at_utc": utc_now(),
        "probes": [],
        "errors": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        cases = [
            ("root-mobile", "/", {"width": 390, "height": 844}),
            ("catalog-mobile", "/video/katalog.html", {"width": 390, "height": 844}),
            ("root-desktop", "/", {"width": 1440, "height": 1000}),
            ("catalog-desktop", "/video/katalog.html", {"width": 1440, "height": 1000}),
        ]
        for label, path, viewport in cases:
            try:
                result["probes"].append(probe_page(browser, label=label, path=path, viewport=viewport))
            except Exception as exc:
                result["errors"].append(f"{label}:{type(exc).__name__}:{exc}")
        browser.close()

    catalog_probes = [p for p in result["probes"] if p.get("label", "").startswith("catalog-")]
    for probe in catalog_probes:
        if probe.get("http_status") != 200:
            result["errors"].append(f"{probe.get('label')}:HTTP_{probe.get('http_status')}")
        if probe.get("cardCount") != 13:
            result["errors"].append(f"{probe.get('label')}:DOM_CARDS_{probe.get('cardCount')}")
        if probe.get("renderedCardCount") != 13:
            result["errors"].append(f"{probe.get('label')}:RENDERED_CARDS_{probe.get('renderedCardCount')}")
        if probe.get("brokenImageCount"):
            result["errors"].append(f"{probe.get('label')}:BROKEN_IMAGES_{probe.get('brokenImageCount')}")
        dimensions = probe.get("dimensions") or {}
        if dimensions.get("scrollWidth", 0) > dimensions.get("innerWidth", 0) + 2:
            result["errors"].append(f"{probe.get('label')}:HORIZONTAL_OVERFLOW")
    result["status"] = "PASS" if not result["errors"] else "FAIL"
    result["finished_at_utc"] = utc_now()
    (EVIDENCE / "browser_probe.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "errors": result["errors"],
        "summary": [
            {
                "label": p.get("label"),
                "http": p.get("http_status"),
                "cards": p.get("cardCount"),
                "rendered": p.get("renderedCardCount"),
                "viewport": p.get("inViewportCardCount"),
                "broken_images": p.get("brokenImageCount"),
                "scroll": p.get("dimensions"),
            }
            for p in result["probes"]
        ],
    }, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
