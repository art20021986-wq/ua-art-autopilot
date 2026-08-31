#!/usr/bin/env python3
"""Deterministic, idempotent source patches for TASK099 production modules."""
from __future__ import annotations

import ast
import re


MASTER_START = "# >>> UA099 ADDITIONAL SPEC MASTER V1"
MASTER_END = "# <<< UA099 ADDITIONAL SPEC MASTER V1"
CRM_START = "# >>> UA099 ADDITIONAL SPEC CRM V1"
CRM_END = "# <<< UA099 ADDITIONAL SPEC CRM V1"
PUBLISH_START = "# >>> UA099 PUBLICATION CONTRACT V1"
PUBLISH_END = "# <<< UA099 PUBLICATION CONTRACT V1"
GUARD_START = "# >>> UA099 BOUNDED GZIP SNAPSHOT V1"
GUARD_END = "# <<< UA099 BOUNDED GZIP SNAPSHOT V1"


def _without(source: str, start: str, end: str) -> str:
    pattern = re.compile(r"(?:\n|^)" + re.escape(start) + r"[\s\S]*?" + re.escape(end) + r"\s*", re.M)
    return pattern.sub("\n", source).rstrip() + "\n"


def _compiled(source: str, name: str) -> str:
    compile(source, name, "exec")
    ast.parse(source)
    return source


MASTER_BLOCK = r'''
# >>> UA099 ADDITIONAL SPEC MASTER V1
_UA099_BASE_OBRABOTAT_KARTOCHKU = obrabotat_kartochku
_UA099_BASE_OBRABOTAT_DIAGNOSTIKU = obrabotat_diagnostiku
_UA099_BASE_PROVERIT = proverit

_UA099_OBSOLETE_VIN_ERRORS = {
    "VIN Guard blocks != 1",
    "VIN buttons != 1",
    "CarHistory target != 1",
    "VIN copy helper missing",
    "video count mismatch",
    "SEO068 CTA",
}

def obrabotat_kartochku(html, kod):
    html = _UA099_BASE_OBRABOTAT_KARTOCHKU(html, kod)
    if not html:
        return html
    import ua_additional_spec as _ua099_spec
    return _ua099_spec.inject_public_spec(html, kod)

def obrabotat_diagnostiku(html, kod):
    html = _UA099_BASE_OBRABOTAT_DIAGNOSTIKU(html, kod)
    if not html:
        return html
    import ua_additional_spec as _ua099_spec
    return _ua099_spec.normalize_diagnostics(html, kod)

def proverit(html, kod=""):
    # Keep every legacy safety check except the five checks whose subject was
    # deliberately replaced by TASK099's local, non-paid VIN block.  Then run
    # the new public contract, which is stricter about uniqueness and order.
    errors = [item for item in list(_UA099_BASE_PROVERIT(html, kod) or [])
              if item not in _UA099_OBSOLETE_VIN_ERRORS]
    if kod:
        import ua_additional_spec as _ua099_spec
        errors.extend("TASK099: " + item
                      for item in _ua099_spec.public_contract_errors(html or "", kod))
    return list(dict.fromkeys(errors))
# <<< UA099 ADDITIONAL SPEC MASTER V1
'''.strip()


