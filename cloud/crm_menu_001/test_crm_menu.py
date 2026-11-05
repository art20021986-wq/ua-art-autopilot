"""Main menu buttons: the pure row logic, and the cars_ui.py edit on the server source read by probe R4."""
import json
from pathlib import Path
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate  # noqa: E402
import ua_menu_extra  # noqa: E402

PROBE = HERE.parent / 'lead_desk_probe_001' / '20261105-R4.json'


class Button:
    def __init__(self, text, callback_data=None):
        self.text, self.callback_data = text, callback_data


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def stub_telegram():
    sys.modules['telegram'] = types.SimpleNamespace(InlineKeyboardButton=Button, InlineKeyboardMarkup=Markup)


class RowsTests(unittest.TestCase):
    def test_adds_leads_then_more(self):
        self.assertEqual(ua_menu_extra.rows_to_add({'cards_cars'}, 'leads:list'),
                         [('📨 Заявки с сайта', 'leads:list'), ('⋯ Ещё', 'crm_more')])

    def test_never_twice_and_no_leads_without_order_package(self):
        self.assertEqual(ua_menu_extra.rows_to_add({'leads:list', 'crm_more'}, 'leads:list'), [])
        self.assertEqual(ua_menu_extra.rows_to_add(set(), None), [('⋯ Ещё', 'crm_more')])

    def test_with_buttons_keeps_existing_rows(self):
        stub_telegram()
        sys.modules['ua_site_leads'] = types.SimpleNamespace(CALLBACK='leads:list', available=lambda: True)
        menu = ua_menu_extra.with_buttons(Markup([[Button('Автомобили', 'cards_cars')]]))
        self.assertEqual([b.callback_data for r in menu.inline_keyboard for b in r], ['cards_cars', 'leads:list', 'crm_more'])


class CarsUiEditTests(unittest.TestCase):
    def source(self):
        return json.loads(PROBE.read_text())['files']['cars_ui.py']['source']

    def test_block_appended_once_and_compiles(self):
        result = candidate.cars_ui(self.source())
        self.assertEqual(result.count(candidate.MARK), 1)
        self.assertTrue(result.startswith(self.source().rstrip('\n')))
        compile(candidate.BLOCK, 'block', 'exec')  # the probe copy is sanitized; the server smoke compiles the real file
        with self.assertRaises(candidate.CandidateError):
            candidate.cars_ui(result)

    def test_wraps_the_previous_menu_and_survives_a_failure(self):
        # Run only the appended block against a stand-in previous with_stats_button.
        stub_telegram()
        sys.modules['ua_site_leads'] = types.SimpleNamespace(CALLBACK='leads:list', available=lambda: True)
        logged = []
        scope = {'with_stats_button': lambda m: Markup([[Button('Фото', 'home_photo')]]),
                 'log': types.SimpleNamespace(warning=lambda *a: logged.append(a))}
        exec(candidate.BLOCK, scope)
        menu = scope['with_stats_button'](None)
        self.assertEqual([b.callback_data for r in menu.inline_keyboard for b in r], ['home_photo', 'leads:list', 'crm_more'])
        sys.modules['ua_menu_extra'] = None  # import fails → previous menu, one warning
        menu = scope['with_stats_button'](None)
        self.assertEqual([b.callback_data for r in menu.inline_keyboard for b in r], ['home_photo'])
        self.assertEqual(len(logged), 1)
        del sys.modules['ua_menu_extra']


if __name__ == '__main__':
    unittest.main()
