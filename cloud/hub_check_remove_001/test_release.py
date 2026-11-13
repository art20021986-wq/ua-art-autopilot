#!/usr/bin/env python3
"""HUB-CHECK-REMOVE-001: the «how we check» section and its texts leave the Korea hubs; nothing else changes."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

import candidate_builder as builder
import deployment_controller as controller

HERE = Path(__file__).resolve().parent
LIVE = (HERE/'fixtures'/'ua_seo_hub_texts.txt').read_bytes()  # SEO-UKRAINE-PAGE-001 version, 2026-11-12
sys.modules.setdefault('ua_seo_ukraine_page', SimpleNamespace(TOPIC={'uk': {'link': 'По всій Україні'},
                                                                    'ru': {'link': 'По всей Украине'}}))


def module(source, name):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/(name + '.txt')
        path.write_bytes(source)
        loader = importlib.machinery.SourceFileLoader(name, str(path))
        spec = importlib.util.spec_from_loader(name, loader)
        value = importlib.util.module_from_spec(spec)
        loader.exec_module(value)
    return value


class RemovalTests(unittest.TestCase):
    def test_section_gone_rest_kept(self):
        before = module(LIVE, 'hub_texts_before')
        after = module(builder.build({builder.NAME: LIVE}, {})[builder.NAME], 'hub_texts_after')
        link = lambda key: '/x'
        for lang, title in (('uk', 'Як ми перевіряємо авто до покупки'), ('ru', 'Как мы проверяем авто до покупки')):
            old, new = before.hub(lang, link), after.hub(lang, link)
            self.assertIn(title, old)
            self.assertNotIn(title, new)
            for gone in controller.GONE:
                self.assertNotIn(gone, new)
            section = old[old.index('<h2>%s</h2>' % title):]
            section = section[:section.index('</ul>') + 5]
            self.assertEqual(old.replace(section, ''), new)  # only the section left
            self.assertNotIn('check', after.TEXTS[lang])
            self.assertEqual(before.order_steps(lang), after.order_steps(lang))
            self.assertEqual({k: v for k, v in before.TEXTS[lang].items() if not k.startswith('check')},
                             after.TEXTS[lang])

    def test_refusals(self):
        with self.assertRaisesRegex(ValueError, 'HUB_CHECK_ALREADY_APPLIED'):
            builder.build({builder.NAME: builder.build({builder.NAME: LIVE}, {})[builder.NAME]}, {})
        with self.assertRaisesRegex(ValueError, 'HUB_CHECK_EDIT'):
            builder.build({builder.NAME: LIVE.replace(b'check_title=', b'title_x=', 1)}, {})


class PublicCheckTests(unittest.TestCase):
    def test_hub_checks(self):
        uk = controller.EXPECTED['/video/seo/ua/avto-z-korei-do-kyieva-pid-kluch.html']
        self.assertTrue(uk('<h2>Моделі з Кореї</h2>'))
        self.assertFalse(uk('<h2>Моделі з Кореї</h2><h2>Як ми перевіряємо авто до покупки</h2>'))
        ru = controller.EXPECTED['/video/seo/ru/avto-iz-korei-v-kiev-pod-kluch.html']
        self.assertFalse(ru('<h2>Модели из Кореи</h2>... лакокрасочное ...'))


if __name__ == '__main__':
    unittest.main()
