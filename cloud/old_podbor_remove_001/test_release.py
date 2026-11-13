#!/usr/bin/env python3
"""OLD-PODBOR-REMOVE-001: the candidate removes only the recognised old page; the preview smoke on a temporary
server root; install-style removal and rollback restore the page."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import deployment_remote as remote  # noqa: E402

OLD = ('<html><head><title>Індивідуальне замовлення автомобіля — UA ART COMPANY</title></head><body>'
       '<h1>Індивідуальне замовлення автомобіля</h1><p>Форма тимчасово недоступна. Телефон: +380 99 222 20 02.</p>'
       '</body></html>').encode()
PROTECTED = ('start_safe.py', 'run_all.py', 'team_bot.py', 'lead_bot.py', 'db.py', 'publication_fence.py',
             'ua_public_freshness.py', 'ua_site_counters.py', 'catalog_design_guard.py', 'cars_schema.py',
             'stranica.py', 'master_card.py', 'publish_transaction_guard.py')


def server(links=False):
    root = Path(tempfile.mkdtemp()).resolve()
    pages = {'video/order/podbor.html': OLD, 'video/podbor.html': 'Оберіть країну підбору'.encode(),
             'video/order/order.js': b'js', 'video/index.html': b'<a href="podbor.html">x</a>',
             'video/preview/x.html': b'<a href="order/podbor.html">draft</a>'}
    if links:
        pages['video/katalog.html'] = b'<a href="order/podbor.html">old</a>'
    for name, value in pages.items():
        (root/name).parent.mkdir(parents=True, exist_ok=True)
        (root/name).write_bytes(value)
    for name in PROTECTED:
        (root/name).write_text('# installed\n')
    return root


class CandidateTests(unittest.TestCase):
    def test_only_the_old_page_is_removed(self):
        self.assertEqual(candidate_builder.build({'video/order/podbor.html': OLD}, {}), {'video/order/podbor.html': None})
        self.assertEqual(candidate_builder.targets(Path('/x')), ('video/order/podbor.html',))

    def test_other_content_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'OLD_PAGE_NOT_RECOGNISED'):
            candidate_builder.build({'video/order/podbor.html': 'Оберіть країну підбору'.encode()}, {})


class SmokeTests(unittest.TestCase):
    def test_preview_plans_removal_only(self):
        root = server()
        with patch.object(remote, 'ROOT', root):
            plan = remote.prepare(root/'work')
            value = remote.smoke(root/'work')
        self.assertEqual(plan['files']['video/order/podbor.html']['after'], None)
        self.assertEqual(plan['files']['video/order/podbor.html']['before'], remote.sha(OLD))
        self.assertTrue((root/'work/before/video/order/podbor.html').is_file())
        self.assertFalse((root/'work/after/video/order/podbor.html').exists())
        self.assertEqual(value, {'files': ['video/order/podbor.html'], 'removed': ['video/order/podbor.html'],
                                 'links_to_old_page': [], 'current_order_page': True})
        self.assertTrue(json.loads((root/'work/plan.json').read_bytes())['site_write'])

    def test_a_public_link_stops_the_preview(self):
        root = server(links=True)
        with patch.object(remote, 'ROOT', root):
            remote.prepare(root/'work')
            with self.assertRaisesRegex(remote.DeploymentError, 'SMOKE_RESULT'):
                remote.smoke(root/'work')


class RemovalTests(unittest.TestCase):
    def test_remove_then_rollback_restores(self):
        root = server()
        with patch.object(remote, 'ROOT', root):
            plan = remote.prepare(root/'work')
            remote.verify_files(plan, False)
            (root/'video/order/podbor.html').unlink()
            remote.verify_files(plan, True)
            self.assertTrue((root/'video/order/order.js').is_file())
            remote.restore(root/'work', plan)
            self.assertEqual((root/'video/order/podbor.html').read_bytes(), OLD)

    def test_recreated_page_is_unexpected(self):
        root = server()
        with patch.object(remote, 'ROOT', root):
            plan = remote.prepare(root/'work')
            with self.assertRaisesRegex(remote.DeploymentError, 'UNEXPECTED_FILE'):
                remote.verify_files(plan, True)


if __name__ == '__main__':
    unittest.main()
