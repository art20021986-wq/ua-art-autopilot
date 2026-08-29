"""Exact live-source transforms for CRM-UNIFIED-CATALOG-001 v1.0.

The module is intentionally pure: it accepts source text, validates the
known production file/function SHA anchors, applies bounded edits inside the
target functions, compiles the candidates, and returns text.  It performs no
network or filesystem writes.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from typing import Dict, Tuple


class PatchError(RuntimeError):
    pass


FULL_FILE_SHA256: Dict[str, str] = {
    "konteyner.py": "2d56a970fb76c782f0d5caebd65b6a7ffd44fd3ad1278a775bf641cffd39080d",
    "cars_ui.py": "862baea2ca0794f5e0d83bc04169f6d2fdec401f86f384ef4376e373c02a776b",
    "stranica.py": "4bb4c26eee5948e1dc37b336c4c32689f51baf0fef1a2eceac86a50fe6434959",
    "master_card.py": "96bb7e99b15d6e5d8de7e825e427406945cf866b5cda300710950ab2ac803e81",
    "yadro.py": "45bc957a8f2b9cbc509e5e140badbb2117bedc6857e111607c50adb2058cdc30",
    "publikaciya.py": "7bb8b0e51b41d94ad305179c35bce20d89dee7f7704c844335a478f87499f0a4",
}

FUNCTION_SHA256 = {
    ("konteyner.py", "gde_mashina"): "d49710dbe1831353432c084439afc1ece9203eee116db9c42b0b00fcb7ca964c",
    ("konteyner.py", "_ekran"): "5e970dcedd8e29da0562dc2653c1b6173fd8d3007e0203fffc5e9f36bd196e6b",
    ("cars_ui.py", "stage_menu"): "edf960e645680f758dd3cbfd071410067f6b4be2a94ec4c4ca97793fc9d8d795",
    ("cars_ui.py", "toggle_publish"): "21c3f452813122f18247359259432bed2a23f12163ac36859bac0ffd594d8682",
    ("stranica.py", "_ua_seo068_normalize"): "30b706b49cbd0895631a8fd1dbe6908055016f0ef03fd30dd7338a7be0887566",
    ("master_card.py", "_ua_seo068_normalize"): "30b706b49cbd0895631a8fd1dbe6908055016f0ef03fd30dd7338a7be0887566",
    ("yadro.py", "_ua_seo068_normalize"): "30b706b49cbd0895631a8fd1dbe6908055016f0ef03fd30dd7338a7be0887566",
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
            raw = "".join(lines[node.lineno - 1:node.end_lineno])
            yield FunctionSpan(node.lineno, node.end_lineno, raw.rstrip("\r\n"))


def function_span(source: str, filename: str, name: str) -> FunctionSpan:
    expected = FUNCTION_SHA256[(filename, name)]
    matches = [span for span in _function_spans(source, name) if sha256_text(span.source) == expected]
    if len(matches) != 1:
        observed = [sha256_text(span.source) for span in _function_spans(source, name)]
        raise PatchError(
            "FUNCTION_SHA_MISMATCH:%s:%s:expected=%s:observed=%s"
            % (filename, name, expected, ",".join(observed) or "missing")
        )
    return matches[0]


def _replace_span(source: str, span: FunctionSpan, replacement: str) -> str:
    lines = source.splitlines(keepends=True)
    old_raw = "".join(lines[span.start_line - 1:span.end_line])
    newline = "\r\n" if old_raw.endswith("\r\n") else "\n"
    new_raw = replacement.rstrip("\r\n") + newline
    return "".join(lines[:span.start_line - 1] + [new_raw] + lines[span.end_line:])


def _replace_exact(value: str, old: str, new: str, label: str) -> str:
    count = value.count(old)
    if count != 1:
        raise PatchError("ANCHOR_COUNT:%s:%d" % (label, count))
    return value.replace(old, new, 1)


def require_full_sha(filename: str, source: str) -> None:
    actual = sha256_text(source)
    expected = FULL_FILE_SHA256[filename]
    if actual != expected:
        raise PatchError("FULL_FILE_SHA:%s:expected=%s:actual=%s" % (filename, expected, actual))


def _replace_function(source: str, filename: str, name: str, replacement: str) -> str:
    span = function_span(source, filename, name)
    return _replace_span(source, span, replacement)


def patch_konteyner(source: str, check_full_sha: bool = True) -> str:
    if check_full_sha:
        require_full_sha("konteyner.py", source)

    span = function_span(source, "konteyner.py", "gde_mashina")
    changed = _replace_exact(
        span.source,
        "if stage_no == nomer_etapa]",
        'if stage_no == nomer_etapa and code not in ("sea_loaded", "sea_transit")]' ,
        "gde_mashina_status_filter",
    )
    source = _replace_span(source, span, changed)

    span = function_span(source, "konteyner.py", "_ekran")
    old = '''        [InlineKeyboardButton("Дни до прибытия",
                              callback_data="cont_days:%d" % cid)],
    ]'''
    new = '''        [InlineKeyboardButton("Дни до прибытия",
                              callback_data="cont_days:%d" % cid)],
        [InlineKeyboardButton("Загружено в контейнер",
                              callback_data="car_setstage:%d:sea_loaded" % cid)],
        [InlineKeyboardButton("В пути",
                              callback_data="car_setstage:%d:sea_transit" % cid)],
    ]'''
    changed = _replace_exact(span.source, old, new, "ekran_inner_actions")
    source = _replace_span(source, span, changed)

    compile(source, "konteyner.py", "exec")
    body = next(_function_spans(source, "_ekran")).source
    if body.count("car_setstage:%d:sea_loaded") != 1 or body.count("car_setstage:%d:sea_transit") != 1:
        raise PatchError("INNER_ACTION_COUNT")
    if "types.InlineKeyboardButton" in body:
        raise PatchError("WRONG_BUTTON_CLASS")
    return source


TOGGLE_PUBLISH_REPLACEMENT = r'''async def toggle_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    card = card_of(cid)
    preimage_published = 1 if card.get("published") else 0
    novoe = 0 if preimage_published else 1

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
            _txt_rem2 = "Публикация отменена из-за технической ошибки: %s" % _e

        if _ok_rem2 is not True:
            _current = card_of(cid)
            _current_published = 1 if (_current and _current.get("published")) else 0
            if _current_published == novoe:
                db.update_card_field("cars", cid, "published", preimage_published,
                                     q.from_user.id)
            _readback = card_of(cid)
            _rollback_ok = bool(_readback) and (
                (1 if _readback.get("published") else 0) == preimage_published)
            if _txt_rem2:
                await q.message.reply_text(_txt_rem2)
            await q.message.reply_text(
                ("Публикация не выполнена. Статус карточки возвращён."
                 if _rollback_ok else
                 "Публикация не выполнена. Возврат статуса не подтверждён — сообщите администратору."),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "← Вернуться к карточке", callback_data="car_open:%d" % cid)]]))
            raise ApplicationHandlerStop
        if _txt_rem2:
            await q.message.reply_text(_txt_rem2)

    await q.message.reply_text(
        "Машина видна клиентам в каталоге." if novoe
        else "Машина скрыта от клиентов.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "← Вернуться к карточке", callback_data="car_open:%d" % cid)]]))
    raise ApplicationHandlerStop'''


def patch_cars_ui(source: str, check_full_sha: bool = True) -> str:
    if check_full_sha:
        require_full_sha("cars_ui.py", source)
    span = function_span(source, "cars_ui.py", "stage_menu")
    changed = _replace_exact(
        span.source,
        "if stage_no == number]",
        'if stage_no == number and code not in ("sea_loaded", "sea_transit")]' ,
        "stage_menu_status_filter",
    )
    source = _replace_span(source, span, changed)
    source = _replace_function(
        source, "cars_ui.py", "toggle_publish", TOGGLE_PUBLISH_REPLACEMENT
    )
    compile(source, "cars_ui.py", "exec")
    patched = [s for s in _function_spans(source, "toggle_publish")]
    if len(patched) != 1 or not patched[0].source.startswith(
        "async def toggle_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):"
    ):
        raise PatchError("TOGGLE_HANDLER_SIGNATURE")
    forbidden = ("_bd_procitat_", "_bd_zapisat_", "msg_or_call")
    if any(value in patched[0].source for value in forbidden):
        raise PatchError("TOGGLE_INVENTED_HELPER")
    return source


SEO_STALE_BLOCK = '''        if not any(_ua_seo068_os.path.isfile(_ua_seo068_os.path.join(root, target)) for root in ('/home/Carix/video', '/home/Carix/site')):
            raise RuntimeError('SEO068_DIAGNOSTIC_TARGET_MISSING:' + identifier)
'''


def patch_seo_module(filename: str, source: str, check_full_sha: bool = True) -> str:
    if check_full_sha:
        require_full_sha(filename, source)
    span = function_span(source, filename, "_ua_seo068_normalize")
    changed = _replace_exact(span.source + "\n", SEO_STALE_BLOCK, "", filename + "_seo_stale")
    source = _replace_span(source, span, changed.rstrip("\n"))
    compile(source, filename, "exec")
    return source


OPUBLIKOVAT_REPLACEMENT = r'''def opublikovat(kod, proba=False):
    """Единая атомарная публикация карточки, диагностики и каталога."""
    kod = (kod or "").strip().upper()
    if not re.match(r"^UA-\d{3,5}$", kod):
        return False, "Публикация отменена: непонятный номер машины."

    do = _kartochki(krome=kod)
    try:
        html, diag, m = _master(kod)
    except Exception as e:
        _zhurnal(["%s FAIL сборка мастером: %s" % (kod, e)])
        return False, "Публикация отменена: сборщик не смог собрать %s (%s). Старая страница цела." % (kod, e)
    if not html:
        _zhurnal(["%s FAIL машина не найдена в CRM" % kod])
        return False, "Публикация отменена: %s не найдена среди машин CRM." % kod
    if not isinstance(diag, str) or not diag.strip():
        _zhurnal(["%s FAIL диагностика/placeholder не собраны" % kod])
        return False, "Публикация отменена: не собрана страница диагностики %s." % kod

    prichiny = proverit(html, kod)
    if prichiny:
        _zhurnal(["%s FAIL валидация: %s" % (kod, "; ".join(prichiny))])
        return False, ("Публикация отменена, страница не прошла проверку:\n· %s\n"
                       "Прежняя страница на сайте не тронута." % "\n· ".join(prichiny))

    try:
        katalog, spisok = _ua9_sobrat_katalog()
    except Exception as e:
        _zhurnal(["%s FAIL сборка каталога: %s" % (kod, e)])
        return False, "Публикация отменена: каталог не собран (%s)." % e
    href_pattern = r"href=['\"]%s\.html(?:[?#][^'\"]*)?['\"]" % re.escape(kod)
    href_count = len(re.findall(href_pattern, katalog))
    if href_count != 1:
        _zhurnal(["%s FAIL каталог href count=%d" % (kod, href_count)])
        return False, "Публикация отменена: в каталоге ссылка %s встречается %d раз." % (kod, href_count)

    if proba:
        return True, "Проба: карточка, диагностика и каталог %s собраны и проверены; ничего не записано." % kod

    papka_rez = os.path.join(REZERV_KORE, "%s_%s" % (kod, time.strftime("%Y%m%d_%H%M%S")))
    celi = []
    for papka in (VIDEO, SITE):
        if not os.path.isdir(papka):
            continue
        celi.append(os.path.join(papka, kod + ".html"))
        for imya in os.listdir(papka):
            if re.match(r"^%s-[0-9a-f]{6,10}\.html$" % kod, imya):
                celi.append(os.path.join(papka, imya))
        celi.append(os.path.join(papka, kod + "-diag.html"))
        celi.append(os.path.join(papka, "katalog.html"))
    celi = list(dict.fromkeys(celi))

    try:
        os.makedirs(papka_rez, exist_ok=True)
        for put in celi:
            if os.path.exists(put):
                shutil.copy2(put, os.path.join(
                    papka_rez, put.replace(BASE + "/", "").replace("/", "__")))
    except Exception as e:
        _zhurnal(["%s FAIL резерв: %s" % (kod, e)])
        return False, "Публикация отменена: не удалось сделать резерв (%s)." % e

    def _material(put):
        imya = os.path.basename(put)
        if imya == "katalog.html":
            return katalog
        if imya.endswith("-diag.html"):
            return diag
        return html

    bylo = dict((put, _sha(put)) for put in celi)
    try:
        for put in celi:
            material = _material(put)
            _zapisat_atomarno(put, material)
            if _chitat(put) != material:
                raise RuntimeError("read-back mismatch: %s" % put)
        for papka in (VIDEO, SITE):
            if not os.path.isdir(papka):
                continue
            fakt_katalog = _chitat(os.path.join(papka, "katalog.html"))
            if len(re.findall(href_pattern, fakt_katalog)) != 1:
                raise RuntimeError("catalog verification: %s" % papka)
    except Exception as e:
        oshibki_otkata = _otkat(papka_rez, celi)
        _zhurnal(["%s FAIL запись: %s — откат: %s" %
                  (kod, e, "ok" if not oshibki_otkata else "; ".join(oshibki_otkata))])
        return False, "Публикация отменена при записи (%s). Выполнен откат." % e

    posle = _kartochki(krome=kod)
    izmenilis = [k for k in do if do.get(k) != posle.get(k)]
    if izmenilis:
        osh_roll = _otkat(papka_rez, celi)
        _zhurnal(["%s FAIL регрессия: изменились %s — откат %s" %
                  (kod, ", ".join(izmenilis), "ok" if not osh_roll else "; ".join(osh_roll))])
        return False, ("Публикация отменена: изменились чужие карточки (%s). Выполнен откат."
                       % ", ".join(os.path.basename(x) for x in izmenilis))

    stalo = dict((put, _sha(put)) for put in celi)
    _zhurnal(["%s PASS единая публикация · primary+diag+catalog · файлов %d" % (kod, len(celi))]
             + ["    %s  %s -> %s" % (os.path.basename(k), (bylo.get(k) or "-")[:12],
                                      (stalo.get(k) or "-")[:12]) for k in celi])
    return True, ("Страница %s, диагностика и каталог обновлены и проверены.\n"
                  "https://www.uaart.com.ua/video/%s.html?v=%d"
                  % (kod, kod, int(time.time())))'''


OTKAT_REPLACEMENT = r'''def _otkat(papka_rez, celi):
    """Восстановить существовавшие цели, а новые удалить."""
    oshibki = []
    for put in celi:
        kopiya = os.path.join(papka_rez, put.replace(BASE + "/", "").replace("/", "__"))
        try:
            if os.path.exists(kopiya):
                shutil.copy2(kopiya, put)
            elif os.path.exists(put):
                os.remove(put)
        except Exception as e:
            oshibki.append("%s: %s" % (put, e))
    return oshibki'''


def patch_publikaciya(source: str, check_full_sha: bool = True) -> str:
    if check_full_sha:
        require_full_sha("publikaciya.py", source)
    source = _replace_function(
        source, "publikaciya.py", "opublikovat", OPUBLIKOVAT_REPLACEMENT
    )
    source = _replace_function(source, "publikaciya.py", "_otkat", OTKAT_REPLACEMENT)
    compile(source, "publikaciya.py", "exec")
    opub = [s for s in _function_spans(source, "opublikovat")]
    if len(opub) != 1:
        raise PatchError("PUBLISHER_COUNT")
    for required in ("_master(kod)", "proverit(html, kod)", "_ua9_sobrat_katalog()", "katalog.html"):
        if required not in opub[0].source:
            raise PatchError("PUBLISHER_SEMANTIC:%s" % required)
    for forbidden in ("_postroit_stranicu", "render_primary_html", "ua-catalog-cards"):
        if forbidden in opub[0].source:
            raise PatchError("SYNTHETIC_PUBLISHER:%s" % forbidden)
    return source


def build_candidates(sources: Dict[str, str], check_full_sha: bool = True) -> Dict[str, str]:
    missing = sorted(set(FULL_FILE_SHA256) - set(sources))
    if missing:
        raise PatchError("MISSING_FILES:%s" % ",".join(missing))
    candidates = {
        "konteyner.py": patch_konteyner(sources["konteyner.py"], check_full_sha),
        "cars_ui.py": patch_cars_ui(sources["cars_ui.py"], check_full_sha),
        "stranica.py": patch_seo_module("stranica.py", sources["stranica.py"], check_full_sha),
        "master_card.py": patch_seo_module("master_card.py", sources["master_card.py"], check_full_sha),
        "yadro.py": patch_seo_module("yadro.py", sources["yadro.py"], check_full_sha),
        "publikaciya.py": patch_publikaciya(sources["publikaciya.py"], check_full_sha),
    }
    for name, value in candidates.items():
        compile(value, name, "exec")
        if value == sources[name]:
            raise PatchError("UNCHANGED_CANDIDATE:%s" % name)
    return candidates


def candidate_hashes(candidates: Dict[str, str]) -> Dict[str, str]:
    return {name: sha256_text(value) for name, value in candidates.items()}