CRM_BLOCK = r'''
# >>> UA099 ADDITIONAL SPEC CRM V1
import html as _ua099_html
import ua_additional_spec as _ua099_spec

_UA099_BASE_RENDER = render
_UA099_BASE_CARD_KB = card_kb
_UA099_BASE_REGISTER = register

def _ua099_uid(card):
    return _ua099_spec.canonical_uid((card or {}).get("auto_number"))

def render(card, staff):
    text = _UA099_BASE_RENDER(card, staff)
    uid = _ua099_uid(card)
    return text + "\n\n<b>ДОПОЛНИТЕЛЬНАЯ СПЕЦИФИКАЦИЯ</b>\n" + _ua099_html.escape(
        _ua099_spec.crm_summary(uid)
    )

def card_kb(card, staff):
    markup = _UA099_BASE_CARD_KB(card, staff)
    rows = []
    for row in markup.inline_keyboard:
        clean = [button for button in row if "carhistory.kr" not in str(getattr(button, "url", "") or "").lower()]
        if clean:
            rows.append(clean)
    cid = int(card["id"])
    spec_row = [InlineKeyboardButton(
        "📐 Дополнительная спецификация", callback_data="car_spec:%d" % cid
    )]
    if not any(any(str(getattr(button, "callback_data", "") or "").startswith("car_spec:") for button in row) for row in rows):
        position = next((index + 1 for index, row in enumerate(rows)
                         if any(str(getattr(button, "callback_data", "") or "").startswith("car_cond:")
                                for button in row)), min(3, len(rows)))
        rows.insert(position, spec_row)
    return InlineKeyboardMarkup(rows)

async def _ua099_require_staff(update):
    q = update.callback_query
    await _v168_ack(q,)
    staff = db.get_staff(q.from_user.id)
    if not staff:
        await q.message.reply_text("Доступ к CRM не разрешён.")
        raise ApplicationHandlerStop
    return q, staff

def _ua099_card(cid):
    card = card_of(int(cid))
    if not card or not _ua099_uid(card):
        raise ValueError("Карточка не найдена")
    return card

def _ua099_back(cid):
    return InlineKeyboardMarkup([[InlineKeyboardButton(
        "← Вернуться к карточке", callback_data="car_open:%d" % int(cid)
    )]])

async def additional_spec_screen(update, context):
    q, staff = await _ua099_require_staff(update)
    cid = int(q.data.split(":")[-1])
    card = _ua099_card(cid)
    uid = _ua099_uid(card)
    rows = _ua099_spec.fetch_specs(uid, include_hidden=True)
    lines = ["<b>%s · Дополнительная спецификация</b>" % _ua099_html.escape(uid),
             _ua099_html.escape(_ua099_spec.crm_summary(uid)), ""]
    keyboard = []
    for item in rows:
        visible = "👁" if int(item.get("is_visible") or 0) else "🚫"
        manual = "✍️" if int(item.get("is_manual") or 0) else "✓"
        lines.append("%s %s <b>%s</b>: %s" % (
            visible, manual, _ua099_html.escape(str(item["label_ru"])),
            _ua099_html.escape(str(item["field_value"]))))
        label = str(item["label_ru"])[:36]
        keyboard.append([InlineKeyboardButton(
            "%s %s" % (visible, label),
            callback_data="car_spec_item:%d:%d" % (cid, int(item["id"])))])
    if not rows:
        lines.append("Подтверждённые дополнительные характеристики пока не найдены.")
    if card.get("published"):
        keyboard.append([InlineKeyboardButton(
            "Обновить опубликованную страницу", callback_data="car_spec_publish:%d" % cid)])
    keyboard.append([InlineKeyboardButton("← Вернуться к карточке", callback_data="car_open:%d" % cid)])
    await q.message.reply_text("\n".join(lines), parse_mode="HTML",
                               reply_markup=InlineKeyboardMarkup(keyboard),
                               disable_web_page_preview=True)
    raise ApplicationHandlerStop

async def additional_spec_item(update, context):
    q, staff = await _ua099_require_staff(update)
    _, cid, spec_id = q.data.split(":", 2)
    card = _ua099_card(cid)
    item = _ua099_spec.get_spec(int(spec_id), _ua099_uid(card))
    if not item:
        await q.message.reply_text("Характеристика не найдена.", reply_markup=_ua099_back(cid))
        raise ApplicationHandlerStop
    state = "видно клиентам" if int(item["is_visible"]) else "скрыто от клиентов"
    manual = "ручное значение защищено" if int(item["is_manual"]) else "подтверждено источниками"
    try:
        domains = ", ".join(__import__("json").loads(item.get("source_domains_json") or "[]")) or "—"
    except Exception:
        domains = "—"
    text = ("<b>%s</b>\n%s\nКатегория: %s · единица: %s\n"
            "Проверка: %s · уверенность %.0f%% · свидетельств %d\n"
            "Источники: %s\nСтатус: %s · %s" % (
        _ua099_html.escape(str(item["label_ru"])),
        _ua099_html.escape(str(item["field_value"])),
        _ua099_html.escape(_ua099_spec.CATEGORY_TITLES.get(item["category"], item["category"])),
        _ua099_html.escape(str(item.get("unit") or "—")),
        _ua099_html.escape(str(item.get("verification_status") or "VERIFIED")),
        float(item.get("confidence") or 0.0) * 100,
        int(item.get("evidence_count") or 0),
        _ua099_html.escape(domains),
        state, manual))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Скрыть" if int(item["is_visible"]) else "Показать",
                              callback_data="car_spec_vis:%s:%s" % (cid, spec_id)),
         InlineKeyboardButton("Изменить значение",
                              callback_data="car_spec_edit:%s:%s" % (cid, spec_id))],
        [InlineKeyboardButton("Изменить категорию",
                              callback_data="car_spec_cat:%s:%s" % (cid, spec_id))],
        [InlineKeyboardButton("← К списку", callback_data="car_spec:%s" % cid)],
    ])
    await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
    raise ApplicationHandlerStop

async def additional_spec_visibility(update, context):
    q, staff = await _ua099_require_staff(update)
    _, cid, spec_id = q.data.split(":", 2)
    card = _ua099_card(cid)
    item = _ua099_spec.get_spec(int(spec_id), _ua099_uid(card))
    if not item:
        await q.message.reply_text("Характеристика не найдена.", reply_markup=_ua099_back(cid))
        raise ApplicationHandlerStop
    changed = _ua099_spec.set_visible(int(spec_id), _ua099_uid(card),
                                      not bool(int(item["is_visible"])), int(q.from_user.id))
    await q.message.reply_text(
        "Сохранено: %s." % ("видно клиентам" if int(changed["is_visible"]) else "скрыто от клиентов"),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "← К дополнительной спецификации", callback_data="car_spec:%s" % cid)]]))
    raise ApplicationHandlerStop

async def additional_spec_edit(update, context):
    q, staff = await _ua099_require_staff(update)
    _, cid, spec_id = q.data.split(":", 2)
    card = _ua099_card(cid)
    item = _ua099_spec.get_spec(int(spec_id), _ua099_uid(card))
    if not item:
        await q.message.reply_text("Характеристика не найдена.", reply_markup=_ua099_back(cid))
        raise ApplicationHandlerStop
    context.user_data["ua099_spec_edit"] = {
        "cid": int(cid), "spec_id": int(spec_id), "actor_id": int(q.from_user.id),
    }
    await q.message.reply_text(
        "Пришлите новое значение для «%s». Цена закупки и основные поля CRM здесь запрещены."
        % item["label_ru"],
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "Отмена", callback_data="car_spec:%s" % cid)]]))
    raise ApplicationHandlerStop

async def additional_spec_edit_message(update, context):
    state = context.user_data.get("ua099_spec_edit")
    if not state:
        return
    if int(update.effective_user.id) != int(state.get("actor_id")):
        return
    staff = db.get_staff(update.effective_user.id)
    if not staff:
        context.user_data.pop("ua099_spec_edit", None)
        await update.effective_message.reply_text("Доступ к CRM не разрешён.")
        raise ApplicationHandlerStop
    text = str(update.effective_message.text or "").strip()
    cid = int(state["cid"])
    card = _ua099_card(cid)
    try:
        item = _ua099_spec.set_manual_value(int(state["spec_id"]), _ua099_uid(card), text,
                                            int(update.effective_user.id))
    except Exception as exc:
        await update.effective_message.reply_text(
            "Значение не сохранено: %s" % _ua099_html.escape(str(exc)), parse_mode="HTML")
        raise ApplicationHandlerStop
    finally:
        if text:
            context.user_data.pop("ua099_spec_edit", None)
    await update.effective_message.reply_text(
        "Сохранено как ручное защищённое значение: <b>%s</b>. "
        "Публичная страница не обновлялась автоматически." % _ua099_html.escape(str(item["field_value"])),
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "← К дополнительной спецификации", callback_data="car_spec:%d" % cid)]]))
    raise ApplicationHandlerStop

async def additional_spec_category(update, context):
    q, staff = await _ua099_require_staff(update)
    _, cid, spec_id = q.data.split(":", 2)
    card = _ua099_card(cid)
    item = _ua099_spec.get_spec(int(spec_id), _ua099_uid(card))
    if not item:
        await q.message.reply_text("Характеристика не найдена.", reply_markup=_ua099_back(cid))
        raise ApplicationHandlerStop
    buttons = []
    for category in _ua099_spec.CATEGORIES:
        buttons.append([InlineKeyboardButton(
            _ua099_spec.CATEGORY_TITLES[category],
            callback_data="car_spec_setcat:%s:%s:%s" % (cid, spec_id, category))])
    buttons.append([InlineKeyboardButton("← Назад", callback_data="car_spec_item:%s:%s" % (cid, spec_id))])
    await q.message.reply_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(buttons))
    raise ApplicationHandlerStop

async def additional_spec_set_category(update, context):
    q, staff = await _ua099_require_staff(update)
    _, cid, spec_id, category = q.data.split(":", 3)
    card = _ua099_card(cid)
    item = _ua099_spec.set_category(int(spec_id), _ua099_uid(card), category, int(q.from_user.id))
    await q.message.reply_text(
        "Категория сохранена: %s. Публичная страница не обновлялась автоматически."
        % _ua099_spec.CATEGORY_TITLES[item["category"]],
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "← К дополнительной спецификации", callback_data="car_spec:%s" % cid)]]))
    raise ApplicationHandlerStop

async def additional_spec_publish(update, context):
    q, staff = await _ua099_require_staff(update)
    cid = int(q.data.split(":")[-1])
    card = _ua099_card(cid)
    if not card.get("published"):
        await q.message.reply_text("Карточка не опубликована. Автопубликация запрещена.",
                                   reply_markup=_ua099_back(cid))
        raise ApplicationHandlerStop
    import asyncio as _ua099_asyncio
    import publikaciya as _ua099_publisher
    ok, detail = await _ua099_asyncio.to_thread(_ua099_publisher.opublikovat, _ua099_uid(card))
    await q.message.reply_text(str(detail), reply_markup=_ua099_back(cid),
                               disable_web_page_preview=True)
    if ok is not True:
        raise ApplicationHandlerStop
    raise ApplicationHandlerStop

def register(app):
    _UA099_BASE_REGISTER(app)
    group = -3
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
                                   additional_spec_edit_message), group=group)
    app.add_handler(CallbackQueryHandler(additional_spec_screen,
                                         pattern=r"^car_spec:\d+$"), group=group)
    app.add_handler(CallbackQueryHandler(additional_spec_item,
                                         pattern=r"^car_spec_item:\d+:\d+$"), group=group)
    app.add_handler(CallbackQueryHandler(additional_spec_visibility,
                                         pattern=r"^car_spec_vis:\d+:\d+$"), group=group)
    app.add_handler(CallbackQueryHandler(additional_spec_edit,
                                         pattern=r"^car_spec_edit:\d+:\d+$"), group=group)
    app.add_handler(CallbackQueryHandler(additional_spec_category,
                                         pattern=r"^car_spec_cat:\d+:\d+$"), group=group)
    app.add_handler(CallbackQueryHandler(additional_spec_set_category,
                                         pattern=r"^car_spec_setcat:\d+:\d+:[a-z_]+$"), group=group)
    app.add_handler(CallbackQueryHandler(additional_spec_publish,
                                         pattern=r"^car_spec_publish:\d+$"), group=group)
# <<< UA099 ADDITIONAL SPEC CRM V1
'''.strip()


