#!/usr/bin/env python3
"""Browser-rendered mobile/desktop immediate+delayed acceptance for TASK099."""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import tempfile
import time
from typing import Any

from playwright.async_api import async_playwright


CONTRACT = "UA-ART-16-SITE-CRM-COMPLETION-099-V1"
HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence" / "visual_evidence.json"
SHOTS = HERE / "evidence" / "screenshots"
BASE = "https://www.uaart.com.ua/video/"
IDS = tuple("UA-%04d" % number for number in range(1, 17))
VIEWPORTS = {
    "mobile-375": {"width": 375, "height": 812},
    "mobile-390": {"width": 390, "height": 844},
    "mobile-430": {"width": 430, "height": 932},
    "desktop-1440": {"width": 1440, "height": 1000},
}
TARGETS = (
    [("home", "index.html"), ("catalog", "katalog.html")]
    + [("card", uid + ".html") for uid in IDS]
    + [("diagnostics", uid + "-diag.html") for uid in IDS]
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


MEASURE = r"""
async ({kind, expectedId, settleImages}) => {
  const visible = el => {
    if (!el) return false;
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0 && r.width > 0 && r.height > 0;
  };
  for (let y = 0; y < document.documentElement.scrollHeight; y += Math.max(320, innerHeight * .7)) {
    scrollTo(0, y); await new Promise(r => setTimeout(r, 45));
  }
  scrollTo(0, 0); await new Promise(r => setTimeout(r, 500));
  document.querySelectorAll('details.ua-additional-spec').forEach(el => { el.open = true; });
  const images = [...document.images];
  const contentImages = images.filter(img => {
    const candidates = ['src','srcset','data-src','data-srcset','data-lazy-src','data-original']
      .map(name => (img.getAttribute(name) || '').trim());
    const pictureSource = img.parentElement?.tagName === 'PICTURE' &&
      [...img.parentElement.querySelectorAll('source')].some(source =>
        Boolean((source.getAttribute('srcset') || source.getAttribute('data-srcset') || '').trim()));
    return candidates.some(Boolean) || Boolean(pictureSource) || visible(img);
  });
  const horizontalGalleries = [...document.querySelectorAll('.lenta,.mini_r,.catalog-grid,.gal')]
    .filter(el => el.scrollWidth > el.clientWidth + 1);
  let galleriesExercised = 0;
  if (settleImages) {
    contentImages.forEach(img => { img.loading = 'eager'; });
    for (const gallery of horizontalGalleries) {
      const previous = gallery.scrollLeft;
      gallery.scrollLeft = gallery.scrollWidth;
      await new Promise(r => setTimeout(r, 90));
      gallery.scrollLeft = previous;
      galleriesExercised += 1;
    }
    const waits = contentImages.map(img => img.complete ? Promise.resolve() : new Promise(resolve => {
      let done = false;
      const finish = () => { if (!done) { done = true; resolve(); } };
      img.addEventListener('load', finish, {once:true});
      img.addEventListener('error', finish, {once:true});
      setTimeout(finish, 15000);
    }));
    await Promise.all(waits);
  }
  const pending = contentImages.filter(img => !img.complete).map(img => img.currentSrc || img.src);
  const broken = contentImages.filter(img => img.complete && img.naturalWidth < 1).map(img => img.currentSrc || img.src);
  if (settleImages) broken.push(...pending);
  const hrefIds = [...document.querySelectorAll('a[href]')].map(a => {
    const m = (a.getAttribute('href') || '').match(/(?:^|\/)(UA-[0-9]{4})\.html(?:[?#].*)?$/i);
    return m ? m[1].toUpperCase() : null;
  }).filter(Boolean);
  const uniqueIds = [...new Set(hrefIds)].sort();
  const visibleIds = uniqueIds.filter(id => [...document.querySelectorAll('a[href]')].some(a =>
    new RegExp('(?:^|/)' + id + '\\.html(?:[?#].*)?$', 'i').test(a.getAttribute('href') || '') && visible(a)));
  const stageNode = document.querySelector('[data-ua-stage]');
  const stage = stageNode ? Number(stageNode.getAttribute('data-ua-stage')) : null;
  const action = document.querySelector('.dejstvie.kn_kupit,[data-ua-primary-action]');
  const videoMeta = document.querySelector('[data-ua-video-count]');
  const descriptionLabels = [...document.querySelectorAll('.zag,.tehstr>div:last-child,h2,h3')]
    .filter(el => (el.textContent || '').trim() === 'Описание').length;
  const bodyText = (document.body?.innerText || '').replace(/\s+/g, ' ').trim();
  const homeStageCounts = {}, homeStageVisible = {};
  document.querySelectorAll('.stage-card[data-stage]').forEach(card => {
    const key = (card.getAttribute('data-stage') || '').toLowerCase();
    const count = Number(card.getAttribute('data-count'));
    if (['kiev','georgia','sea','korea'].includes(key) && Number.isFinite(count)) {
      homeStageCounts[key] = count;
      homeStageVisible[key] = visible(card);
    }
  });
  const homeTotalNode = document.querySelector('.outline-cta i[data-ru*="Открыть все автомобили"]');
  const homeTotalMatch = (homeTotalNode?.getAttribute('data-ru') || homeTotalNode?.textContent || '').match(/(\d+)\s*$/);
  return {
    kind, expectedId, title: document.title, bodyBytes: new TextEncoder().encode(bodyText).length,
    viewportWidth: innerWidth, documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body ? document.body.scrollWidth : 0,
    horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1 || (document.body && document.body.scrollWidth > innerWidth + 1),
    imageCount: contentImages.length, ignoredEmptyImagePlaceholders: images.length - contentImages.length,
    brokenImages: [...new Set(broken)], pendingImages: pending,
    horizontalGalleryCount: horizontalGalleries.length, galleriesExercised,
    uniqueIds, visibleIds,
    homeStageCounts, homeStageVisible,
    homeTotal: homeTotalMatch ? Number(homeTotalMatch[1]) : null,
    expectedIdentity: expectedId ? bodyText.includes(expectedId) : true,
    h1Visible: visible(document.querySelector('h1')),
    specCount: document.querySelectorAll('[data-ua-additional-spec="1"]').length,
    specVisible: visible(document.querySelector('[data-ua-additional-spec="1"]')),
    specRows: document.querySelectorAll('.ua-addspec-row').length,
    specEmpty: document.querySelectorAll('.ua-addspec-empty').length,
    operatorInstructionLeak: /Чтобы\s+изменить\s*[—–-]\s*пришлите\s+новый\s+текст|Пришлите\s+новое\s+значение\s+текстом\s+или\s+голосом/i.test(bodyText),
    cleanVinCount: document.querySelectorAll('[data-ua-clean-vin="1"]').length,
    diagnosticLinks: [...document.querySelectorAll('a[href]')].filter(a => expectedId &&
      new RegExp('(?:^|/)' + expectedId + '-diag\\.html(?:[?#].*)?$', 'i').test(a.getAttribute('href') || '')).length,
    diagnosticVisible: [...document.querySelectorAll('a[href]')].some(a => expectedId &&
      new RegExp('(?:^|/)' + expectedId + '-diag\\.html(?:[?#].*)?$', 'i').test(a.getAttribute('href') || '') && visible(a)),
    externalVinCta: [...document.querySelectorAll('a[href]')].filter(a => /carhistory\.kr/i.test(a.href) || /Проверить VIN/i.test(a.textContent || '')).length,
    oldSeaWording: /(^|\s)В море(?=\s|[·,.]|$)/i.test(bodyText),
    descriptionLabels,
    stage,
    actionText: action ? (action.textContent || '').replace(/\s+/g, ' ').trim() : '',
    actionVisible: visible(action),
    videoMeta: videoMeta ? Number(videoMeta.getAttribute('data-ua-video-count')) : null,
    videoElements: document.querySelectorAll('video').length,
    detailsOpen: document.querySelector('details.ua-additional-spec')?.open || false
  };
}
"""


def errors_for(kind: str, metrics: dict[str, Any]) -> list[str]:
    errors = []
    if metrics.get("bodyBytes", 0) < 80:
        errors.append("BODY_EMPTY")
    if metrics.get("horizontalOverflow"):
        errors.append("HORIZONTAL_OVERFLOW")
    if metrics.get("brokenImages"):
        errors.append("BROKEN_IMAGES:%d" % len(metrics["brokenImages"]))
    if kind == "catalog":
        if metrics.get("uniqueIds") != list(IDS):
            errors.append("CATALOG_IDS_NOT_16")
        if metrics.get("visibleIds") != list(IDS):
            errors.append("CATALOG_VISIBLE_IDS_NOT_16")
        if metrics.get("imageCount", 0) < 16:
            errors.append("CATALOG_IMAGES_LT_16")
    elif kind == "home":
        counts = metrics.get("homeStageCounts") or {}
        visible = metrics.get("homeStageVisible") or {}
        if set(counts) != {"kiev", "georgia", "sea", "korea"}:
            errors.append("HOME_STAGE_CARD_SET")
        elif sum(int(value) for value in counts.values()) != 16:
            errors.append("HOME_STAGE_COUNTS_NOT_16")
        if metrics.get("homeTotal") != 16:
            errors.append("HOME_TOTAL_NOT_16")
        if set(visible) != {"kiev", "georgia", "sea", "korea"} or not all(visible.values()):
            errors.append("HOME_STAGE_CARDS_NOT_VISIBLE")
        if metrics.get("imageCount", 0) < 1:
            errors.append("HOME_IMAGES_ZERO")
    elif kind == "card":
        if not metrics.get("expectedIdentity") or not metrics.get("h1Visible"):
            errors.append("CARD_IDENTITY_OR_H1")
        if metrics.get("imageCount", 0) < 1:
            errors.append("CARD_IMAGES_ZERO")
        if metrics.get("specRows", 0) > 0:
            if metrics.get("specCount") != 1 or not metrics.get("specVisible"):
                errors.append("POPULATED_ADDITIONAL_SPEC_NOT_VISIBLE_ONCE")
        elif metrics.get("specCount") != 0:
            errors.append("EMPTY_ADDITIONAL_SPEC_BLOCK_MUST_BE_HIDDEN")
        if metrics.get("specEmpty") != 0:
            errors.append("EMPTY_ADDITIONAL_SPEC_PLACEHOLDER_FORBIDDEN")
        if metrics.get("operatorInstructionLeak"):
            errors.append("OPERATOR_INSTRUCTION_LEAK")
        if metrics.get("cleanVinCount") != 1:
            errors.append("VIN_BLOCK_NOT_ONCE")
        if metrics.get("diagnosticLinks") != 1 or not metrics.get("diagnosticVisible"):
            errors.append("DIAGNOSTICS_LINK_NOT_VISIBLE_ONCE")
        if metrics.get("externalVinCta") != 0:
            errors.append("EXTERNAL_VIN_CTA_REMAINS")
        if metrics.get("oldSeaWording"):
            errors.append("OLD_SEA_WORDING")
        if metrics.get("descriptionLabels", 0) > 1:
            errors.append("DUPLICATE_DESCRIPTION_LABEL")
        stage = metrics.get("stage")
        expected_action = "Купить" if stage == 4 else "Задаток 500 $"
        if not metrics.get("actionVisible") or metrics.get("actionText") != expected_action:
            errors.append("PRIMARY_ACTION_MISMATCH:%s" % expected_action)
        if metrics.get("videoMeta") is not None and metrics.get("videoMeta") != metrics.get("videoElements"):
            errors.append("VIDEO_COUNT_MISMATCH")
    elif kind == "diagnostics":
        if not metrics.get("expectedIdentity") or not metrics.get("h1Visible"):
            errors.append("DIAGNOSTICS_IDENTITY_OR_H1")
    return errors


async def run() -> dict[str, Any]:
    SHOTS.mkdir(parents=True, exist_ok=True)
    value = {
        "contract_id": CONTRACT, "task_id": "task_099", "status": "FAIL",
        "mode": "PUBLIC_BROWSER_RENDERED_GET_ONLY", "started_at_utc": utc_now(),
        "viewports": {}, "errors": [], "production_touched": False,
        "crm_write": False, "site_write": False, "media_write": False,
        "immediate_and_delayed": True, "issue_35_closed": False,
        "github_comment_published": False,
    }
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for viewport_name, viewport in VIEWPORTS.items():
                context = await browser.new_context(viewport=viewport, device_scale_factor=1)
                records = {}
                try:
                    for kind, relative in TARGETS:
                        page = await context.new_page()
                        match = re.search(r"(UA-[0-9]{4})", relative)
                        expected = match.group(1) if match else None
                        url = BASE + relative + "?task099=%d" % int(time.time() * 1000)
                        record = {"kind": kind, "relative": relative, "url": url, "errors": []}
                        try:
                            response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                            record["http_status"] = response.status if response else None
                            await page.wait_for_timeout(800)
                            immediate = await page.evaluate(
                                MEASURE, {"kind": kind, "expectedId": expected, "settleImages": False}
                            )
                            record["immediate"] = immediate
                            record["errors"] += ["IMMEDIATE_" + item for item in errors_for(kind, immediate)]
                            delay_ms = 35000 if kind in ("home", "catalog") else 3000
                            await page.wait_for_timeout(delay_ms)
                            delayed = await page.evaluate(
                                MEASURE, {"kind": kind, "expectedId": expected, "settleImages": True}
                            )
                            record["delayed"] = delayed
                            record["delayed_seconds"] = delay_ms / 1000
                            record["errors"] += ["DELAYED_" + item for item in errors_for(kind, delayed)]
                            if kind == "diagnostics" and expected:
                                card_record = records.get(expected + ".html") or {}
                                card_stage = (card_record.get("delayed") or {}).get("stage")
                                expected_action = "Купить" if card_stage == 4 else "Задаток 500 $"
                                if delayed.get("actionText") != expected_action or not delayed.get("actionVisible"):
                                    record["errors"].append("DIAGNOSTICS_ACTION_MISMATCH:" + expected_action)
                            if kind in ("home", "catalog") and immediate.get("visibleIds") != delayed.get("visibleIds"):
                                record["errors"].append("VISIBLE_CARD_SET_CHANGED_AFTER_DELAY")
                            name = "%s__%s.png" % (viewport_name, relative.replace(".html", "").replace("/", "_"))
                            shot = SHOTS / name
                            await page.screenshot(path=str(shot), full_page=False)
                            record["screenshot"] = "screenshots/" + name
                            record["screenshot_sha256"] = hashlib.sha256(shot.read_bytes()).hexdigest()
                        except Exception as exc:
                            record["errors"].append(type(exc).__name__ + ":" + str(exc)[:500])
                        finally:
                            await page.close()
                        if record["errors"]:
                            value["errors"].append(viewport_name + ":" + relative + ":" + ";".join(record["errors"]))
                        records[relative] = record
                finally:
                    await context.close()
                value["viewports"][viewport_name] = records
        finally:
            await browser.close()
    value["status"] = "PASS" if not value["errors"] else "FAIL"
    value["finished_at_utc"] = utc_now()
    return value


def main() -> int:
    value = asyncio.run(run())
    atomic_json(EVIDENCE, value)
    print(json.dumps({"status": value["status"], "errors": value["errors"][:20]}, ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
