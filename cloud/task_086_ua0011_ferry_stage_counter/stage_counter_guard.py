#!/usr/bin/env python3
"""Single stage writer and catalog-counter guard for UA ART.

A stage change succeeds only when the CRM row, card pages, both catalogs and
their counters are rebuilt and read back. Any failure restores the exact row
and file preimages before the CRM receives an error.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import os
import pathlib
import re
import tempfile
from typing import Iterable, Mapping, Tuple


CONTRACT_ID = "UA-0011-FERRY-STAGE-COUNTER-SYNC-006-V1.0"
LOCK_PATH = pathlib.Path("/home/Carix/.ua_art_production_writer.lock")

SEA_FIELDS = ("sea_container", "sea_date_out", "sea_port_from")
ETA_FIELDS = ("days_to_kyiv", "eta_manual")
GEORGIA_FIELDS = ("ge_arrived", "ge_port", "ge_released", "ge_to_kyiv_at")
ALL_STAGE_FIELDS = SEA_FIELDS + ETA_FIELDS + GEORGIA_FIELDS
PUBLIC_STAGE = {1: "korea", 2: "more", 3: "gruzia", 4: "kiev"}


class StageCounterError(RuntimeError):
    """Fail-closed stage/counter contract violation."""


def _status(value: object) -> str:
    return str(value or "").strip().casefold()


def stage_number(value: object) -> int | None:
    """Return the sole public stage for a status; unknown values are refused."""
    status = _status(value)
    if status.startswith(("kr_", "korea")):
        return 1
    if status.startswith(("sea_", "ferry", "more", "ocean")):
        return 2
    if status == "sold_transit":
        return 2
    if status.startswith(("ge_", "georgia")):
        return 3
    if status.startswith(("ua_", "kyiv", "kiev")):
        return 4
    return None


def public_bucket(value: object) -> str:
    number = stage_number(value)
    if number is None:
        raise StageCounterError("UNKNOWN_STAGE:%s" % value)
    return PUBLIC_STAGE[number]


def validate_destination(value: object) -> str:
    status = _status(value)
    if status == "sea_transit":
        raise StageCounterError("LEGACY_SEA_TRANSIT_DESTINATION")
    if stage_number(status) is None:
        raise StageCounterError("UNKNOWN_DESTINATION_STAGE")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", status):
        raise StageCounterError("UNSAFE_DESTINATION_STATUS")
    return status


def cleanup_fields_for_transition(
    old_status: object,
    new_status: object,
    available_fields: Iterable[str],
) -> tuple[str, ...]:
    """Clear only payload incompatible with the destination stage.

    A ferry transition preserves confirmed container, sailing date and ETA;
    only later Georgia/Kyiv events are cleared.
    """
    old_stage = stage_number(old_status)
    new_stage = stage_number(validate_destination(new_status))
    if old_stage == new_stage:
        return ()
    available = set(available_fields)
    if new_stage == 1:
        wanted = ALL_STAGE_FIELDS
    elif new_stage == 2:
        wanted = GEORGIA_FIELDS
    elif new_stage == 3:
        wanted = ("ge_released", "ge_to_kyiv_at")
    else:
        wanted = ETA_FIELDS
    return tuple(field for field in wanted if field in available)


def public_projection(card: Mapping | None) -> dict:
    """Stage-aware renderer view: historical fields cannot leak publicly."""
    value = dict(card or {})
    stage = stage_number(value.get("status") or value.get("stage"))
    if stage is None:
        return value
    hidden = {
        1: ALL_STAGE_FIELDS,
        2: GEORGIA_FIELDS,
        3: SEA_FIELDS,
        4: SEA_FIELDS + ETA_FIELDS + GEORGIA_FIELDS,
    }[stage]
    for field in hidden:
        if field in value:
            value[field] = None
    return value


def _atomic_bytes(path: str, data: bytes) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def _capture(paths: Iterable[str]) -> dict[str, bytes | None]:
    return {
        path: pathlib.Path(path).read_bytes() if os.path.isfile(path) else None
        for path in paths
    }


def _restore(preimage: Mapping[str, bytes | None]) -> None:
    for path, data in preimage.items():
        if data is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            _atomic_bytes(path, data)
    for path, data in preimage.items():
        installed = pathlib.Path(path).read_bytes() if os.path.isfile(path) else None
        if installed != data:
            raise StageCounterError("FILE_ROLLBACK_MISMATCH:" + path)


_PUBLIC_STAGE_ALIASES = {
    "korea": "korea",
    "more": "more",
    "sea": "more",
    "ferry": "more",
    "gruzia": "gruzia",
    "georgia": "gruzia",
    "kiev": "kiev",
    "kyiv": "kiev",
}

_ARTICLE_STAGE_VALUE = {
    "korea": "korea",
    "more": "sea",
    "gruzia": "georgia",
    "kiev": "kiev",
}


def _rendered_stage(opening: str) -> str | None:
    canonical = re.findall(
        r"\bdata-stage\s*=\s*[\"']([^\"']+)[\"']", opening, re.I,
    )
    if canonical:
        return _PUBLIC_STAGE_ALIASES.get(canonical[-1].strip().casefold())
    for name in ("data-ua-card-stage", "data-etap"):
        found = re.findall(
            r"\b" + re.escape(name) + r"\s*=\s*[\"']([^\"']+)[\"']",
            opening, re.I,
        )
        if found:
            return _PUBLIC_STAGE_ALIASES.get(found[-1].strip().casefold())
    tile = re.findall(
        r"\bdata-(?:ua-stage|ua-stage-tile)\s*=\s*[\"']([1-4])[\"']",
        opening, re.I,
    )
    return PUBLIC_STAGE.get(int(tile[-1])) if tile else None


def card_entries(source: str) -> list[tuple[str, str | None, str]]:
    """Return one semantic entry per rendered vehicle card.

    The live catalog uses ``article.catalog-card`` containers with two links
    to the same vehicle.  Older catalogs used one stage-annotated anchor and
    the temporary UA-0011 fallback uses a standalone anchor.  Parsing the
    semantic container prevents the two normal links from being counted as
    duplicate vehicles while retaining fail-closed duplicate detection.
    """
    article_pattern = re.compile(
        r"<article\b(?=[^>]*class=[\"'][^\"']*\bcatalog-card\b)[^>]*>"
        r".*?</article\s*>", re.I | re.S,
    )
    entries: list[tuple[str, str | None, str]] = []
    spans: list[tuple[int, int]] = []
    for match in article_pattern.finditer(source):
        block = match.group(0)
        opening = re.match(r"<article\b[^>]*>", block, re.I | re.S)
        code = re.search(
            r"href=[\"'][^\"']*(UA-[0-9]{4,})\.html(?:\?[^\"']*)?[\"']",
            block, re.I,
        )
        if not code:
            raise StageCounterError("CATALOG_CARD_CODE_MISSING")
        entries.append((
            code.group(1).upper(),
            _rendered_stage(opening.group(0) if opening else ""),
            block,
        ))
        spans.append(match.span())

    # Remove article bodies before parsing legacy/fallback anchors.  Otherwise
    # each canonical card's photo and arrow links would be counted twice.
    remainder_parts = []
    cursor = 0
    for start, end in spans:
        remainder_parts.append(source[cursor:start])
        cursor = end
    remainder_parts.append(source[cursor:])
    remainder = "".join(remainder_parts)
    anchor_pattern = re.compile(
        r"<a\b(?=[^>]*href=[\"'][^\"']*(UA-[0-9]{4,})\.html(?:\?[^\"']*)?[\"'])"
        r"[^>]*>.*?</a\s*>", re.I | re.S,
    )
    for match in anchor_pattern.finditer(remainder):
        block = match.group(0)
        opening = re.match(r"<a\b[^>]*>", block, re.I | re.S)
        entries.append((
            match.group(1).upper(),
            _rendered_stage(opening.group(0) if opening else ""),
            block,
        ))
    return entries


def _set_attribute(opening: str, name: str, value: str) -> str:
    pattern = re.compile(r"\s+" + re.escape(name) + r"=[\"'][^\"']*[\"']", re.I)
    replacement = ' %s="%s"' % (name, value)
    if pattern.search(opening):
        return pattern.sub(replacement, opening, count=1)
    return opening[:-1] + replacement + ">"


def _published_stage_map(rows: Iterable[Mapping]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in rows:
        row = dict(raw or {})
        if int(row.get("published") or 0) != 1:
            continue
        code = str(row.get("auto_number") or "").strip().upper()
        if not re.fullmatch(r"UA-[0-9]{4,}", code):
            raise StageCounterError("INVALID_PUBLISHED_AUTO_NUMBER")
        if code in result:
            raise StageCounterError("DUPLICATE_PUBLISHED_AUTO_NUMBER:" + code)
        result[code] = public_bucket(row.get("status") or row.get("stage"))
    if not result:
        raise StageCounterError("NO_PUBLISHED_CARDS")
    return result


def _rewrite_chip_counts(source: str, counts: Mapping[str, int]) -> str:
    seen = {key: 0 for key in ("all", "korea", "more", "gruzia", "kiev")}
    pattern = re.compile(
        r"<(?P<tag>a|button)\b"
        r"(?=[^>]*data-f\s*=\s*[\"'](?P<bucket>all|korea|more|sea|gruzia|georgia|kiev|kyiv)[\"'])"
        r"[^>]*>(?P<body>.*?)</(?P=tag)\s*>",
        re.I | re.S,
    )

    def replace(match: re.Match) -> str:
        key = _PUBLIC_STAGE_ALIASES.get(match.group("bucket").casefold(),
                                        match.group("bucket").casefold())
        seen[key] += 1
        value = str(int(counts[key]))
        body = match.group("body")
        body, changed = re.subn(
            r"(<b\b[^>]*>)\s*\d+\s*(</b\s*>)",
            lambda item: item.group(1) + value + item.group(2),
            body, flags=re.I | re.S,
        )
        if not changed:
            body, changed = re.subn(
                r"(<span\b(?=[^>]*class=[\"'][^\"']*\bcount\b)[^>]*>)"
                r"\s*\d+\s*(</span\s*>)",
                lambda item: item.group(1) + value + item.group(2),
                body, flags=re.I | re.S,
            )
        if not changed:
            body, changed = re.subn(
                r"([·:]\s*)\d+",
                lambda item: item.group(1) + value,
                body, flags=re.I,
            )
        if not changed:
            raise StageCounterError("CHIP_VALUE_%s:0" % key)
        opening_end = match.group(0).find(">") + 1
        closing_start = match.group(0).lower().rfind("</")
        return match.group(0)[:opening_end] + body + match.group(0)[closing_start:]

    candidate = pattern.sub(replace, source)
    if not any(seen.values()):
        labels = {
            "all": r"(?:Все|Усі)",
            "kiev": r"(?:В Киеве|У Києві)",
            "gruzia": r"(?:В Грузии|У Грузії)",
            "more": r"(?:На пароме|На поромі)",
            "korea": r"(?:В Корее|У Кореї)",
        }
        for key, label in labels.items():
            candidate, changed = re.subn(
                r"(" + label + r"\s*·\s*)\d+",
                lambda item, value=str(int(counts[key])): item.group(1) + value,
                candidate, flags=re.I,
            )
            if not changed:
                raise StageCounterError("CHIP_LABEL_MISSING:" + key)
        candidate = re.sub(
            r"(Показано\s*:?\s*)\d+",
            lambda item: item.group(1) + str(int(counts["all"])),
            candidate, flags=re.I,
        )
        candidate = re.sub(
            r"\d+(\s+(?:в подборке|у добірці))",
            lambda item: str(int(counts["all"])) + item.group(1),
            candidate, flags=re.I,
        )
        return candidate
    invalid = [key for key, value in seen.items() if value != 1]
    if invalid:
        raise StageCounterError("CHIP_REWRITE_COUNT:" + ",".join(invalid))
    return candidate


def normalize_catalog_from_rows(source: str, rows: Iterable[Mapping]) -> str:
    """Bind every rendered card and chip to one fresh published CRM snapshot."""
    stages = _published_stage_map(rows)
    article_pattern = re.compile(
        r"<article\b(?=[^>]*class=[\"'][^\"']*\bcatalog-card\b)[^>]*>"
        r".*?</article\s*>", re.I | re.S,
    )

    def rewrite_article(match: re.Match) -> str:
        block = match.group(0)
        code_match = re.search(
            r"href=[\"'][^\"']*(UA-[0-9]{4,})\.html(?:\?[^\"']*)?[\"']",
            block, re.I,
        )
        if not code_match:
            raise StageCounterError("CATALOG_CARD_CODE_MISSING")
        code = code_match.group(1).upper()
        if code not in stages:
            raise StageCounterError("CATALOG_CARD_NOT_PUBLISHED:" + code)
        opening = re.match(r"<article\b[^>]*>", block, re.I | re.S)
        if not opening:
            raise StageCounterError("CATALOG_CARD_OPENING_MISSING:" + code)
        updated = re.sub(
            r"\s+(?:data-ua-card-stage|data-ua-stage-tile|data-ua-stage|data-stage|data-etap)"
            r"=[\"'][^\"']*[\"']",
            "", opening.group(0), flags=re.I,
        )
        updated = _set_attribute(
            updated, "data-stage", _ARTICLE_STAGE_VALUE[stages[code]]
        )
        stage_no = {value: number for number, value in PUBLIC_STAGE.items()}[stages[code]]
        updated = _set_attribute(updated, "data-ua-stage", str(stage_no))
        return updated + block[opening.end():]

    candidate = article_pattern.sub(rewrite_article, source)
    anchor_pattern = re.compile(
        r"<a\b(?=[^>]*href=[\"'][^\"']*(UA-[0-9]{4,})\.html(?:\?[^\"']*)?[\"'])"
        r"[^>]*>.*?</a\s*>", re.I | re.S,
    )

    def rewrite_anchor(match: re.Match) -> str:
        block = match.group(0)
        code = match.group(1).upper()
        if code not in stages:
            return block
        opening = re.match(r"<a\b[^>]*>", block, re.I | re.S)
        if not opening:
            raise StageCounterError("CATALOG_ANCHOR_OPENING_MISSING:" + code)
        updated = re.sub(
            r"\s+(?:data-ua-card-stage|data-ua-stage-tile|data-ua-stage|data-stage|data-etap)"
            r"\s*=\s*[\"'][^\"']*[\"']",
            "", opening.group(0), flags=re.I,
        )
        updated = _set_attribute(
            updated, "data-stage", _ARTICLE_STAGE_VALUE[stages[code]]
        )
        stage_no = {value: number for number, value in PUBLIC_STAGE.items()}[stages[code]]
        updated = _set_attribute(updated, "data-ua-stage", str(stage_no))
        return updated + block[opening.end():]

    candidate = anchor_pattern.sub(rewrite_anchor, candidate)
    entries = card_entries(candidate)
    rendered = [code for code, _stage, _block in entries]
    if len(rendered) != len(set(rendered)):
        raise StageCounterError("CATALOG_DUPLICATE_AUTO_NUMBER")
    if set(rendered) != set(stages):
        missing = sorted(set(stages) - set(rendered))
        extra = sorted(set(rendered) - set(stages))
        raise StageCounterError(
            "CATALOG_DB_SET_MISMATCH:missing=%s:extra=%s"
            % (",".join(missing), ",".join(extra))
        )
    for code, stage, _block in entries:
        if stage != stages[code]:
            raise StageCounterError("CATALOG_STAGE_MISMATCH:" + code)
    counts = catalog_counts(candidate)
    return _rewrite_chip_counts(candidate, counts)


def _card_blocks(source: str) -> list[tuple[str, str]]:
    return [(code, block) for code, _stage, block in card_entries(source)]


def catalog_counts(source: str) -> dict[str, int]:
    """Recompute from unique rendered cards; never increment/decrement chips."""
    entries = card_entries(source)
    ids = [code for code, _stage, _block in entries]
    if len(ids) != len(set(ids)):
        raise StageCounterError("CATALOG_DUPLICATE_AUTO_NUMBER")
    counts = {"all": len(ids), "korea": 0, "more": 0, "gruzia": 0, "kiev": 0}
    for code, stage, _block in entries:
        if not stage:
            raise StageCounterError("CARD_PUBLIC_STAGE_MISSING:" + code)
        counts[stage] += 1
    if counts["all"] != sum(counts[key] for key in ("korea", "more", "gruzia", "kiev")):
        raise StageCounterError("CATALOG_COUNT_INVARIANT")
    return counts


def chip_counts(source: str) -> dict[str, int]:
    values: dict[str, list[int]] = {
        key: [] for key in ("all", "korea", "more", "gruzia", "kiev")
    }
    pattern = re.compile(
        r"<(?P<tag>a|button)\b"
        r"(?=[^>]*data-f\s*=\s*[\"'](?P<bucket>all|korea|more|sea|gruzia|georgia|kiev|kyiv)[\"'])"
        r"[^>]*>(?P<body>.*?)</(?P=tag)\s*>",
        re.I | re.S,
    )
    for match in pattern.finditer(source):
        key = _PUBLIC_STAGE_ALIASES.get(match.group("bucket").casefold(),
                                        match.group("bucket").casefold())
        body = match.group("body")
        found = re.findall(r"<b\b[^>]*>\s*(\d+)\s*</b\s*>",
                           body, re.I | re.S)
        if not found:
            found = re.findall(
                r"<span\b(?=[^>]*class=[\"'][^\"']*\bcount\b)[^>]*>"
                r"\s*(\d+)\s*</span\s*>",
                body, re.I | re.S,
            )
        if not found:
            found = re.findall(r"[·:]\s*(\d+)", body, re.I)
        numbers = [int(value) for value in found]
        if not numbers or len(set(numbers)) != 1:
            raise StageCounterError("CHIP_VALUE_%s:%d" % (key, len(numbers)))
        values[key].append(numbers[0])
    if not any(values.values()):
        labels = {
            "all": r"(?:Все|Усі)",
            "kiev": r"(?:В Киеве|У Києві)",
            "gruzia": r"(?:В Грузии|У Грузії)",
            "more": r"(?:На пароме|На поромі)",
            "korea": r"(?:В Корее|У Кореї)",
        }
        result = {}
        for key, label in labels.items():
            found = [
                int(value) for value in re.findall(
                    label + r"\s*·\s*(\d+)", source, re.I,
                )
            ]
            if not found or len(set(found)) != 1:
                raise StageCounterError("CHIP_LABEL_COUNT_%s:%d" % (key, len(found)))
            result[key] = found[0]
        return result
    result = {}
    for key, found in values.items():
        if len(found) != 1:
            raise StageCounterError("CHIP_COUNT_%s:%d" % (key, len(found)))
        result[key] = found[0]
    return result


def verify_catalog(source: str, target_code: str | None = None,
                   target_bucket: str | None = None,
                   expect_target: bool = True) -> dict:
    actual = catalog_counts(source)
    if chip_counts(source) != actual:
        raise StageCounterError("CHIPS_DO_NOT_MATCH_CARDS")
    if target_code:
        target = [entry for entry in card_entries(source)
                  if entry[0] == target_code.upper()]
        wanted_count = 1 if expect_target else 0
        if len(target) != wanted_count:
            raise StageCounterError("TARGET_CATALOG_COUNT:%d" % len(target))
        if target_bucket and expect_target:
            if target[0][1] != target_bucket:
                raise StageCounterError("TARGET_BUCKET_MISMATCH")
    return actual


def diagnostic_placeholder_html(code: str) -> str:
    if not re.fullmatch(r"UA-[0-9]{4,}", str(code or "")):
        raise StageCounterError("INVALID_DIAGNOSTIC_CODE")
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Диагностика %s</title></head><body><h1>%s</h1>"
        "<p>Материалы комплексной диагностики ожидаются.</p>"
        "<a href='%s.html'>Вернуться к автомобилю</a></body></html>"
        % (code, code, code)
    )


def rebuild_catalogs_live() -> Tuple[bool, str]:
    """Build both catalogs from one fresh CRM snapshot and install atomically."""
    try:
        import publikaciya
        import stranica

        cars = list(stranica.mashiny())
        try:
            import catalog_design_guard as design
        except ImportError:
            design = None

        if (
            design is not None
            and hasattr(design, "build_from_golden_path")
            and hasattr(design, "audit_catalog")
            and hasattr(design, "extract_main_photo")
        ):
            photos = {}
            for car in cars:
                code = stranica.nomer(car)
                primary = pathlib.Path(publikaciya.VIDEO, code + ".html")
                if not primary.is_file():
                    raise StageCounterError("PRIMARY_PAGE_MISSING:" + code)
                page = primary.read_text(encoding="utf-8", errors="replace")
                photos[code] = design.extract_main_photo(page, code)
            html = design.build_from_golden_path(cars, photos)
            golden_path = pathlib.Path(getattr(
                design, "GOLDEN_PATH", pathlib.Path("/home/Carix/catalog_design_golden.html")
            ))
            if not golden_path.is_file():
                raise StageCounterError("CATALOG_GOLDEN_MISSING")
            audit = design.audit_catalog(
                html, cars, golden_path.read_text(encoding="utf-8")
            )
            if audit.get("status") != "PASS":
                raise StageCounterError(
                    "CATALOG_DESIGN_AUDIT:" + ",".join(audit.get("errors") or [])
                )
            stages = _published_stage_map(cars)
            entries = card_entries(html)
            rendered = {code: stage for code, stage, _block in entries}
            if len(entries) != len(rendered) or set(rendered) != set(stages):
                raise StageCounterError("CATALOG_DESIGN_DB_SET_MISMATCH")
            for code, stage in rendered.items():
                if stage != stages[code]:
                    raise StageCounterError("CATALOG_DESIGN_STAGE_MISMATCH:" + code)
            detail = "catalog design guard"
        else:
            frames, light = {}, {}
            for car in cars:
                code = stranica.nomer(car)
                card_frames = stranica.kadry_mashiny(car)
                frames[code] = card_frames
                light[code] = stranica.legkie(card_frames) if card_frames else ([], [])
            html = stranica.sobrat_katalog(cars, frames, light)
            if not isinstance(html, str) or "UA-" not in html:
                raise StageCounterError("CATALOG_BUILDER_INVALID_HTML")
            if not re.search(r"data-f\\s*=\\s*[\\\"']all[\\\"']", html, re.I):
                approved = pathlib.Path(publikaciya.VIDEO, "katalog.html")
                if not approved.is_file():
                    raise StageCounterError("APPROVED_CATALOG_TEMPLATE_MISSING")
                html = approved.read_text(encoding="utf-8")
            html = normalize_catalog_from_rows(html, cars)
            verify_catalog(html)
            detail = "approved catalog shell guard"

        if not isinstance(html, str) or "UA-" not in html:
            raise StageCounterError("CATALOG_BUILDER_INVALID_HTML")
        payload = html.encode("utf-8")
        targets = [
            os.path.join(publikaciya.VIDEO, "katalog.html"),
            os.path.join(publikaciya.SITE, "katalog.html"),
        ]
        preimage = _capture(targets)
        try:
            for target in targets:
                _atomic_bytes(target, payload)
            for target in targets:
                if pathlib.Path(target).read_bytes() != payload:
                    raise StageCounterError("CATALOG_READBACK_MISMATCH")
            return True, "both catalogs rebuilt from one CRM snapshot via " + detail
        except Exception:
            _restore(preimage)
            raise
    except Exception as exc:
        return False, "%s:%s" % (type(exc).__name__, exc)


def _row(connection, card_id: int) -> dict:
    cursor = connection.execute("SELECT * FROM cars WHERE id=?", (int(card_id),))
    raw = cursor.fetchone()
    if raw is None:
        raise StageCounterError("CARD_NOT_FOUND")
    return dict(zip([item[0] for item in cursor.description], tuple(raw)))


def _managed_public_paths(code: str) -> list[str]:
    import publikaciya
    result = []
    for base in (publikaciya.VIDEO, publikaciya.SITE):
        result.extend([
            os.path.join(base, code + ".html"),
            os.path.join(base, code + "-diag.html"),
            os.path.join(base, "katalog.html"),
        ])
    return result


def _audit_max(connection) -> int | None:
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    if "audit" not in tables:
        return None
    return int(connection.execute("SELECT COALESCE(MAX(id),0) FROM audit").fetchone()[0])


def _rollback_row(connection, preimage: Mapping, changed_fields: Iterable[str],
                  actor_id=None, audit_max: int | None = None) -> None:
    fields = sorted(set(changed_fields))
    if not fields:
        return
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            "UPDATE cars SET %s WHERE id=?" % ", ".join('"%s"=?' % field for field in fields),
            [preimage.get(field) for field in fields] + [int(preimage["id"])],
        )
        if audit_max is not None:
            connection.execute(
                "DELETE FROM audit WHERE id>? AND CAST(actor_id AS TEXT)=? "
                "AND entity_type='cars' AND entity_id=?",
                (int(audit_max), str(actor_id), int(preimage["id"])),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    restored = _row(connection, int(preimage["id"]))
    if any(restored.get(field) != preimage.get(field) for field in fields):
        raise StageCounterError("DB_ROLLBACK_MISMATCH")


def apply_stage_transition_live(card_id: int, destination: object, actor_id) -> Tuple[bool, str]:
    """The only CRM stage writer. It publishes or restores the full preimage."""
    try:
        card_id = int(card_id)
        if card_id <= 0:
            raise StageCounterError("INVALID_CARD_ID")
        destination = validate_destination(destination)
    except Exception as exc:
        return False, "Этап не изменён: %s" % exc

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        import db
        import publikaciya

        connection = db.connect()
        preimage = None
        file_preimage = None
        changed: dict[str, tuple[object, object]] = {}
        audit_before = None
        try:
            preimage = _row(connection, card_id)
            audit_before = _audit_max(connection)
            code = str(preimage.get("auto_number") or "").upper()
            if not re.fullmatch(r"UA-[0-9]{4,}", code):
                raise StageCounterError("INVALID_AUTO_NUMBER")
            fields = set(preimage)
            desired = {"status": destination}
            desired.update({
                field: None for field in cleanup_fields_for_transition(
                    preimage.get("status"), destination, fields
                )
            })
            if destination == "ge_waiting" and "ge_arrived" in fields and not preimage.get("ge_arrived"):
                desired["ge_arrived"] = dt.date.today().isoformat()
            if destination == "ge_to_kyiv" and "ge_released" in fields and not preimage.get("ge_released"):
                desired["ge_released"] = dt.date.today().isoformat()
            if "updated_at" in fields:
                desired["updated_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
            changed = {
                field: (preimage.get(field), value)
                for field, value in desired.items() if preimage.get(field) != value
            }
            file_preimage = _capture(_managed_public_paths(code))
            if changed:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        "UPDATE cars SET %s WHERE id=?" % ", ".join(
                            '"%s"=?' % field for field in changed
                        ),
                        [after for _field, (_before, after) in changed.items()] + [card_id],
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
            if _row(connection, card_id).get("status") != destination:
                raise StageCounterError("STATUS_READBACK_MISMATCH")
            result = publikaciya.opublikovat(code)
            ok = result[0] is True if isinstance(result, tuple) else result is True
            detail = str(result[1]) if isinstance(result, tuple) and len(result) > 1 else str(result)
            if not ok:
                raise StageCounterError("PUBLISHER_FAILED:" + detail[:500])
            expected_bucket = public_bucket(destination)
            expect_published = bool(int(preimage.get("published") or 0))
            for path in _managed_public_paths(code):
                if not os.path.isfile(path) or os.path.getsize(path) == 0:
                    raise StageCounterError("PUBLIC_FILE_MISSING:" + path)
            for base in (publikaciya.VIDEO, publikaciya.SITE):
                verify_catalog(
                    pathlib.Path(base, "katalog.html").read_text(encoding="utf-8"),
                    code, expected_bucket, expect_target=expect_published,
                )
            for field, (before, after) in changed.items():
                if field != "updated_at":
                    db.log_action(actor_id, "card_edit", "cars", card_id, field, before, after)
            return True, "Этап сохранён и каталоги пересчитаны: %s" % destination
        except Exception as exc:
            rollback_error = None
            try:
                if preimage is not None:
                    _rollback_row(
                        connection, preimage, changed,
                        actor_id=actor_id, audit_max=audit_before,
                    )
                if file_preimage is not None:
                    _restore(file_preimage)
            except Exception as rollback_exc:
                rollback_error = "%s:%s" % (type(rollback_exc).__name__, rollback_exc)
            if rollback_error:
                return False, "Этап не изменён; откат требует проверки: %s" % rollback_error
            return False, "Этап не изменён, прежние данные восстановлены: %s:%s" % (
                type(exc).__name__, exc,
            )
        finally:
            connection.close()
