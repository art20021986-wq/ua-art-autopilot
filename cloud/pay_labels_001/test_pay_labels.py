#!/usr/bin/env python3
"""PAY-LABELS-001: the exact edits, the candidate, preview smoke, install/rollback on real files, public check."""
from contextlib import closing, nullcontext
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import candidate_builder  # noqa: E402
import deployment_controller as controller  # noqa: E402
import deployment_remote as remote  # noqa: E402
from deployment_transport import canonical, sha  # noqa: E402
import pay_labels as p  # noqa: E402


def entry(key, value):
    return json.dumps(key, ensure_ascii=False) + ':' + json.dumps(value, ensure_ascii=False)


def live_like():
    """Each file as it is now, reduced to the lines the release edits (and a neighbour that must not change)."""
    (ru, _), (uk, _), (ka, _) = p.HOME_NOTE['ru'], p.HOME_NOTE['uk'], p.HOME_NOTE['ka']
    (kuk, _), (kru, _) = p.KOREA_FAQ['uk'], p.KOREA_FAQ['ru']
    info = [line[0][0] for line in p.INFO]
    uk_words = ','.join(entry(line[0][0], line[1][0]) for line in p.INFO)
    ka_words = ','.join(entry(line[0][0], line[2][0]) for line in p.INFO)
    return {
        'video/index.html': '<p>Оплата: послуга — 600 $</p><p class="ua-kr-note" data-ru="%s" data-uk="%s" data-ka="%s">%s</p>'
                            % (ru, uk, ka, uk),
        'video/korea.html': '<h3>Скільки передоплата?</h3><p><span data-uk="%s" data-ru="%s">%s</span></p>' % (kuk, kru, kuk),
        'video/info.html': ''.join('<div>%s</div>' % line for line in info) + '<div>Сертификация</div>',
        'stranica.py': ''.join('c.append("%s" %% BRON_USD)\n' % line.replace('500 $', '%d $') for line in info),
        'video/ua-site-languages.js': '(function(){var dictionaries = {"ru":{},"uk":{%s,"Да":"Так"},"ka":{%s}};})();'
                                      % (uk_words, ka_words),
    }


