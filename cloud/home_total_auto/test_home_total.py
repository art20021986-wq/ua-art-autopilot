import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import home_total as total

OLD = Path(__file__).resolve().parents[1] / "task_093_home_stage_counter_sync/home_counter_guard.py"
spec = importlib.util.spec_from_file_location("legacy_home_guard", OLD)
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


def home():
    return ('<!doctype html><html lang="uk"><body><p>Protected VIN and specification link</p>'
            '<a class="stage-card" data-stage="sea" data-count="8"><em>8 автомобилей</em></a>'
            '<a class="outline-cta" href="katalog.html"><i data-ru="Открыть все автомобили · 16" '
            'data-uk="Відкрити всі автомобілі · 16">Відкрити всі автомобілі · 16</i></a>'
            + legacy.DYNAMIC_SCRIPT + '</body></html>')


def catalog(numbers, stage="unknown"):
    return '<html><body><div class="catalog-grid">' + ''.join(
        '<article class="catalog-card"><a href="UA-%04d.html">Photo</a>'
        '<div data-ua-card="UA-%04d" data-category="%s"></div></article>' % (n, n, stage)
        for n in numbers) + '</div></body></html>'


class HomeTotalTests(unittest.TestCase):
    def test_published_catalog_18_to_19_to_18_and_duplicates(self):
        self.assertEqual(len(total.catalog_ids(catalog(range(1, 19)), "uaart.com.ua")), 18)
        self.assertEqual(len(total.catalog_ids(catalog(range(1, 20)), "uaart.com.ua")), 19)
        self.assertEqual(len(total.catalog_ids(catalog(list(range(1, 19)) + [17, 18]), "uaart.com.ua")), 18)

    def test_real_renderer_formats_and_missing_stage_are_counted(self):
        source = '<html><body><div class="catalog-grid">' \
                 '<article class="catalog-card" data-ua="UA-0017"></article>' \
                 '<article class="catalog-card"><a href="UA-0018.html">Open</a></article>' \
                 '</div><a href="UA-0999.html">Unrelated navigation</a></body></html>'
        self.assertEqual(total.catalog_ids(source, "uaart.com.ua"), ("UA-0017", "UA-0018"))

    def test_missing_conflicting_or_external_only_card_identity_fails(self):
        for card in ('<article class="catalog-card"></article>',
                     '<article class="catalog-card" data-ua="UA-0017"><a href="UA-0018.html">X</a></article>',
                     '<article class="catalog-card"><a href="https://other.example/UA-0017.html">X</a></article>'):
            with self.subTest(card=card), self.assertRaises(total.TotalError):
                total.catalog_ids('<html><body><div class="catalog-grid">' + card + '</div></body></html>', "uaart.com.ua")

    def test_empty_catalog_distinct_from_error_or_truncated_page(self):
        self.assertEqual(total.catalog_ids(catalog([]), "uaart.com.ua"), ())
        for source in ('<html><body>Error</body></html>', catalog(range(1, 19))[:-7]):
            with self.assertRaises(total.TotalError):
                total.catalog_ids(source, "uaart.com.ua")

    def test_patch_changes_only_total_fragment_and_its_writer(self):
        before = home()
        after = total.patch_home_total(before, 18)
        self.assertIn('data-uk="Відкрити всі автомобілі · 18"', after)
        self.assertIn('>Відкрити всі автомобілі · 18</i>', after)
        self.assertIn('data-ru="Открыть все автомобили · 18"', after)
        self.assertEqual(after, total.patch_home_total(after, 18))
        normalized = re.sub(re.escape(total.START) + r'.*?' + re.escape(total.END) + r'\n', '', after, flags=re.S)
        normalized = normalized.replace(total.OWNED_WRITE, total.OLD_WRITE)
        normalized = total.CTA_RE.sub(lambda _: total.CTA_RE.search(before).group(), normalized)
        self.assertEqual(before, normalized)

    def test_unrecognized_writer_or_duplicate_cta_is_rejected(self):
        with self.assertRaises(total.TotalError):
            total.patch_home_total(home().replace(total.OLD_WRITE, 'if (cta) {'), 18)
        with self.assertRaises(total.TotalError):
            total.patch_home_total(home().replace('</body>', total.CTA_RE.search(home()).group() + '</body>'), 18)

    def test_zero_updates_visible_and_language_attributes(self):
        self.assertIn('>Відкрити всі автомобілі · 0</i>', total.patch_home_total(home(), 0))

    def test_cli_plan_apply_and_stale_preimage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            hp, cp, lock = root / 'index.html', root / 'katalog.html', root / 'publisher.lock'
            hp.write_text(home(), encoding='utf-8')
            cp.write_text(catalog(range(1, 19)), encoding='utf-8')
            lock.touch()
            before = hp.read_bytes()
            cmd = [sys.executable, total.__file__, '--home', str(hp), '--catalog', str(cp),
                   '--catalog-origin', 'uaart.com.ua']
            subprocess.run(cmd, capture_output=True, check=True)
            self.assertEqual(hp.read_bytes(), before)
            apply = cmd + ['--apply', '--lock-file', str(lock), '--expected-home-sha256',
                           hashlib.sha256(before).hexdigest(), '--expected-catalog-sha256',
                           hashlib.sha256(cp.read_bytes()).hexdigest()]
            subprocess.run(apply, capture_output=True, check=True)
            after = hp.read_bytes()
            self.assertIn('· 18'.encode(), after)
            self.assertEqual(next(root.glob('*.bak')).read_bytes(), before)
            self.assertNotEqual(subprocess.run(apply, capture_output=True).returncode, 0)
            self.assertEqual(hp.read_bytes(), after)


if __name__ == '__main__':
    unittest.main(verbosity=2)
