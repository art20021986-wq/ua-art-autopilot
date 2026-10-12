#!/usr/bin/env python3
"""Builder tests on a fixture that copies the installed with_stats_button and more_screen."""
import ast
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('build_cars_ui', HERE / 'build_cars_ui.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

SOURCE = '''class InlineKeyboardButton:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class InlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


HIDE = {"cards_hidden"}
MORE = {"cards_clients", "staff_list"}


def with_stats_button(markup):
    """Оставляет на виду только рабочее, остальное убирает в «Ещё»."""
    try:
        rows = list(markup.inline_keyboard)
    except Exception:
        return markup
    clean, spryatano = [], []
    for row in rows:
        keep = []
        for b in row:
            cb = getattr(b, "callback_data", None)
            if cb in HIDE:
                continue
            if cb in MORE:
                spryatano.append(b)
                continue
            keep.append(b)
        if keep:
            clean.append(keep)
    clean.append([InlineKeyboardButton("Отчёт по клиентам",
                                       callback_data="crm_stats")])
    clean.append([InlineKeyboardButton("Запуск оптимизации",
                                       callback_data="crm_optimize")])
    if spryatano:
        clean.append([InlineKeyboardButton("Ещё", callback_data="crm_more")])
    return InlineKeyboardMarkup(clean)


async def more_screen(update, context):
    """Скрытое меню: то, что нужно не каждый день."""
    return InlineKeyboardButton("Клиенты", callback_data="cards_clients")
'''.encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(source):
    """Import the given source as a real module from a temporary file."""
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'cars_ui_fixture.py'
        path.write_bytes(source)
        module_spec = importlib.util.spec_from_file_location('cars_ui_fixture', path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    return vars(module)


def menu(module):
    button = module['InlineKeyboardButton']
    markup = module['InlineKeyboardMarkup']([
        [button('🚗 Автомобили', 'cards_cars')],
        [button('Скрытое', 'cards_hidden')],
        [button('Клиенты', 'cards_clients'), button('Сотрудники', 'staff_list')],
    ])
    result = module['with_stats_button'](markup)
    return [[(x.text, x.callback_data) for x in row] for row in result.inline_keyboard]


class BuildTests(unittest.TestCase):
    def build(self):
        return b.build(SOURCE, expected=sha(SOURCE))

    def test_fixture_reproduces_owner_screenshot(self):
        labels = [row[0][0] for row in menu(load(SOURCE))]
        self.assertEqual(labels, ['🚗 Автомобили', 'Отчёт по клиентам', 'Запуск оптимизации', 'Ещё'])

    def test_menu_keeps_only_working_buttons(self):
        self.assertEqual(menu(load(self.build())), [[('🚗 Автомобили', 'cards_cars')]])

    def test_non_keyboard_is_returned_unchanged(self):
        module = load(self.build())
        marker = object()
        self.assertIs(module['with_stats_button'](marker), marker)

    def test_only_target_function_changes(self):
        out = self.build().decode()
        for value in b.REMOVED:
            self.assertNotIn('"%s"' % value, out)
        names = [n.name for n in ast.parse(out).body if hasattr(n, 'name')]
        self.assertEqual(names, ['InlineKeyboardButton', 'InlineKeyboardMarkup',
                                 'with_stats_button', 'more_screen'])
        before, after = SOURCE.decode().split('def with_stats_button')
        self.assertTrue(out.startswith(before))
        self.assertTrue(out.endswith('\n\n\nasync def more_screen' + after.split('async def more_screen')[1]))

    def test_refuses_other_source_duplicates_and_rebuild(self):
        with self.assertRaises(b.BuildError):
            b.build(SOURCE)
        twice = SOURCE + b'\ndef with_stats_button(m):\n    return m\n'
        with self.assertRaises(b.BuildError):
            b.build(twice, expected=sha(twice))
        built = self.build()
        with self.assertRaises(b.BuildError):
            b.build(built, expected=sha(built))


if __name__ == '__main__':
    unittest.main()
