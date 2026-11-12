#!/usr/bin/env python3
"""Release-specific checks: exact installed inputs, the script and report patches on the real sources."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import candidate_builder
import ua_page_depth

HERE = Path(__file__).resolve().parent
SOURCE = {name: (HERE/'fixtures'/name.replace('.py', '.txt')).read_bytes() for name in candidate_builder.SOURCE_FILES}


def load(name, value, folder):
    path = Path(folder)/name
    path.write_bytes(value)
    spec = importlib.util.spec_from_file_location('t_' + name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)
        self.candidate = candidate_builder.build(SOURCE, {})
        sys.path.insert(0, self.folder)
        self.addCleanup(sys.path.remove, self.folder)
        self.yadro = load('analitika_yadro.py', self.candidate['analitika_yadro.py'], self.folder)
        load('ua_page_depth.py', self.candidate['ua_page_depth.py'], self.folder)
        self.otchet = load('analitika_otchet.py', self.candidate['analitika_otchet.py'], self.folder)
        self.yadro.BAZA = self.otchet.BAZA = os.path.join(self.folder, 'analytics.db')
        self.yadro.CRM = self.otchet.CRM = os.path.join(self.folder, 'none.db')

    def send(self, events):
        for number, (tip, page, label) in enumerate(events):
            self.assertEqual(self.yadro.zapisat({'t': tip, 'v': 'v1', 's': 's1', 'e': 'e%d' % number,
                                                 'p': page, 'z': label}), 'ok')

    def test_fixtures_are_the_installed_files(self):
        for name, digest in candidate_builder.SOURCE_SHA256.items():
            self.assertEqual(hashlib.sha256(SOURCE[name]).hexdigest(), digest)

    def test_builder_refuses_unexpected_input_and_double_patch(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            candidate_builder.build({**SOURCE, 'analitika_yadro.py': SOURCE['analitika_yadro.py'] + b'#'}, {})
        with self.assertRaisesRegex(ValueError, 'ALREADY_PATCHED'):
            candidate_builder.patch('analitika_otchet.py', self.candidate['analitika_otchet.py'])

    def test_planned_files_only(self):
        self.assertEqual(sorted(self.candidate), ['analitika_otchet.py', 'analitika_yadro.py', 'ua_page_depth.py'])
        self.assertEqual(candidate_builder.page_paths(HERE), [])

    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_page_script_is_valid_javascript(self):
        script = Path(self.folder)/'a.js'
        script.write_text(self.yadro.SKRIPT)
        subprocess.run(['node', '--check', str(script)], check=True)

    def test_new_events_are_accepted_and_depth_is_not_a_route_step(self):
        self.send([('card', '/video/UA-0013.html', ''), ('foto', '/video/UA-0013.html', ''),
                   ('scroll', '/video/UA-0013.html', '50'), ('knopka', '/video/UA-0013.html', 'Кредит')])
        connection = self.yadro._db()
        self.assertEqual(connection.execute('select put from sessions').fetchone()[0], 'UA-0013 > Фото > Кнопка')
        connection.close()
        self.assertEqual(self.yadro.zapisat({'t': 'other', 'v': 'v', 's': 's', 'e': 'x'}), 'skip')

    def test_report_shows_buttons_and_the_page_block(self):
        self.send([('page', '/video/index.html', ''), ('scroll', '/video/index.html', '50'),
                   ('scroll', '/video/index.html', '100'), ('whatsapp', '/video/index.html', 'WhatsApp'),
                   ('page', '/video/index.html', ''), ('knopka', '/video/index.html', 'Розрахувати кредит'),
                   ('card', '/video/UA-0013.html', ''), ('foto', '/video/UA-0013.html', ''),
                   ('scroll', '/video/UA-0013.html', '50'), ('diag', '/video/UA-0013.html', 'Діагностика')])
        report = self.otchet.otchet('today')
        self.assertIn('Кнопка «Розрахувати кредит» — 1', report)
        self.assertIn('Фото — 1', report)
        self.assertNotIn('scroll', report)
        block = report[report.index('📜 <b>СТРАНИЦЫ: ДОЧИТАЛИ И НАЖИМАЛИ</b>'):report.index('🔥')].strip().split('\n')
        self.assertEqual(block[1:], [
            'Главная — 2 просмотра', '  дочитали: до середины 50% · до конца 50%',
            '  нажимали: WhatsApp 1 · Кнопка «Розрахувати кредит» 1',
            'UA-0013 — 1 просмотр', '  дочитали: до середины 100% · до конца 0%',
            '  нажимали: Диагностика 1 · Фото 1'])

    def test_no_block_before_depth_data_and_report_survives_a_broken_module(self):
        self.send([('page', '/video/index.html', ''), ('whatsapp', '/video/index.html', 'WhatsApp')])
        self.assertNotIn('📜', self.otchet.otchet('today'))
        sys.modules['ua_page_depth'] = None
        self.addCleanup(sys.modules.pop, 'ua_page_depth', None)
        self.assertIn('ЧТО НАЖИМАЛИ', self.otchet.otchet('today'))

    def test_block_numbers(self):
        events = [{'tip': 'page', 'adres': 'a', 'z': ''}] * 3 + [{'tip': 'scroll', 'adres': 'a', 'z': '100'}] * 5
        lines = ua_page_depth.stroki(events, lambda adres: adres, lambda s: None, ('start',))
        self.assertEqual(lines[2:], ['a — 3 просмотра', '  дочитали: до середины 0% · до конца 100%'])


if __name__ == '__main__':
    unittest.main()