PUBLISH_BLOCK = r'''
# >>> UA099 PUBLICATION CONTRACT V1
_UA099_BASE_PROVERIT = proverit

def proverit(html, kod):
    errors = [item for item in _UA099_BASE_PROVERIT(html, kod)
              if item not in ("нет кнопки Задаток 500 $", "нет кнопки Купить")]
    import re as _ua099_re
    import ua_additional_spec as _ua099_spec
    stage_match = _ua099_re.search(r"data-ua-stage=['\"](\d+)['\"]", html or "", _ua099_re.I)
    stage = int(stage_match.group(1)) if stage_match else _ua099_spec._stage_number(kod)
    expected = "Купить" if stage == 4 else "Задаток 500 $"
    if expected not in (html or ""):
        errors.append("нет основной кнопки " + expected)
    for item in _ua099_spec.public_contract_errors(html or "", kod):
        errors.append("TASK099: " + item)
    return list(dict.fromkeys(errors))
# <<< UA099 PUBLICATION CONTRACT V1
'''.strip()


GUARD_BLOCK = r'''
# >>> UA099 BOUNDED GZIP SNAPSHOT V1
# The publisher writes card HTML, diagnostic HTML and catalogs only.  Media
# directories are operator-owned and are deliberately excluded from this
# transaction snapshot.  A separate TASK099 outer backup protects every
# public target before this guard is installed.
import gzip as _ua099_gzip

def _matching_paths(codes):
    normalized = {_code(value) for value in codes}
    paths = {root / "katalog.html" for root in ROOTS}
    for code in normalized:
        for root in ROOTS:
            paths.add(root / (code + ".html"))
            paths.add(root / (code + "-diag.html"))
            if root.is_dir():
                paths.update(path for path in root.glob(code + "*.html") if path.is_file())
    return paths


class Snapshot:
    """Exact rollback snapshot, bounded to publisher-written HTML and gzip stored."""

    def __init__(self, codes):
        self.codes = {_code(value) for value in codes}
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.root = BACKUPS / (stamp + "-" + uuid.uuid4().hex[:12])
        self.root.mkdir(parents=True, exist_ok=False)
        self.before_paths = _matching_paths(self.codes)
        self.present = {path for path in self.before_paths if path.is_file()}
        manifest = {}
        for path in sorted(self.before_paths):
            item = {"exists": path in self.present, "path": str(path)}
            if path in self.present:
                data = _read(path)
                relative = path.relative_to(ROOT)
                stored_relative = pathlib.Path("files") / (str(relative) + ".gz")
                target = self.root / stored_relative
                packed = _ua099_gzip.compress(data, compresslevel=9, mtime=0)
                _atomic(target, packed, 0o600)
                item.update({
                    "sha256": _sha(data), "mode": path.stat().st_mode & 0o777,
                    "storage": "gzip-v1", "stored_relative": str(stored_relative),
                    "stored_bytes": len(packed),
                })
            manifest[str(path)] = item
        _atomic(
            self.root / "manifest.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
            0o600,
        )

    def restore(self):
        current = _matching_paths(self.codes)
        removed, restored = [], []
        for path in sorted(current - self.present, reverse=True):
            if path.is_file():
                path.unlink()
                removed.append(str(path))
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        for path in sorted(self.present):
            item = manifest[str(path)]
            stored = (self.root / str(item["stored_relative"])).resolve()
            if self.root.resolve() not in stored.parents or not stored.is_file():
                raise PublishError("SNAPSHOT_GZIP_SCOPE:" + str(path))
            data = _ua099_gzip.decompress(_read(stored))
            if _sha(data) != item["sha256"]:
                raise PublishError("SNAPSHOT_GZIP_SHA:" + str(path))
            if not path.is_file() or _read(path) != data:
                _atomic(path, data, int(item.get("mode") or 0o644))
                restored.append(str(path))
        mismatches = [
            str(path) for path in self.present
            if not path.is_file() or _sha(_read(path)) != manifest[str(path)]["sha256"]
        ]
        if mismatches:
            raise PublishError("ROLLBACK_READBACK_MISMATCH:" + ",".join(mismatches))
        return {"backup_root": str(self.root), "removed": removed, "restored": restored}
# <<< UA099 BOUNDED GZIP SNAPSHOT V1
'''.strip()


