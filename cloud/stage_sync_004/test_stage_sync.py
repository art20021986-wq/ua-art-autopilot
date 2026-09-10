import contextlib
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import ua_stage_catalog_sync as sync


def article(code, stage=2):
    category, inner, ru, uk = sync.STAGES[stage]
    return (f'<article class="catalog-card" data-stage="{category}" data-ua-stage="{stage}">'
            f'<a class="catalog-photo" href="{code}.html"><img src="foto/{code}/one.jpg"></a>'
            '<h2>Original car 4289</h2><b>12 345 $</b>'
            f'<div class="status-pill" style="white-space:pre-line" data-ru="{ru} · маршрут — Киев" '
            f'data-uk="{uk} · маршрут — Київ">{ru} · маршрут — Киев</div>'
            f'<div class="ua-cat-vin-v1" data-ua-card="{code}" data-ua-stage-tile="{stage}" '
            f'data-category="{inner}"><div class="ua-cat-vin-v1-top">VIN <b>KMHE341DBKA544289</b></div>'
            '<div class="ua-cat-vin-v1-copy">18 дней до Киева</div></div>'
            f'<a href="{code}-spec.html">Дополнительная спецификация</a></article>')


def page(articles):
    return '<html lang="uk"><body><div class="catalog-grid">' + articles + '</div></body></html>'


def mask_dynamic(source):
    source = re.sub(r'(data-(?:stage|ua-stage|ua-stage-tile|category)\s*=\s*")[^"]*"', r'\1#"', source)
    return re.sub(r'В Корее|У Кореї|На пароме|На поромі|В Грузии|У Грузії|В Киеве|У Києві', '#', source)


class PureTests(unittest.TestCase):
    def setUp(self):
        self.codes = ['UA-0009', 'UA-0010', 'UA-0011', 'UA-0012']
        self.rows = {code: {'auto_number': code, 'status': 'ge_waiting'} for code in self.codes}

    def test_four_moves_and_byte_scope(self):
        original = page(''.join(article(code) for code in self.codes))
        changed, ids = sync.patch_catalog_stages(original, self.rows)
        self.assertEqual(ids, self.codes)
        self.assertEqual(changed.count('data-stage="georgia"'), 4)
        self.assertEqual(changed.count('data-category="gruzia"'), 4)
        self.assertEqual(changed.count('data-ua-stage-tile="3"'), 4)
        self.assertEqual(changed.count('data-uk="У Грузії · маршрут — Київ"'), 4)
        self.assertEqual(mask_dynamic(original), mask_dynamic(changed))
        self.assertEqual(changed.count('18 дней до Киева'), 4)

    def test_repeating_event_is_noop(self):
        original = page(''.join(article(code) for code in self.codes))
        once, _ = sync.patch_catalog_stages(original, self.rows)
        twice, ids = sync.patch_catalog_stages(once, self.rows)
        self.assertEqual((twice, ids), (once, []))

    def test_unknown_stage_fails(self):
        self.rows['UA-0009']['status'] = 'unknown'
        with self.assertRaisesRegex(sync.StageSyncError, 'UNKNOWN_STAGE'):
            sync.patch_catalog_stages(page(''.join(article(code) for code in self.codes)), self.rows)

    def test_duplicate_or_unpublished_card_fails(self):
        source = page(''.join(article(code) for code in self.codes) + article('UA-0019'))
        with self.assertRaisesRegex(sync.StageSyncError, 'CATALOG_ID:UA-0019'):
            sync.patch_catalog_stages(source, self.rows)
        source = page(''.join(article(code) for code in self.codes) + article('UA-0009'))
        with self.assertRaisesRegex(sync.StageSyncError, 'CATALOG_ID:UA-0009'):
            sync.patch_catalog_stages(source, self.rows)

    def test_existing_special_statuses(self):
        for status, expected in [('sold_transit', 2), ('ge_to_kyiv', 3), ('ua_arrived', 4), ('kr_bought', 1)]:
            self.assertEqual(sync.stage_of({'status': status}), expected)


