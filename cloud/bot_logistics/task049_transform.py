#!/usr/bin/env python3
"""Strict, deterministic TASK 049 transform for the BOT CRM logistics hub.

This module is pure: it transforms supplied text in memory and never opens,
writes or executes production files. The remote Gate A runner binds its use to
the previously discovered SHA-256 of /home/Carix/cars_ui.py.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass

EXPECTED_SOURCE_SHA256 = (
    "06e7da916ea36c4ffafef01c85f59a0574f06d3cdda24aa1f8c242175de726b7"
)
HUB_LABEL = "🚢 Этапы и доставка"


class TransformBlocked(RuntimeError):
    """Fail-closed refusal caused by an unproved source shape."""


@dataclass(frozen=True)
class TransformResult:
    source_sha256: str
    candidate_sha256: str
    candidate: str
    operations: tuple[str, ...]
    already_applied: bool


CARD_OLD = '''    rows = [
        [InlineKeyboardButton("Редактировать", callback_data="car_edit:%d" % cid),
         InlineKeyboardButton("Фото и видео", callback_data="car_media:%d" % cid)],
        [InlineKeyboardButton("Комплексная диагностика", callback_data="car_cond:%d" % cid),
         InlineKeyboardButton("Сменить этап", callback_data="car_stage:%d" % cid)],
        [InlineKeyboardButton("Описание",
                              callback_data="car_setf:%d:condition_text" % cid)],
        [InlineKeyboardButton("Срок доставки", callback_data="car_setf:%d:eta_days" % cid)],
    ]
'''

CARD_NEW = '''    rows = [
        [InlineKeyboardButton("Редактировать", callback_data="car_edit:%d" % cid),
         InlineKeyboardButton("Фото и видео", callback_data="car_media:%d" % cid)],
        [InlineKeyboardButton("Комплексная диагностика",
                              callback_data="car_cond:%d" % cid)],
        [InlineKeyboardButton("Описание",
                              callback_data="car_setf:%d:condition_text" % cid)],
        [InlineKeyboardButton("🚢 Этапы и доставка",
                              callback_data="car_logistics:%d:card" % cid)],
    ]
'''

EDITABLE_OLD = '''    ("price_uah", "Цена продажи"), ("diag_link", "Ссылка на отчёт"),
    ("diag_text", "Описание диагностики"),
    ("eta_days", "Дней до прибытия"),
    ("sea_container", "Номер контейнера"),
]
'''

EDITABLE_NEW = '''    ("price_uah", "Цена продажи"), ("diag_link", "Ссылка на отчёт"),
    ("diag_text", "Описание диагностики"),
]
'''

EDITOR_BACK_OLD = '''    if buf:
        rows.append(buf)
    rows.append([InlineKeyboardButton("← К карточке", callback_data="car_open:%d" % cid)])
'''

EDITOR_BACK_NEW = '''    if buf:
        rows.append(buf)
    rows.append([InlineKeyboardButton("🚢 Этапы и доставка",
                                      callback_data="car_logistics:%d:edit" % cid)])
    rows.append([InlineKeyboardButton("← К карточке", callback_data="car_open:%d" % cid)])
'''

ETA_LABEL_OLD = '    "eta_days": "срок доставки", "auto_number": "номер авто",\n'
ETA_LABEL_NEW = '    "eta_days": "количество дней до прибытия", "auto_number": "номер авто",\n'

POST_STAGE_OLD = '''    if left is not None:
        rows.append([InlineKeyboardButton("Изменить срок доставки",
                                          callback_data="car_setf:%d:eta_days" % cid)])
'''

HUB_MARKER = '''# ─────────────────────────────────────────────────────────────
# ЭТАПЫ
# ─────────────────────────────────────────────────────────────
'''

HUB_CODE = '''async def logistics_hub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """One selected-card entry for stage, container and arrival days."""
    q = update.callback_query
    await q.answer()
    drop_wait(context)
    parts = q.data.split(":")
    if len(parts) != 3 or parts[2] not in ("card", "edit"):
        await q.message.reply_text("Не удалось открыть этапы и доставку.")
        raise ApplicationHandlerStop
    cid = int(parts[1])
    origin = parts[2]
    card = card_of(cid)
    if not card:
        await q.message.reply_text("Карточка машины не найдена.")
        raise ApplicationHandlerStop

    left, eta = eta_of(card)
    status = S.status_label(card.get("status")) or "—"
    container = card.get("sea_container") or "—"
    days_text = str(left) if left is not None else "—"
    eta_text = eta.strftime("%d.%m.%Y") if eta else "—"
    back = ("car_edit:%d" if origin == "edit" else "car_open:%d") % cid
    rows = [
        [InlineKeyboardButton("Сменить этап", callback_data="car_stage:%d" % cid)],
        [InlineKeyboardButton("Номер контейнера",
                              callback_data="car_setf:%d:sea_container" % cid)],
        [InlineKeyboardButton("Количество дней",
                              callback_data="car_setf:%d:eta_days" % cid)],
        [InlineKeyboardButton("← Назад", callback_data=back)],
    ]
    await q.message.reply_text(
        "🚢 <b>ЭТАПЫ И ДОСТАВКА</b>\\n\\n"
        "Этап: <b>%s</b>\\n"
        "Контейнер: <b>%s</b>\\n"
        "Осталось дней: <b>%s</b>\\n"
        "Дата прибытия: <b>%s</b>"
        % (status, container, days_text, eta_text),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    raise ApplicationHandlerStop


'''

REGISTER_OLD = '''    app.add_handler(CallbackQueryHandler(stage_menu, pattern=r"^car_stage:"), group=g)
'''

REGISTER_NEW = '''    app.add_handler(CallbackQueryHandler(
        logistics_hub, pattern=r"^car_logistics:[0-9]+:(?:card|edit)$"), group=g)
    app.add_handler(CallbackQueryHandler(stage_menu, pattern=r"^car_stage:"), group=g)
'''


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _replace_once(source: str, old: str, new: str, operation: str) -> str:
    count = source.count(old)
    if count != 1:
        raise TransformBlocked(f"anchor_count:{operation}:expected=1:actual={count}")
    return source.replace(old, new, 1)


def validate_candidate(candidate: str) -> dict[str, int | bool]:
    try:
        tree = ast.parse(candidate, filename="cars_ui.py.candidate")
        compile(tree, "cars_ui.py.candidate", "exec")
    except (SyntaxError, ValueError, TypeError) as exc:
        raise TransformBlocked("candidate_compile_failed") from exc

    async_functions = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)
    }
    if "logistics_hub" not in async_functions:
        raise TransformBlocked("logistics_hub_function_missing")

    checks = {
        "hub_outer_labels": candidate.count(HUB_LABEL),
        "card_entry": candidate.count('callback_data="car_logistics:%d:card" % cid'),
        "editor_entry": candidate.count('callback_data="car_logistics:%d:edit" % cid'),
        "hub_handler_registration": candidate.count(
            'logistics_hub, pattern=r"^car_logistics:[0-9]+:(?:card|edit)$"'
        ),
        "hub_stage_action": candidate.count(
            'InlineKeyboardButton("Сменить этап", callback_data="car_stage:%d" % cid)'
        ),
        "hub_container_action": candidate.count(
            'callback_data="car_setf:%d:sea_container" % cid'
        ),
        "hub_days_action": candidate.count(
            'callback_data="car_setf:%d:eta_days" % cid'
        ),
        "old_delivery_button": candidate.count(
            'InlineKeyboardButton("Срок доставки"'
        ),
        "old_post_stage_button": candidate.count(
            'InlineKeyboardButton("Изменить срок доставки"'
        ),
        "old_editor_days": candidate.count('("eta_days", "Дней до прибытия")'),
        "old_editor_container": candidate.count(
            '("sea_container", "Номер контейнера")'
        ),
    }
    expected = {
        "hub_outer_labels": 2,
        "card_entry": 1,
        "editor_entry": 1,
        "hub_handler_registration": 1,
        "hub_stage_action": 1,
        "hub_container_action": 1,
        "hub_days_action": 1,
        "old_delivery_button": 0,
        "old_post_stage_button": 0,
        "old_editor_days": 0,
        "old_editor_container": 0,
    }
    for key, value in expected.items():
        if checks[key] != value:
            raise TransformBlocked(
                f"candidate_invariant:{key}:expected={value}:actual={checks[key]}"
            )
    checks["compiled"] = True
    return checks


def transform_source(source: str, expected_sha256: str) -> TransformResult:
    if not isinstance(source, str):
        raise TransformBlocked("source_not_text")
    source_sha = sha256_text(source)
    if source_sha != expected_sha256:
        raise TransformBlocked("source_sha256_mismatch")

    if HUB_LABEL in source:
        validate_candidate(source)
        return TransformResult(
            source_sha256=source_sha,
            candidate_sha256=source_sha,
            candidate=source,
            operations=(),
            already_applied=True,
        )

    operations: list[str] = []
    candidate = source
    replacements = (
        (CARD_OLD, CARD_NEW, "centralize_card_keyboard"),
        (EDITABLE_OLD, EDITABLE_NEW, "remove_logistics_from_editor_grid"),
        (EDITOR_BACK_OLD, EDITOR_BACK_NEW, "add_editor_hub_entry"),
        (ETA_LABEL_OLD, ETA_LABEL_NEW, "rename_eta_field_label"),
        (POST_STAGE_OLD, "", "remove_post_stage_delivery_button"),
        (HUB_MARKER, HUB_CODE + HUB_MARKER, "insert_logistics_hub"),
        (REGISTER_OLD, REGISTER_NEW, "register_logistics_hub"),
    )
    for old, new, name in replacements:
        candidate = _replace_once(candidate, old, new, name)
        operations.append(name)

    validate_candidate(candidate)
    return TransformResult(
        source_sha256=source_sha,
        candidate_sha256=sha256_text(candidate),
        candidate=candidate,
        operations=tuple(operations),
        already_applied=False,
    )

