#!/usr/bin/env python3
"""Pure homepage stage-counter synchronizer for UA ART."""
from __future__ import annotations

import html
import re
from typing import Any, Iterable, Mapping


CONTRACT_ID = "UA-HOME-STAGE-COUNTER-SYNC-093-V1.0"
STAGES = ("kiev", "georgia", "sea", "korea")
STAGE_KEYS = {1: "korea", 2: "sea", 3: "georgia", 4: "kiev"}
SCRIPT_ID = "ua-home-stage-counter-sync-v1"
SCRIPT_START = "<!-- UA-HOME-STAGE-COUNTER-SYNC-093:START -->"
SCRIPT_END = "<!-- UA-HOME-STAGE-COUNTER-SYNC-093:END -->"

CARD_RE = re.compile(
    r'<a\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bstage-card\b[^"\']*["\'])'
    r'(?=[^>]*\bdata-stage\s*=\s*["\'](?:kiev|georgia|sea|korea)["\'])'
    r'[^>]*>.*?</a\s*>',
    re.I | re.S,
)
CTA_RE = re.compile(
    r'<i\b(?=[^>]*\bdata-ru\s*=\s*["\'][^"\']*Открыть все автомобили)'
    r'[^>]*>.*?</i\s*>',
    re.I | re.S,
)


class HomeCounterError(RuntimeError):
    pass


def stage_number(row: Mapping[str, Any]) -> int:
    status = str(row.get("status") or "").strip().casefold()
    if status.startswith(("kr_", "korea")):
        return 1
    if status.startswith(("sea_", "ferry", "more", "ocean", "sold_transit")):
        return 2
    if status == "ge_to_kyiv" or status.startswith(("ge_", "georgia")):
        return 3
    if status.startswith(("ua_", "kyiv", "kiev")) or status in {"sold", "archive"}:
        return 4
    try:
        explicit = int(row.get("stage") or 0)
    except (TypeError, ValueError):
        explicit = 0
    if explicit in STAGE_KEYS:
        return explicit
    raise HomeCounterError(
        "UNKNOWN_STAGE:%s:%s" % (row.get("auto_number") or "?", status)
    )


def counts_from_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    result = {"all": 0, "kiev": 0, "georgia": 0, "sea": 0, "korea": 0}
    seen: set[str] = set()
    for row in rows:
        try:
            published = int(row.get("published") or 0)
        except (TypeError, ValueError):
            published = 0
        if published != 1:
            continue
        identifier = str(row.get("auto_number") or "").strip().upper()
        if not re.fullmatch(r"UA-[0-9]{4,}", identifier):
            raise HomeCounterError("INVALID_PUBLISHED_IDENTIFIER:" + identifier)
        if identifier in seen:
            raise HomeCounterError("DUPLICATE_PUBLISHED_IDENTIFIER:" + identifier)
        seen.add(identifier)
        result[STAGE_KEYS[stage_number(row)]] += 1
    result["all"] = len(seen)
    if result["all"] < 1 or result["all"] != sum(result[key] for key in STAGES):
        raise HomeCounterError("COUNT_INVARIANT")
    return result


