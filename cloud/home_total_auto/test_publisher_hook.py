from pathlib import Path
import tempfile
import unittest

from publisher_hook import patch_publisher

SOURCE = (Path(__file__).resolve().parents[1] /
          'task_083_publish_transaction/publish_transaction_guard.py').read_text()


def module(source, root):
    namespace = {}
    exec(compile(source, '<publisher fixture>', 'exec'), namespace)
    namespace.update(ROOT=root, VIDEO=root/'video', SITE=root/'site',
                     ROOTS=(root/'video', root/'site'),
                     BACKUPS=root/'backups', LOCK=root/'writer.lock')
    return namespace


class PublisherHookTests(unittest.TestCase):
    def test_historical_snapshot_does_not_delete_homepages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('video', 'site'):
                (root/name).mkdir()
                (root/name/'index.html').write_text('home stays')
                (root/name/'katalog.html').write_text('old catalogue')
            old = module(SOURCE, root)
            snapshot = old['Snapshot']([])
            new = module(patch_publisher(SOURCE), root)
            for folder in new['ROOTS']:
                (folder/'katalog.html').write_text('changed catalogue')
            new['rollback_backup'](str(snapshot.root), [])
            for folder in new['ROOTS']:
                self.assertEqual((folder/'index.html').read_text(), 'home stays')
                self.assertEqual((folder/'katalog.html').read_text(), 'old catalogue')

    def test_new_snapshot_restores_homepages_with_catalogue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('video', 'site'):
                (root/name).mkdir()
                (root/name/'index.html').write_text('home 18')
                (root/name/'katalog.html').write_text('catalogue 18')
            new = module(patch_publisher(SOURCE), root)
            snapshot = new['Snapshot']([])
            for folder in new['ROOTS']:
                (folder/'index.html').write_text('home 19')
                (folder/'katalog.html').write_text('catalogue 19')
            snapshot.restore()
            for folder in new['ROOTS']:
                self.assertEqual((folder/'index.html').read_text(), 'home 18')
                self.assertEqual((folder/'katalog.html').read_text(), 'catalogue 18')

    def test_patch_is_idempotent_and_rejects_unknown_anchor(self):
        candidate = patch_publisher(SOURCE)
        self.assertEqual(patch_publisher(candidate), candidate)
        with self.assertRaises(ValueError):
            patch_publisher(SOURCE.replace('"candidate": before', '"candidate": changed'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
