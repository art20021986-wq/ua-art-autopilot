"""Corrective menu release: role buttons put back, the cars_ui.py one-line edit, and the protected-set fix."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate  # noqa: E402
import ua_menu_extra  # noqa: E402

PREVIOUS_BLOCK = (HERE.parent / 'crm_menu_001' / 'candidate.py')


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def flat(markup):
    return [b.callback_data for r in markup.inline_keyboard for b in r]


def setUpModule():
    sys.modules['telegram'] = types.SimpleNamespace(InlineKeyboardButton=Button, InlineKeyboardMarkup=Markup)


OWNER = Markup([[Button('🚗 Автомобили', 'cards_cars'), Button('👤 Клиенты', 'cards_clients')],
                [Button('🔎 Поиск', 'search_start')], [Button('👥 Сотрудники', 'staff_list')]])
MANAGER = Markup([[Button('🚗 Автомобили', 'cards_cars'), Button('👤 Клиенты', 'cards_clients')]])
SHOWN = Markup([[Button('🚗 Автомобили', 'cards_cars')], [Button('🖼 Фото главной страницы', 'home_photo')]])


class MenuTests(unittest.TestCase):
    def test_owner_gets_clients_and_staff_only(self):
        menu = ua_menu_extra.with_buttons(OWNER, SHOWN)
        self.assertEqual(flat(menu), ['cards_cars', 'home_photo', 'cards_clients', 'staff_list'])
        self.assertEqual([b.text for r in menu.inline_keyboard for b in r][-2:], ['👤 Клиенты', '👥 Сотрудники'])

    def test_manager_never_gets_staff(self):
        self.assertEqual(flat(ua_menu_extra.with_buttons(MANAGER, SHOWN)), ['cards_cars', 'home_photo', 'cards_clients'])

    def test_no_duplicates_and_no_old_buttons(self):
        once = ua_menu_extra.with_buttons(OWNER, SHOWN)
        self.assertEqual(flat(ua_menu_extra.with_buttons(OWNER, once)), flat(once))
        self.assertNotIn('leads:list', flat(once))
        self.assertNotIn('crm_more', flat(once))


class CarsUiEditTests(unittest.TestCase):
    def installed(self):
        spec = importlib.util.spec_from_file_location('previous_candidate', PREVIOUS_BLOCK)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return 'def with_stats_button(markup):\n    return markup\n' + module.BLOCK

    def test_one_line_changes(self):
        before = self.installed()
        after = candidate.cars_ui(before)
        self.assertEqual(len(before.splitlines()), len(after.splitlines()))
        self.assertEqual(sum(a != b for a, b in zip(before.splitlines(), after.splitlines())), 1)
        with self.assertRaises(candidate.CandidateError):
            candidate.cars_ui(after)

    def test_block_passes_role_menu(self):
        logged = []
        sys.modules['menu_prelude'] = types.SimpleNamespace(
            previous=lambda m: SHOWN, log=types.SimpleNamespace(warning=lambda *a: logged.append(a)))
        block = candidate.cars_ui(self.installed()).split('\n', 2)[2]
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'menu_block_r2.py').write_text(
                'from menu_prelude import previous as with_stats_button, log\n' + block, encoding='utf-8')
            sys.path.insert(0, temp)
            try:
                module = importlib.import_module('menu_block_r2')
            finally:
                sys.path.remove(temp)
                sys.modules.pop('menu_block_r2', None)
        self.assertEqual(flat(module.with_stats_button(OWNER)), ['cards_cars', 'home_photo', 'cards_clients', 'staff_list'])
        self.assertEqual(logged, [])


class ProtectedSetTests(unittest.TestCase):
    def test_replaced_file_is_not_protected(self):
        source = (HERE / 'deployment_remote.py').read_text(encoding='utf-8')
        self.assertIn('sorted(protected_names - set(candidate))', source)


if __name__ == '__main__':
    unittest.main()
