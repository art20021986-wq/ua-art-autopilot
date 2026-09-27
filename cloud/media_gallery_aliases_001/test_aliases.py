"""Prove the missing public-URL inventory and the prerequisite installed renderer."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_candidate as build
import deployment_remote as remote


class AliasScopeTests(unittest.TestCase):
    def sources(self):
        return {'stranica.py': b'def sobrat_kartochku():\n    from ua_media_gallery import photos\n',
                **{name: Path(__file__).with_name(name).read_bytes() for name in build.ASSET_NAMES}}

    def test_installed_renderer_produces_no_application_changes(self):
        self.assertEqual(build.build(self.sources()), {})
        self.assertEqual(build.MODULES, ())

    def test_uninstalled_or_different_gallery_is_rejected(self):
        sources = self.sources()
        sources['stranica.py'] = b'def sobrat_kartochku():\n    pass\n'
        with self.assertRaisesRegex(ValueError, 'MEDIA_RENDERER_NOT_INSTALLED'):
            build.build(sources)
        for name in build.ASSET_NAMES:
            with self.subTest(name=name):
                sources = self.sources()
                sources[name] += b'\n'
                with self.assertRaisesRegex(ValueError, 'INSTALLED_MEDIA_ASSET_MISMATCH'):
                    build.build(sources)

    def test_inventory_contains_saved_public_urls_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('video/UA-0023-956711ae.html', 'site/UA-0023-956711ae.html',
                         'video/UA-0023.html', 'video/UA-0023-diagnostics.html',
                         'video/katalog.html', 'video/UA-0023-956711ae.txt'):
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.write_text('preserve')
            with patch.object(remote, 'ROOT', root):
                self.assertEqual(remote.gallery_paths(),
                                 ['site/UA-0023-956711ae.html', 'video/UA-0023-956711ae.html'])


if __name__ == '__main__':
    unittest.main()