def patch_master(source: str) -> str:
    source = _without(source, MASTER_START, MASTER_END)
    for name in ("obrabotat_kartochku", "obrabotat_diagnostiku", "proverit"):
        if not re.search(r"^def\s+" + name + r"\s*\(", source, re.M):
            raise RuntimeError("MASTER_ENTRYPOINT_MISSING:" + name)
    return _compiled(source.rstrip() + "\n\n" + MASTER_BLOCK + "\n", "master_card.py")


def patch_cars_ui(source: str) -> str:
    source = _without(source, CRM_START, CRM_END)
    for name in ("render", "card_kb", "register"):
        if not re.search(r"^def\s+" + name + r"\s*\(", source, re.M):
            raise RuntimeError("CRM_ENTRYPOINT_MISSING:" + name)
    return _compiled(source.rstrip() + "\n\n" + CRM_BLOCK + "\n", "cars_ui.py")


def patch_publikaciya(source: str) -> str:
    source = _without(source, PUBLISH_START, PUBLISH_END)
    if not re.search(r"^def\s+proverit\s*\(", source, re.M):
        raise RuntimeError("PUBLISH_VALIDATOR_MISSING")
    if not re.search(r"^def\s+opublikovat\s*\(", source, re.M):
        raise RuntimeError("PUBLISH_ENTRYPOINT_MISSING")
    return _compiled(source.rstrip() + "\n\n" + PUBLISH_BLOCK + "\n", "publikaciya.py")


