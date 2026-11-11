"""Step 1 on the home page: only the first step and one CSS block change, three languages, valid structure."""
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import edit_home  # noqa: E402
from release_constants import HOME  # noqa: E402

# Live home page read by LEAD-DESK-PROBE-20261105-R5 (sanitized: foreign links and long numbers masked).
LIVE = json.loads((HERE.parent / 'lead_desk_probe_001' / '20261105-R5.json').read_text())['files'][HOME]['source']


class Texts(HTMLParser):
    """Every element with data-ru must hold exactly one text node equal to its data-uk (site language script)."""

    def __init__(self):
        super().__init__()
        self.stack, self.bad, self.found = [], [], []

    def handle_starttag(self, tag, attrs):
        self.stack.append([tag, dict(attrs), []])

    def handle_data(self, data):
        if self.stack:
            self.stack[-1][2].append(data)

    def handle_endtag(self, tag):
        name, attrs, texts = self.stack.pop()
        if 'data-ru' in attrs:
            self.found.append(attrs)
            if texts != [attrs['data-uk']] or not attrs.get('data-ka'):
                self.bad.append((name, attrs, texts))
        elif self.stack:
            self.stack[-1][2].append('<child>')


class EditHomeTests(unittest.TestCase):
    def test_only_step_one_and_css_change(self):
        result = edit_home.build(LIVE.encode()).decode()
        self.assertEqual(result.replace(edit_home.CSS, '', 1).replace(edit_home.step(), edit_home.OLD_STEP, 1), LIVE)
        self.assertLess(result.index(edit_home.CSS), result.index('</head>'))
        self.assertIn(edit_home.CHECK, result)
        self.assertEqual(result.count('<li><i>2</i>'), 1)

    def test_texts_switch_by_language(self):
        parser = Texts()
        parser.feed(edit_home.step())
        self.assertEqual(parser.bad, [])
        self.assertEqual(len(parser.found), 9)  # title, short, «more», 4 lines, payment, button
        self.assertEqual(parser.stack, [])

    def test_owner_wording(self):
        step = edit_home.step()
        for text in ('Безкоштовна консультація', '3 робочі дні', 'до 200 $', 'Оплата на цьому кроці: 0 грн',
                     'не договір', 'href="podbor.html"', 'Заповнити заявку', 'Бесплатная консультация',
                     'უფასო კონსულტაცია'):
            self.assertIn(text, step)

    def test_release_two_changes_only_the_price_range(self):
        new = edit_home.build(LIVE.encode()).decode()
        old_p, new_p = edit_home._text('p', edit_home.OLD_PRICE), edit_home._text('p', edit_home.LINES[2])
        release_one = new.replace(new_p, old_p, 1)
        self.assertIn('до 1000 $', release_one)
        result = edit_home.build(release_one.encode()).decode()
        self.assertEqual(result, new)
        self.assertEqual(result.replace(new_p, old_p, 1), release_one)
        self.assertNotIn('1000 $', result)
        for text in ('отличаться до 200 $', 'відрізнятися до 200 $', '200 $-მდე'):
            self.assertIn(text, result)
        self.assertIn(edit_home.CHECK, result)

    def test_refuses_second_run_and_missing_anchor(self):
        once = edit_home.build(LIVE.encode())
        with self.assertRaises(ValueError):
            edit_home.build(once)
        with self.assertRaises(ValueError):
            edit_home.build(LIVE.replace('<li><i>1</i>', '<li><i>01</i>').encode())

    def test_builder_changes_only_the_home_page(self):
        self.assertEqual(list(candidate_builder.build({HOME: LIVE.encode()}, {})), [HOME])

    def test_readable_and_accessible(self):
        self.assertIn('font-size:16px', edit_home.CSS)
        self.assertIn('min-height:44px', edit_home.CSS)
        self.assertIn('summary:focus-visible', edit_home.CSS)


if __name__ == '__main__':
    unittest.main()
