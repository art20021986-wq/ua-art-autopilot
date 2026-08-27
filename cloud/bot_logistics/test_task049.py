#!/usr/bin/env python3
"""Offline regression tests for the TASK 049 candidate transform."""
from __future__ import annotations

import hashlib
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import task049_transform as T  # noqa: E402


def source_fixture() -> str:
    return '''from object import InlineKeyboardButton, InlineKeyboardMarkup

LABELS_ALL = {
    "eta_days": "срок доставки", "auto_number": "номер авто",
}

EDITABLE = [
    ("auto_number", "Номер авто"),
    ("price_uah", "Цена продажи"), ("diag_link", "Ссылка на отчёт"),
    ("diag_text", "Описание диагностики"),
    ("eta_days", "Дней до прибытия"),
    ("sea_container", "Номер контейнера"),
]

def card_kb(card, staff):
    cid = card["id"]
    rows = [
        [InlineKeyboardButton("Редактировать", callback_data="car_edit:%d" % cid),
         InlineKeyboardButton("Фото и видео", callback_data="car_media:%d" % cid)],
        [InlineKeyboardButton("Комплексная диагностика", callback_data="car_cond:%d" % cid),
         InlineKeyboardButton("Сменить этап", callback_data="car_stage:%d" % cid)],
        [InlineKeyboardButton("Описание",
                              callback_data="car_setf:%d:condition_text" % cid)],
        [InlineKeyboardButton("Срок доставки", callback_data="car_setf:%d:eta_days" % cid)],
    ]
    return rows

async def edit_menu(update, context):
    cid = 1
    rows, buf = [], []
    if buf:
        rows.append(buf)
    rows.append([InlineKeyboardButton("← К карточке", callback_data="car_open:%d" % cid)])

# ─────────────────────────────────────────────────────────────
# ЭТАПЫ
# ─────────────────────────────────────────────────────────────

async def stage_menu(update, context):
    return None

async def stage_set(update, context):
    cid = 1
    left = 4
    rows = []
    if left is not None:
        rows.append([InlineKeyboardButton("Изменить срок доставки",
                                          callback_data="car_setf:%d:eta_days" % cid)])
    return rows

def register(app, g):
    app.add_handler(CallbackQueryHandler(stage_menu, pattern=r"^car_stage:"), group=g)
'''


class TransformTests(unittest.TestCase):
    def transform(self, source=None):
        source = source_fixture() if source is None else source
        return T.transform_source(source, hashlib.sha256(source.encode()).hexdigest())

    def test_candidate_compiles_and_has_exact_central_entries(self):
        result = self.transform()
        checks = T.validate_candidate(result.candidate)
        self.assertTrue(checks["compiled"])
        self.assertEqual(checks["hub_outer_labels"], 2)
        self.assertEqual(checks["card_entry"], 1)
        self.assertEqual(checks["editor_entry"], 1)

    def test_old_duplicate_buttons_and_editor_fields_are_absent(self):
        candidate = self.transform().candidate
        self.assertNotIn('InlineKeyboardButton("Срок доставки"', candidate)
        self.assertNotIn('InlineKeyboardButton("Изменить срок доставки"', candidate)
        self.assertNotIn('("eta_days", "Дней до прибытия")', candidate)
        self.assertNotIn('("sea_container", "Номер контейнера")', candidate)

    def test_hub_uses_existing_selected_card_callbacks(self):
        candidate = self.transform().candidate
        for callback in (
            'callback_data="car_stage:%d" % cid',
            'callback_data="car_setf:%d:sea_container" % cid',
            'callback_data="car_setf:%d:eta_days" % cid',
        ):
            self.assertIn(callback, candidate)
        self.assertIn('parts[2] not in ("card", "edit")', candidate)

    def test_unrelated_controls_and_fields_are_preserved(self):
        candidate = self.transform().candidate
        for value in (
            "Редактировать",
            "Фото и видео",
            "Комплексная диагностика",
            "Описание",
            '("auto_number", "Номер авто")',
            '("price_uah", "Цена продажи")',
            '("diag_link", "Ссылка на отчёт")',
            '("diag_text", "Описание диагностики")',
        ):
            self.assertIn(value, candidate)

    def test_eta_prompt_label_is_quantity_of_days(self):
        candidate = self.transform().candidate
        self.assertIn('"eta_days": "количество дней до прибытия"', candidate)
        self.assertNotIn('"eta_days": "срок доставки"', candidate)

    def test_each_exact_anchor_must_be_unique(self):
        source = source_fixture().replace(T.CARD_OLD, T.CARD_OLD + T.CARD_OLD)
        with self.assertRaisesRegex(T.TransformBlocked, "anchor_count"):
            self.transform(source)

    def test_missing_anchor_blocks(self):
        source = source_fixture().replace(T.POST_STAGE_OLD, "")
        with self.assertRaisesRegex(T.TransformBlocked, "anchor_count"):
            self.transform(source)

    def test_sha_mismatch_blocks_before_transform(self):
        with self.assertRaisesRegex(T.TransformBlocked, "source_sha256_mismatch"):
            T.transform_source(source_fixture(), "0" * 64)

    def test_idempotent_when_rebound_to_candidate_hash(self):
        first = self.transform()
        second = T.transform_source(first.candidate, first.candidate_sha256)
        self.assertTrue(second.already_applied)
        self.assertEqual(second.candidate, first.candidate)
        self.assertEqual(second.candidate_sha256, first.candidate_sha256)

    def test_ten_fresh_runs_are_deterministic(self):
        candidates = [self.transform().candidate_sha256 for _ in range(10)]
        self.assertEqual(len(set(candidates)), 1)

    def test_callback_templates_fit_telegram_limit(self):
        callbacks = (
            "car_logistics:999999999999999999:card",
            "car_logistics:999999999999999999:edit",
            "car_setf:999999999999999999:sea_container",
            "car_setf:999999999999999999:eta_days",
        )
        for callback in callbacks:
            self.assertLessEqual(len(callback.encode("utf-8")), 64)


if __name__ == "__main__":
    unittest.main()