def _ru(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        word = "автомобиль"
    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        word = "автомобиля"
    else:
        word = "автомобилей"
    return "%d %s" % (count, word)


def _uk(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        word = "автомобіль"
    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        word = "автомобілі"
    else:
        word = "автомобілів"
    return "%d %s" % (count, word)


def _set_attr(tag: str, name: str, value: str) -> str:
    pattern = re.compile(
        r"\s+" + re.escape(name) + r'\s*=\s*(["\']).*?\1',
        re.I | re.S,
    )
    tag = pattern.sub("", tag)
    if not tag.endswith(">"):
        raise HomeCounterError("INVALID_TAG:" + name)
    return tag[:-1] + ' %s="%s">' % (name, html.escape(value, quote=True))


def _stage_of(block: str) -> str:
    opening = re.match(r"<a\b[^>]*>", block, re.I | re.S)
    if not opening:
        raise HomeCounterError("STAGE_OPENING_MISSING")
    match = re.search(
        r'\bdata-stage\s*=\s*["\'](kiev|georgia|sea|korea)["\']',
        opening.group(0),
        re.I,
    )
    if not match:
        raise HomeCounterError("STAGE_ATTRIBUTE_MISSING")
    return match.group(1).casefold()


def _patch_stage(block: str, stage: str, count: int) -> str:
    opening = re.match(r"<a\b[^>]*>", block, re.I | re.S)
    if not opening:
        raise HomeCounterError("STAGE_OPENING_MISSING:" + stage)
    tag = _set_attr(opening.group(0), "data-count", str(count))
    value = tag + block[opening.end():]
    em_matches = list(re.finditer(r"<em\b[^>]*>.*?</em\s*>", value, re.I | re.S))
    if len(em_matches) != 1:
        raise HomeCounterError("STAGE_COUNT_LABELS:%s:%d" % (stage, len(em_matches)))
    match = em_matches[0]
    old = match.group(0)
    em_open = re.match(r"<em\b[^>]*>", old, re.I | re.S)
    if not em_open:
        raise HomeCounterError("STAGE_EM_OPENING:" + stage)
    em_tag = _set_attr(_set_attr(em_open.group(0), "data-ru", _ru(count)), "data-uk", _uk(count))
    replacement = em_tag + html.escape(_ru(count)) + "</em>"
    return value[:match.start()] + replacement + value[match.end():]


def _patch_cta(source: str, total: int) -> str:
    matches = list(CTA_RE.finditer(source))
    if len(matches) != 1:
        raise HomeCounterError("TOTAL_CTA_COUNT:%d" % len(matches))
    match = matches[0]
    block = match.group(0)
    opening = re.match(r"<i\b[^>]*>", block, re.I | re.S)
    if not opening:
        raise HomeCounterError("TOTAL_CTA_OPENING")
    ru = "Открыть все автомобили · %d" % total
    uk = "Відкрити всі автомобілі · %d" % total
    tag = _set_attr(_set_attr(opening.group(0), "data-ru", ru), "data-uk", uk)
    replacement = tag + html.escape(ru) + "</i>"
    return source[:match.start()] + replacement + source[match.end():]


DYNAMIC_SCRIPT = r'''<!-- UA-HOME-STAGE-COUNTER-SYNC-093:START -->
<script id="ua-home-stage-counter-sync-v1">
(function () {
  "use strict";
  var aliases = {kiev:"kiev", georgia:"georgia", gruzia:"georgia",
                 sea:"sea", more:"sea", korea:"korea"};
  function ru(n) {
    var d=n%10, h=n%100, w=(d===1&&h!==11)?"автомобиль":
      ((d>=2&&d<=4&&!(h>=12&&h<=14))?"автомобиля":"автомобилей");
    return n+" "+w;
  }
  function uk(n) {
    var d=n%10, h=n%100, w=(d===1&&h!==11)?"автомобіль":
      ((d>=2&&d<=4&&!(h>=12&&h<=14))?"автомобілі":"автомобілів");
    return n+" "+w;
  }
  function ukrainian() {
    var lang=(document.documentElement.getAttribute("lang")||"").toLowerCase();
    return lang.indexOf("uk")===0 || lang.indexOf("ua")===0;
  }
  function apply(counts) {
    document.querySelectorAll(".stage-card[data-stage]").forEach(function(card){
      var key=aliases[(card.getAttribute("data-stage")||"").toLowerCase()];
      if (!key || typeof counts[key] !== "number") return;
      var n=counts[key], label=card.querySelector(".stage-copy em")||card.querySelector("em");
      card.setAttribute("data-count", String(n));
      if (label) {
        label.setAttribute("data-ru", ru(n));
        label.setAttribute("data-uk", uk(n));
        label.textContent=ukrainian()?uk(n):ru(n);
      }
    });
    var total=counts.all, cta=document.querySelector(
      '.outline-cta i[data-ru*="Открыть все автомобили"]');
    if (cta && typeof total === "number") {
      var r="Открыть все автомобили · "+total;
      var u="Відкрити всі автомобілі · "+total;
      cta.setAttribute("data-ru", r);
      cta.setAttribute("data-uk", u);
      cta.textContent=ukrainian()?u:r;
    }
  }
  async function sync() {
    try {
      var response=await fetch("katalog.html?ua_stage_counts="+Date.now(),
                               {cache:"no-store", credentials:"same-origin"});
      if (!response.ok) return;
      var doc=new DOMParser().parseFromString(await response.text(),"text/html");
      var counts={all:0,kiev:0,georgia:0,sea:0,korea:0}, seen={};
      doc.querySelectorAll("[data-ua-card]").forEach(function(card){
        var id=(card.getAttribute("data-ua-card")||"").toUpperCase();
        var raw=(card.getAttribute("data-ua-card-stage")||
                 card.getAttribute("data-etap")||
                 card.getAttribute("data-stage")||"").toLowerCase();
        var key=aliases[raw];
        if (!id || !key || seen[id]) return;
        seen[id]=true; counts[key]+=1; counts.all+=1;
      });
      if (counts.all>0 &&
          counts.all===counts.kiev+counts.georgia+counts.sea+counts.korea) {
        apply(counts);
      }
    } catch (_error) {
      /* The server-rendered CRM snapshot remains the fail-safe value. */
    }
  }
  if (document.readyState==="loading") {
    document.addEventListener("DOMContentLoaded", sync, {once:true});
  } else {
    sync();
  }
}());
</script>
<!-- UA-HOME-STAGE-COUNTER-SYNC-093:END -->'''


def _inject_script(source: str) -> str:
    region = re.compile(
        re.escape(SCRIPT_START) + r".*?" + re.escape(SCRIPT_END),
        re.S,
    )
    if region.search(source):
        return region.sub(DYNAMIC_SCRIPT, source, count=1)
    positions = list(re.finditer(r"</body\s*>", source, re.I))
    if len(positions) != 1:
        raise HomeCounterError("BODY_END_COUNT:%d" % len(positions))
    match = positions[0]
    return source[:match.start()] + DYNAMIC_SCRIPT + "\n" + source[match.start():]


def patch_home(source: str, counts: Mapping[str, int]) -> str:
    expected = {"all", *STAGES}
    if set(counts) != expected:
        raise HomeCounterError("COUNT_KEYS")
    if int(counts["all"]) != sum(int(counts[key]) for key in STAGES):
        raise HomeCounterError("COUNT_SUM")
    found: dict[str, int] = {}

    def replace(match: re.Match[str]) -> str:
        block = match.group(0)
        stage = _stage_of(block)
        found[stage] = found.get(stage, 0) + 1
        return _patch_stage(block, stage, int(counts[stage]))

    result = CARD_RE.sub(replace, source)
    if found != {stage: 1 for stage in STAGES}:
        raise HomeCounterError("STAGE_CARD_SET:" + repr(found))
    result = _patch_cta(result, int(counts["all"]))
    result = _inject_script(result)
    audit = audit_home(result, counts)
    if audit["status"] != "PASS":
        raise HomeCounterError("PATCH_AUDIT:" + ",".join(audit["errors"]))
    return result


def audit_home(source: str, counts: Mapping[str, int]) -> dict[str, Any]:
    errors: list[str] = []
    blocks = CARD_RE.findall(source)
    actual: dict[str, int] = {}
    for block in blocks:
        try:
            stage = _stage_of(block)
        except HomeCounterError as exc:
            errors.append(str(exc))
            continue
        actual[stage] = actual.get(stage, 0) + 1
        opening = re.match(r"<a\b[^>]*>", block, re.I | re.S)
        expected_count = int(counts.get(stage, -1))
        if not opening or not re.search(
            r'\bdata-count\s*=\s*["\']%d["\']' % expected_count,
            opening.group(0),
            re.I,
        ):
            errors.append("DATA_COUNT:" + stage)
        if _ru(expected_count) not in block or _uk(expected_count) not in block:
            errors.append("VISIBLE_COUNT:" + stage)
    if actual != {stage: 1 for stage in STAGES}:
        errors.append("STAGE_CARD_SET:" + repr(actual))
    total = int(counts.get("all", -1))
    if source.count("Открыть все автомобили · %d" % total) < 2:
        errors.append("TOTAL_RU")
    if source.count("Відкрити всі автомобілі · %d" % total) < 1:
        errors.append("TOTAL_UK")
    if source.count('id="' + SCRIPT_ID + '"') != 1:
        errors.append("DYNAMIC_SCRIPT")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "counts": {key: int(counts[key]) for key in ("all", *STAGES)},
        "stage_cards": actual,
        "dynamic_script": source.count('id="' + SCRIPT_ID + '"') == 1,
    }


__all__ = [
    "CONTRACT_ID",
    "HomeCounterError",
    "STAGES",
    "audit_home",
    "counts_from_rows",
    "patch_home",
    "stage_number",
]