class EditTests(unittest.TestCase):
    def test_every_file_gets_its_new_texts_once(self):
        for name, text in live_like().items():
            new = p.apply(name, text)
            self.assertTrue(p.has_labels(name, new), name)
            self.assertFalse(p.has_labels(name, text), name)
            with self.assertRaisesRegex(ValueError, 'PAY_LABELS_FRAGMENT'):
                p.apply(name, new)  # never twice

    def test_sums_do_not_change_and_neighbours_stay(self):
        files = live_like()
        home = p.apply('video/index.html', files['video/index.html'])
        self.assertTrue(home.startswith('<p>Оплата: послуга — 600 $</p>'))
        self.assertIn('data-ka="წინასწარი გადახდა 1 000 $ ჩაითვლება ავტომობილის ღირებულებაში. ეს თანხები', home)
        self.assertIn('>Передоплата 1 000 $ зараховується у вартість авто. Ці суми — для купівлі з аукціону. '
                      'Для авто в наявності чи в дорозі передоплата — 500 $.</p>', home)
        info = p.apply('video/info.html', files['video/info.html'])
        self.assertTrue(info.endswith('<div>Сертификация</div>'))
        source = p.apply('stranica.py', files['stranica.py'])
        self.assertIn('"Предоплата %d $ за автомобиль в наличии или в пути входит в его стоимость" % BRON_USD', source)
        self.assertEqual(source.count('% BRON_USD'), 3)

    def test_dictionary_maps_the_new_conditions_lines(self):
        script = p.apply('video/ua-site-languages.js', live_like()['video/ua-site-languages.js'])
        start = script.index('var dictionaries = ') + len('var dictionaries = ')
        words = json.JSONDecoder().raw_decode(script[start:])[0]
        for (ru, uk, ka) in p.INFO:
            self.assertEqual(words['uk'][ru[1]], uk[1])
            self.assertEqual(words['ka'][ru[1]], ka[1])
            self.assertNotIn(ru[0], words['uk'] if ru[0] != ru[1] else {})
        self.assertEqual(words['uk']['Да'], 'Так')

    def test_fragment_missing_or_doubled_is_refused(self):
        text = live_like()['video/korea.html']
        with self.assertRaisesRegex(ValueError, 'PAY_LABELS_FRAGMENT:video/korea.html:2'):
            p.apply('video/korea.html', text + text)
        with self.assertRaisesRegex(ValueError, 'PAY_LABELS_FRAGMENT:video/korea.html:0'):
            p.apply('video/korea.html', '<p>other</p>')


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name, text in live_like().items():
            (self.root/name).parent.mkdir(parents=True, exist_ok=True)
            (self.root/name).write_text(text, encoding='utf-8')
        (self.root/'video/katalog.html').write_text('<p>catalogue</p>', encoding='utf-8')
        for name in ('start_safe.py', 'run_all.py', 'team_bot.py', 'lead_bot.py', 'db.py', 'publication_fence.py',
                     'ua_public_freshness.py', 'ua_site_counters.py', 'catalog_design_guard.py', 'cars_schema.py',
                     'master_card.py', 'publish_transaction_guard.py'):
            (self.root/name).write_text('# ' + name, encoding='utf-8')
        with closing(sqlite3.connect(self.root/'crm.db')) as connection:
            connection.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY, vin TEXT)')
            connection.execute("INSERT INTO cars VALUES(1,'VIN-PRESERVED')")
            connection.commit()
        patcher = patch.object(remote, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.events = []

    def lifecycle(self, mode, saved, plan):
        outer = self

        class FakeAPI:
            enabled = True

            def __init__(self, token):
                pass

            def bot(self):
                return {'enabled': FakeAPI.enabled, 'state': 'running' if FakeAPI.enabled else 'stopped'}

            def set_bot(self, enabled):
                FakeAPI.enabled = enabled
                outer.events.append(enabled)
                return self.bot()
        manifest = {'plan': plan, 'plan_sha256': sha(canonical(plan)), 'run_id': '1'}
        with patch.object(remote, 'API', FakeAPI), patch.object(remote, 'load_backup', return_value=(saved, manifest)), \
                patch.object(remote, 'writer_exclusion', side_effect=nullcontext), \
                patch.object(remote, 'no_bot_processes'):
            return remote.lifecycle(mode, '1', manifest['plan_sha256'], 'a' * 64)

    def test_preview_plans_all_five_files_and_smoke_passes(self):
        saved = self.root/'run'
        plan = remote.prepare(saved)
        self.assertEqual(sorted(plan['files']), sorted(p.FILES))
        self.assertNotIn('stranica.py', plan['protected'])
        self.assertEqual(remote.smoke(saved), {'files': sorted(p.FILES), 'labels': 'PASS', 'dictionary_lines': 6})

    def test_install_then_rollback_on_real_files(self):
        before = {n: (self.root/n).read_bytes() for n in p.FILES}
        saved = self.root/'run'
        plan = remote.prepare(saved)
        result = self.lifecycle('install', saved, plan)
        self.assertTrue(result['installed'], result)
        self.assertTrue(all(p.has_labels(n, (self.root/n).read_text(encoding='utf-8')) for n in p.FILES))
        self.assertEqual((self.root/'video/katalog.html').read_text(encoding='utf-8'), '<p>catalogue</p>')
        result = self.lifecycle('rollback', saved, plan)
        self.assertTrue(result['restored'], result)
        self.assertEqual({n: (self.root/n).read_bytes() for n in p.FILES}, before)
        self.assertEqual(self.events, [False, True, False, True])

    def test_page_rewritten_after_install_is_accepted_when_it_keeps_the_texts(self):
        saved = self.root/'run'
        plan = remote.prepare(saved)
        self.lifecycle('install', saved, plan)
        home = self.root/'video/index.html'
        home.write_text(home.read_text(encoding='utf-8') + '<!-- counter 2 -->', encoding='utf-8')
        remote.verify_files(plan, True)
        home.write_text(live_like()['video/index.html'], encoding='utf-8')
        with self.assertRaisesRegex(remote.DeploymentError, 'FILE_CHANGED:video/index.html'):
            remote.verify_files(plan, True)

    def test_source_edited_by_someone_else_is_refused_before_any_write(self):
        saved = self.root/'run'
        plan = remote.prepare(saved)
        (self.root/'stranica.py').write_text('# other editor', encoding='utf-8')
        result = self.lifecycle('install', saved, plan)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(live_like()['video/korea.html'], (self.root/'video/korea.html').read_text(encoding='utf-8'))
        self.assertEqual(self.events, [False, True])


class PublicVerifyTests(unittest.TestCase):
    def page(self, ru_korea_ready):
        def fetch(url, path):
            texts = controller.EXPECTED[path]
            if path == '/video/ru/korea.html' and not ru_korea_ready():
                texts = ['old Russian page']
            return 'x' * 200 + ' '.join(texts)
        return fetch

    def test_waits_for_the_russian_korea_page(self):
        calls = []
        result = controller.public_verify(fetch=self.page(lambda: len(calls) > 0),
                                          sleep=lambda s: calls.append(s), clock=lambda: 0)
        self.assertEqual(set(result.values()), {'PASS'})
        self.assertEqual(calls, [20])

    def test_missing_text_fails_after_the_wait(self):
        times = iter([0, 10**6])
        with self.assertRaisesRegex(RuntimeError, 'PUBLIC_CHANGE_MISSING:/video/ru/korea.html'):
            controller.public_verify(fetch=self.page(lambda: False), sleep=lambda s: None, clock=lambda: next(times))


if __name__ == '__main__':
    unittest.main()