def patch_publish_transaction_guard(source: str) -> str:
    source = _without(source, GUARD_START, GUARD_END)
    for name in ("Snapshot", "_matching_paths", "publish_batch"):
        if not re.search(r"^(?:class|def)\s+" + name + r"\b", source, re.M):
            raise RuntimeError("PUBLISH_GUARD_ENTRYPOINT_MISSING:" + name)
    return _compiled(source.rstrip() + "\n\n" + GUARD_BLOCK + "\n", "publish_transaction_guard.py")


def selftest() -> None:
    sample_master = ("def obrabotat_kartochku(html,kod):\n    return html\n"
                     "def obrabotat_diagnostiku(html,kod):\n    return html\n"
                     "def proverit(html,kod=''):\n    return []\n")
    once = patch_master(sample_master)
    twice = patch_master(once)
    assert once == twice and once.count(MASTER_START) == 1
    sample_crm = "def render(card,staff): return ''\ndef card_kb(card,staff): return None\ndef register(app): pass\n"
    crm_once = patch_cars_ui(sample_crm)
    crm_twice = patch_cars_ui(crm_once)
    assert crm_once == crm_twice and crm_once.count(CRM_START) == 1
    sample_publish = ("def proverit(html,kod): return []\n"
                      "def opublikovat(kod,proba=False): return True,''\n")
    publish_once = patch_publikaciya(sample_publish)
    publish_twice = patch_publikaciya(publish_once)
    assert publish_once == publish_twice and publish_once.count(PUBLISH_START) == 1
    print("UA099_PATCHES_SELFTEST_PASS")


if __name__ == "__main__":
    selftest()
