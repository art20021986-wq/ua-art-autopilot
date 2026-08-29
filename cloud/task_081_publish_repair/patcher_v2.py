"""Exact live-source transforms for UA-0013-PUBLISH-REPAIR-001 v1.0.

The patcher is pure: it accepts source text, verifies the fresh production
file and function SHA256 anchors, applies bounded AST-span replacements,
compiles every candidate, and returns candidate text.  It performs no remote
or local production writes.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from typing import Dict


class PatchError(RuntimeError):
    pass


FULL_FILE_SHA256: Dict[str, str] = {
    "cars_ui.py": "50f1cb15b6e1ec3a35878a3021beb362a87f3607ac46abf3eb44566023b14306",
    "stranica.py": "84a56024e185932c3f2af289db87d1b98558acdf9c4788256dfd36d544ec28b3",
    "master_card.py": "df2001cd808e5fbb2201e2dbc5e06ab3d529be3cdb65dbaca691a15a2bad2174",
    "yadro.py": "a0976afb93a4d2fdcab392601d25253700977618a02b04bc31903a18e95ee81a",
    "publikaciya.py": "7bb8b0e51b41d94ad305179c35bce20d89dee7f7704c844335a478f87499f0a4",
}

FUNCTION_SHA256 = {
    ("cars_ui.py", "toggle_publish"): "21c3f452813122f18247359259432bed2a23f12163ac36859bac0ffd594d8682",
    ("stranica.py", "_ua_seo068_normalize"): "30b706b49cbd0895631a8fd1dbe6908055016f0ef03fd30dd7338a7be0887566",
    ("master_card.py", "_ua_seo068_normalize"): "30b706b49cbd0895631a8fd1dbe6908055016f0ef03fd30dd7338a7be0887566",
    ("yadro.py", "_ua_seo068_normalize"): "30b706b49cbd0895631a8fd1dbe6908055016f0ef03fd30dd7338a7be0887566",
    ("stranica.py", "_ua068_ensure_diag_files"): "f052003770561cf5ab7aba0c683cfb2b9c63769d5a925d6aded8e1a2f2de5b6b",
    ("master_card.py", "_ua068_ensure_diag_files"): "f052003770561cf5ab7aba0c683cfb2b9c63769d5a925d6aded8e1a2f2de5b6b",
    ("yadro.py", "_ua068_ensure_diag_files"): "f052003770561cf5ab7aba0c683cfb2b9c63769d5a925d6aded8e1a2f2de5b6b",
    ("publikaciya.py", "opublikovat"): "93f130c2542124b820eae2416984705ecbbc80019a298d2b3c40fdf58d93033f",
    ("publikaciya.py", "_otkat"): "141cd24d4d57b4812ea1339fd6f74a0656b993b190897a4e932e2ec6792e15b1",
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FunctionSpan:
    start_line: int
    end_line: int
    source: str


def _function_spans(source: str, name: str):
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            if node.end_lineno is None:
                raise PatchError("AST_END_LINE_MISSING:%s" % name)
            raw = "".join(lines[node.lineno - 1 : node.end_lineno])
            yield FunctionSpan(node.lineno, node.end_lineno, raw.rstrip("\r\n"))


def function_span(source: str, filename: str, name: str) -> FunctionSpan:
    expected = FUNCTION_SHA256[(filename, name)]
    spans = list(_function_spans(source, name))
    matches = [span for span in spans if sha256_text(span.source) == expected]
    if len(matches) != 1:
        observed = [sha256_text(span.source) for span in spans]
        raise PatchError(
            "FUNCTION_SHA_MISMATCH:%s:%s:expected=%s:observed=%s"
            % (filename, name, expected, ",".join(observed) or "missing")
        )
    return matches[0]


def require_full_sha(filename: str, source: str) -> None:
    actual = sha256_text(source)
    expected = FULL_FILE_SHA256[filename]
    if actual != expected:
        raise PatchError(
            "FULL_FILE_SHA:%s:expected=%s:actual=%s" % (filename, expected, actual)
        )


def _replace_span(source: str, span: FunctionSpan, replacement: str) -> str:
    lines = source.splitlines(keepends=True)
    old_raw = "".join(lines[span.start_line - 1 : span.end_line])
    newline = "\r\n" if old_raw.endswith("\r\n") else "\n"
    new_raw = replacement.rstrip("\r\n") + newline
    return "".join(lines[: span.start_line - 1] + [new_raw] + lines[span.end_line :])


def _replace_function(source: str, filename: str, name: str, replacement: str) -> str:
    return _replace_span(source, function_span(source, filename, name), replacement)


def _replace_exact(value: str, old: str, new: str, label: str) -> str:
    count = value.count(old)
    if count != 1:
        raise PatchError("ANCHOR_COUNT:%s:%d" % (label, count))
    return value.replace(old, new, 1)


TOGGLE_PUBLISH_REPLACEMENT = r'''async def toggle_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    card = card_of(cid)
    if not card:
        await q.message.reply_text("Карточка не найдена.")
        raise ApplicationHandlerStop

    preimage = {
        "published": 1 if card.get("published") else 0,
        "status": card.get("status"),
        "publish_pending": card.get("publish_pending"),
    }
    novoe = 0 if preimage["published"] else 1

    if novoe:
        miss = S.missing_required(card)
        if miss:
            await q.message.reply_text(
                "Для показа клиентам не хватает: %s" % ", ".join(miss),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Дозаполнить",
                                          callback_data="car_edit:%d" % cid)],
                    [InlineKeyboardButton("← Вернуться к карточке",
                                          callback_data="car_open:%d" % cid)]]))
            raise ApplicationHandlerStop

    db.update_card_field("cars", cid, "published", novoe, q.from_user.id)
    if novoe:
        try:
            import asyncio as _aio_rem2
            import publikaciya as _pub_rem2
            _ok_rem2, _txt_rem2 = await _aio_rem2.to_thread(
                _pub_rem2.opublikovat, card.get("auto_number"))
        except Exception as _e:
            log.warning("Страница при публикации: %s", _e)
            _ok_rem2 = False
            _txt_rem2 = (
                "Публикация отменена: техническая ошибка (%s). "
                "Старая страница цела." % _e)

        if _ok_rem2 is not True:
            current = card_of(cid) or {}
            for _field, _value in preimage.items():
                if current.get(_field) != _value:
                    db.update_card_field("cars", cid, _field, _value,
                                         q.from_user.id)
                    current = card_of(cid) or current
            readback = card_of(cid) or {}
            rollback_ok = all(readback.get(_field) == _value
                              for _field, _value in preimage.items())
            message = (_txt_rem2 or
                       "Публикация отменена: сборщик не подтвердил результат. "
                       "Старая страница цела.")
            if not rollback_ok:
                message += (" Возврат статуса не подтверждён — "
                            "сообщите администратору.")
            await q.message.reply_text(
                message,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "← Вернуться к карточке", callback_data="car_open:%d" % cid)]]))
            raise ApplicationHandlerStop

    await q.message.reply_text(
        "Машина видна клиентам в каталоге." if novoe
        else "Машина скрыта от клиентов.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "← Вернуться к карточке", callback_data="car_open:%d" % cid)]]))
    raise ApplicationHandlerStop'''


SEO_STALE_BLOCK = '''        if not any(_ua_seo068_os.path.isfile(_ua_seo068_os.path.join(root, target)) for root in ('/home/Carix/video', '/home/Carix/site')):
            raise RuntimeError('SEO068_DIAGNOSTIC_TARGET_MISSING:' + identifier)
'''


ENSURE_DIAG_REPLACEMENT = r'''def _ua068_ensure_diag_files(kod, row):
    """Create missing live placeholders for background builds.

    The unified publisher sets ``_UA081_STAGE_ONLY`` while building its
    staged bundle; in that mode this function returns the canonical payload
    without touching live roots.  Default background behavior is preserved.
    """
    payload = _ua068_diag_placeholder(kod, row).encode("utf-8")
    if globals().get("_UA081_STAGE_ONLY"):
        return payload.decode("utf-8")
    for root in ("/home/Carix/video", "/home/Carix/site"):
        path = _ua068_os.path.join(root, "%s-diag.html" % kod)
        if _ua068_os.path.exists(path):
            continue
        try:
            _ua068_os.makedirs(root, exist_ok=True)
            handle = _ua068_tempfile.NamedTemporaryFile(
                prefix=".ua068-diag-", suffix=".tmp", dir=root, delete=False)
            temp_path = handle.name
            with handle:
                handle.write(payload)
                handle.flush()
                _ua068_os.fsync(handle.fileno())
            if not _ua068_os.path.exists(path):
                _ua068_os.replace(temp_path, path)
            elif _ua068_os.path.exists(temp_path):
                _ua068_os.unlink(temp_path)
        except Exception:
            try:
                if "temp_path" in locals() and _ua068_os.path.exists(temp_path):
                    _ua068_os.unlink(temp_path)
            except Exception:
                pass
    return payload.decode("utf-8")'''


OPUBLIKOVAT_REPLACEMENT = r'''def opublikovat(kod, proba=False):
    """Unified atomic publication: primary + diag + both catalogs."""
    kod = (kod or "").strip().upper()
    if not re.match(r"^UA-[0-9]{4,}$", kod):
        return False, "Публикация отменена: непонятный номер машины."

    def _stage_only_begin():
        state = []
        for name in ("stranica", "master_card", "yadro"):
            try:
                module = sys.modules.get(name)
                if module is None and name in ("stranica", "master_card"):
                    module = __import__(name)
                if module is None:
                    continue
                had = hasattr(module, "_UA081_STAGE_ONLY")
                old = getattr(module, "_UA081_STAGE_ONLY", None)
                setattr(module, "_UA081_STAGE_ONLY", True)
                state.append((module, had, old))
            except Exception:
                continue
        return state

    def _stage_only_end(state):
        for module, had, old in reversed(state):
            try:
                if had:
                    setattr(module, "_UA081_STAGE_ONLY", old)
                else:
                    delattr(module, "_UA081_STAGE_ONLY")
            except Exception:
                pass

    protected_before = _kartochki(krome=kod)
    stage_state = _stage_only_begin()
    try:
        html, diag, mashina = _master(kod)
        katalog, spisok = _ua9_sobrat_katalog()
    except Exception as e:
        _zhurnal(["%s FAIL сборка мастером: %s" % (kod, e)])
        return False, (
            "Публикация отменена: сборщик не смог собрать %s (%s). "
            "Старая страница цела." % (kod, e))
    finally:
        _stage_only_end(stage_state)

    if not html or mashina is None:
        _zhurnal(["%s FAIL машина не найдена в CRM" % kod])
        return False, "Публикация отменена: %s не найдена среди машин CRM." % kod
    if not isinstance(diag, str) or not diag.strip():
        _zhurnal(["%s FAIL диагностика/placeholder не собраны" % kod])
        return False, (
            "Публикация отменена: не собрана страница диагностики %s. "
            "Старая страница цела." % kod)

    reasons = proverit(html, kod)
    diag_href_pattern = (
        r"href=['\"](?:[^'\"]*/)?%s-diag\.html(?:[?#][^'\"]*)?['\"]"
        % re.escape(kod))
    diag_href_count = len(re.findall(diag_href_pattern, html, re.I))
    if diag_href_count != 1:
        reasons.append("ссылка диагностики встречается %d раз" % diag_href_count)
    if kod not in diag or "иагност" not in diag.lower():
        reasons.append("страница диагностики не подтверждает %s" % kod)
    if reasons:
        _zhurnal(["%s FAIL валидация: %s" % (kod, "; ".join(reasons))])
        return False, (
            "Публикация отменена, страница не прошла проверку:\n· %s\n"
            "Прежняя страница на сайте не тронута." % "\n· ".join(reasons))

    try:
        import stranica as _ua081_stranica
        numbers = [str(_ua081_stranica.nomer(row)).upper() for row in spisok]
    except Exception as e:
        return False, "Публикация отменена: номера каталога не проверены (%s)." % e
    if len(numbers) != len(set(numbers)) or kod not in numbers:
        return False, "Публикация отменена: список машин каталога некорректен."
    for number in numbers:
        href_pattern = r"href=['\"]%s\.html(?:[?#][^'\"]*)?['\"]" % re.escape(number)
        count = len(re.findall(href_pattern, katalog))
        if count != 1:
            return False, (
                "Публикация отменена: в каталоге ссылка %s встречается %d раз."
                % (number, count))

    status = str((mashina or {}).get("status") or (mashina or {}).get("stage") or "").lower()
    if status.startswith("kr_"):
        expected_stage = 1
    elif status.startswith(("sea_", "ferry_")):
        expected_stage = 2
    elif status.startswith("ge_"):
        expected_stage = 3
    elif status.startswith("ua_"):
        expected_stage = 4
    else:
        return False, "Публикация отменена: этап %s не распознан." % status
    marker = 'data-ua-card="%s"' % kod
    marker_pos = katalog.find(marker)
    marker_window = katalog[max(0, marker_pos - 500):marker_pos + 1600]
    if marker_pos < 0 or ('data-ua-stage="%d"' % expected_stage) not in marker_window:
        return False, (
            "Публикация отменена: этап %s не подтверждён в каталоге." % status)

    if proba:
        return True, (
            "Проба: карточка, диагностика и оба каталога %s собраны и проверены; "
            "ничего не записано." % kod)

    backup_dir = os.path.join(
        REZERV_KORE, "%s_%s" % (kod, time.strftime("%Y%m%d_%H%M%S")))
    targets = []
    for folder in (VIDEO, SITE):
        if not os.path.isdir(folder):
            continue
        targets.append(os.path.join(folder, kod + ".html"))
        for name in os.listdir(folder):
            if re.match(r"^%s-[0-9a-f]{6,10}\.html$" % re.escape(kod), name):
                targets.append(os.path.join(folder, name))
        targets.append(os.path.join(folder, kod + "-diag.html"))
        targets.append(os.path.join(folder, "katalog.html"))
    targets = list(dict.fromkeys(targets))
    if len([path for path in targets if path.endswith("katalog.html")]) != 2:
        return False, "Публикация отменена: не найдены оба каталога."

    try:
        os.makedirs(backup_dir, exist_ok=False)
        for path in targets:
            if os.path.exists(path):
                shutil.copy2(
                    path,
                    os.path.join(
                        backup_dir, path.replace(BASE + "/", "").replace("/", "__")),
                )
    except Exception as e:
        _zhurnal(["%s FAIL резерв: %s" % (kod, e)])
        return False, "Публикация отменена: не удалось сделать резерв (%s)." % e

    def _material(path):
        name = os.path.basename(path)
        if name == "katalog.html":
            return katalog
        if name.endswith("-diag.html"):
            return diag
        return html

    before = dict((path, _sha(path)) for path in targets)
    stage_state = _stage_only_begin()
    try:
        for path in targets:
            material = _material(path)
            _zapisat_atomarno(path, material)
            if _chitat(path) != material:
                raise RuntimeError("read-back mismatch: %s" % path)
        for folder in (VIDEO, SITE):
            actual_catalog = _chitat(os.path.join(folder, "katalog.html"))
            for number in numbers:
                href_pattern = (
                    r"href=['\"]%s\.html(?:[?#][^'\"]*)?['\"]"
                    % re.escape(number))
                if len(re.findall(href_pattern, actual_catalog)) != 1:
                    raise RuntimeError("catalog verification: %s:%s" % (folder, number))
    except Exception as e:
        rollback_errors = _otkat(backup_dir, targets)
        _zhurnal(["%s FAIL запись: %s — откат: %s" % (
            kod, e, "ok" if not rollback_errors else "; ".join(rollback_errors))])
        return False, "Публикация отменена при записи (%s). Выполнен откат." % e
    finally:
        _stage_only_end(stage_state)

    protected_after = _kartochki(krome=kod)
    changed = [path for path in protected_before
               if protected_before.get(path) != protected_after.get(path)]
    if changed:
        rollback_errors = _otkat(backup_dir, targets)
        _zhurnal(["%s FAIL регрессия: изменились %s — откат %s" % (
            kod, ", ".join(changed),
            "ok" if not rollback_errors else "; ".join(rollback_errors))])
        return False, (
            "Публикация отменена: изменились чужие карточки (%s). Выполнен откат."
            % ", ".join(os.path.basename(path) for path in changed))

    after = dict((path, _sha(path)) for path in targets)
    _zhurnal(["%s PASS единая публикация · primary+diag+2catalogs · файлов %d"
              % (kod, len(targets))]
             + ["    %s  %s -> %s" % (
                 os.path.basename(path), (before.get(path) or "-")[:12],
                 (after.get(path) or "-")[:12]) for path in targets])
    return True, (
        "Страница %s, диагностика и оба каталога обновлены и проверены.\n"
        "https://www.uaart.com.ua/video/%s.html?v=%d"
        % (kod, kod, int(time.time())))'''


OTKAT_REPLACEMENT = r'''def _otkat(papka_rez, celi):
    """Restore existing targets and delete targets absent in the preimage."""
    errors = []
    for path in celi:
        copy = os.path.join(
            papka_rez, path.replace(BASE + "/", "").replace("/", "__"))
        try:
            if os.path.exists(copy):
                shutil.copy2(copy, path)
            elif os.path.exists(path):
                os.remove(path)
        except Exception as e:
            errors.append("%s: %s" % (path, e))
    return errors'''


def patch_cars_ui(source: str, check_full_sha: bool = True) -> str:
    if check_full_sha:
        require_full_sha("cars_ui.py", source)
    source = _replace_function(
        source, "cars_ui.py", "toggle_publish", TOGGLE_PUBLISH_REPLACEMENT
    )
    compile(source, "cars_ui.py", "exec")
    toggle = list(_function_spans(source, "toggle_publish"))
    if len(toggle) != 1 or not toggle[0].source.startswith(
        "async def toggle_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):"
    ):
        raise PatchError("TOGGLE_HANDLER_SIGNATURE")
    for forbidden in ("db_get_publish_state", "check_page_reachable", "catalog_occurrences_exactly_one"):
        if forbidden in toggle[0].source:
            raise PatchError("TOGGLE_INVENTED_HELPER:" + forbidden)
    for required in ("if _ok_rem2 is not True:", "preimage", "rollback_ok"):
        if required not in toggle[0].source:
            raise PatchError("TOGGLE_SEMANTIC:" + required)
    return source


def patch_seo_module(filename: str, source: str, check_full_sha: bool = True) -> str:
    if check_full_sha:
        require_full_sha(filename, source)
    normalizer = function_span(source, filename, "_ua_seo068_normalize")
    changed = _replace_exact(
        normalizer.source + "\n", SEO_STALE_BLOCK, "", filename + "_stale_precheck"
    )
    source = _replace_span(source, normalizer, changed.rstrip("\n"))
    source = _replace_function(
        source, filename, "_ua068_ensure_diag_files", ENSURE_DIAG_REPLACEMENT
    )
    compile(source, filename, "exec")
    if "SEO068_DIAGNOSTIC_TARGET_MISSING" in next(
        _function_spans(source, "_ua_seo068_normalize")
    ).source:
        raise PatchError("SEO_STALE_PRECHECK_REMAINS:" + filename)
    return source


def patch_publikaciya(source: str, check_full_sha: bool = True) -> str:
    if check_full_sha:
        require_full_sha("publikaciya.py", source)
    source = _replace_function(
        source, "publikaciya.py", "opublikovat", OPUBLIKOVAT_REPLACEMENT
    )
    source = _replace_function(
        source, "publikaciya.py", "_otkat", OTKAT_REPLACEMENT
    )
    compile(source, "publikaciya.py", "exec")
    publisher = list(_function_spans(source, "opublikovat"))
    if len(publisher) != 1:
        raise PatchError("PUBLISHER_COUNT")
    for required in (
        "_master(kod)",
        "proverit(html, kod)",
        "_ua9_sobrat_katalog()",
        "_stage_only_begin()",
        'os.path.join(folder, "katalog.html")',
        "_otkat(backup_dir, targets)",
    ):
        if required not in publisher[0].source:
            raise PatchError("PUBLISHER_SEMANTIC:" + required)
    for forbidden in ("render_primary_html", "_postroit_stranicu", "ua-catalog-cards"):
        if forbidden in publisher[0].source:
            raise PatchError("SYNTHETIC_PUBLISHER:" + forbidden)
    return source


def build_candidates(sources: Dict[str, str], check_full_sha: bool = True) -> Dict[str, str]:
    missing = sorted(set(FULL_FILE_SHA256) - set(sources))
    if missing:
        raise PatchError("MISSING_FILES:" + ",".join(missing))
    candidates = {
        "cars_ui.py": patch_cars_ui(sources["cars_ui.py"], check_full_sha),
        "stranica.py": patch_seo_module(
            "stranica.py", sources["stranica.py"], check_full_sha
        ),
        "master_card.py": patch_seo_module(
            "master_card.py", sources["master_card.py"], check_full_sha
        ),
        "yadro.py": patch_seo_module("yadro.py", sources["yadro.py"], check_full_sha),
        "publikaciya.py": patch_publikaciya(
            sources["publikaciya.py"], check_full_sha
        ),
    }
    for name, value in candidates.items():
        compile(value, name, "exec")
        if value == sources[name]:
            raise PatchError("UNCHANGED_CANDIDATE:" + name)
    return candidates


def candidate_hashes(candidates: Dict[str, str]) -> Dict[str, str]:
    return {name: sha256_text(value) for name, value in candidates.items()}