class StubCounter:
    @staticmethod
    def catalog_snapshot(source):
        records = {}
        for block in re.findall(r'<article\b.*?</article>', source, re.S):
            code = re.search(r'data-ua-card="([^"]+)"', block)[1]
            stage = re.search(r'data-stage="([^"]+)"', block)[1]
            inner = re.search(r'data-category="([^"]+)"', block)[1]
            if sync.ALIASES[inner] != stage:
                raise ValueError('inconsistent stages')
            records[code] = stage
        counts = {'all': len(records), 'kiev': 0, 'georgia': 0, 'sea': 0, 'korea': 0}
        for stage in records.values():
            counts[stage] += 1
        return records, counts

    @staticmethod
    def patch_catalog(source, counts):
        return source

    @staticmethod
    def patch_home(source, counts):
        return 'stage-card outline-cta home counts: ' + repr(counts)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.roots = (self.root / 'video', self.root / 'site')
        self.rows = {'UA-0009': {'auto_number': 'UA-0009', 'status': 'ge_waiting'}}
        self.writes, self.fail_after, self.failed = 0, None, False
        for root in self.roots:
            root.mkdir()
            (root / 'katalog.html').write_text(page(article('UA-0009')))
            (root / 'index.html').write_text('stage-card outline-cta home old')
            (root / 'UA-0009.html').write_text('<section data-ua-stage-current="3">preserved</section>')
            (root / 'UA-0009-spec.html').write_text('spec untouched')
        self.before = {path: path.read_bytes() for root in self.roots for path in root.iterdir()}
        self.pub = types.SimpleNamespace(ROOT=self.root, ROOTS=self.roots,
            _row_map=lambda: (self.rows, 'digest'), _stage=sync.stage_of,
            _exclusive_lock=contextlib.nullcontext, _atomic=self.atomic,
            _validate_catalog=lambda source, rows: {})
        self.modules = patch.dict(sys.modules, {'publish_transaction_guard': self.pub, 'ua_site_counters': StubCounter})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def atomic(self, path, data, mode):
        if path.parent in self.roots:
            self.writes += 1
            if self.fail_after == self.writes and not self.failed:
                self.failed = True
                raise OSError('injected write failure')
        path.write_bytes(data)

    def test_check_is_read_only_then_apply_noop(self):
        result = sync.reconcile()
        self.assertEqual(result['status'], 'CHECKED')
        self.assertEqual(self.writes, 0)
        self.assertFalse((self.root / 'backups').exists())
        self.assertEqual(sync.reconcile(apply=True)['status'], 'APPLIED')
        writes = self.writes
        self.assertEqual(sync.reconcile(apply=True)['status'], 'NOOP')
        self.assertEqual(self.writes, writes)
        for path, before in self.before.items():
            if path.name.startswith('UA-'):
                self.assertEqual(path.read_bytes(), before)

    def test_failure_restores_only_changed_html(self):
        self.fail_after = 3
        with self.assertRaisesRegex(OSError, 'injected write failure'):
            sync.reconcile(apply=True)
        for path, before in self.before.items():
            self.assertEqual(path.read_bytes(), before)

    def test_redirect_index_is_preserved(self):
        redirect = self.roots[1] / 'index.html'
        original = '<html><head><meta http-equiv="refresh" content="0; url=/video/index.html"></head></html>'
        redirect.write_text(original)
        result = sync.reconcile(apply=True)
        self.assertEqual(result['status'], 'APPLIED')
        self.assertEqual(result['home_paths'], [str(self.roots[0] / 'index.html')])
        self.assertNotIn(str(redirect), result['files'])
        self.assertEqual(redirect.read_text(), original)
        self.assertEqual(sync.reconcile(apply=True)['status'], 'NOOP')

    def test_missing_home_counter_surface_fails_without_writes(self):
        for root in self.roots:
            (root / 'index.html').write_text('<html>redirect</html>')
        with self.assertRaisesRegex(sync.StageSyncError, 'HOMEPAGE_COUNTER_SURFACE_MISSING'):
            sync.reconcile(apply=True)
        self.assertEqual(self.writes, 0)

    def test_primary_not_ready_prevents_all_writes(self):
        (self.roots[0] / 'UA-0009.html').write_text('<section data-ua-stage-current="2">unchanged</section>')
        with self.assertRaisesRegex(sync.StageSyncError, 'PRIMARY_STAGE_NOT_READY'):
            sync.reconcile(apply=True)
        self.assertEqual(self.writes, 0)

    def test_newer_crm_change_rolls_back_html(self):
        calls = 0
        def row_map():
            nonlocal calls
            calls += 1
            return self.rows, 'digest' if calls < 3 else 'newer'
        self.pub._row_map = row_map
        with self.assertRaisesRegex(sync.StageSyncError, 'CRM_CHANGED_DURING_INSTALL'):
            sync.reconcile(apply=True)
        for path, before in self.before.items():
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
