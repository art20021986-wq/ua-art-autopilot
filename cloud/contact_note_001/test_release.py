"""The CONTACT-NOTE candidate from the live Korea page, the order strings and the page writers."""
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder as builder  # noqa: E402

FIXTURES = {'video/korea.html': 'korea_live.html', 'video/order/order-strings.json': 'order-strings.json',
            'ua_card_contact.py': 'ua_card_contact.txt', 'ua_seo_quick_form.py': 'ua_seo_quick_form.txt'}


def source():
    return {name: (HERE / 'fixtures' / fixture).read_bytes() for name, fixture in FIXTURES.items()}


class CandidateTests(unittest.TestCase):
    def test_only_the_sentences_change(self):
        old = source()
        new = builder.build(old, {})
        self.assertEqual(set(new), set(old))
        for name, value in new.items():
            text = value.decode()
            self.assertFalse(builder.carries(text), name)
            self.assertEqual(builder.undo(text).encode(), old[name], name)
            if name.endswith('.py'):
                compile(value, name, 'exec')
        page = new['video/korea.html'].decode()
        self.assertIn('data-uk="Менеджер зв’яжеться з вами."', page)
        self.assertIn('data-ru="Менеджер свяжется с вами."', page)
        self.assertIn('data-ka="მენეჯერი დაგიკავშირდებათ."', page)
        self.assertIn('header-telegram', page)  # the header contact line stays
        self.assertIn('прийнято. Менеджер зв’яжеться з вами.', new['video/order/order-strings.json'].decode())

    def test_second_build_refused(self):
        with self.assertRaises(ValueError):
            builder.build(builder.build(source(), {}), {})

    def test_targets_find_only_the_carriers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, value in source().items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes(value)
            for name in ('video/seo/a/b/index.html', 'deployment_x.py', 'test_x.py'):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_bytes(source()['video/korea.html'])
            (root / 'video/index.html').write_text('<html>Telegram</html>')
            (root / 'link.html').symlink_to(root / 'video/korea.html')
            self.assertEqual(builder.targets(root), tuple(sorted(set(FIXTURES) | {'video/seo/a/b/index.html'})))

    def test_pages_and_webapp(self):
        self.assertTrue(builder.is_page('video/korea.html'))
        self.assertFalse(builder.is_page('catalog_design_golden.html'))
        self.assertTrue(builder.webapp(['ua_order/auction.py']))
        self.assertFalse(builder.webapp(['ua_card_contact.py', 'video/korea.html']))


if __name__ == '__main__':
    unittest.main()
