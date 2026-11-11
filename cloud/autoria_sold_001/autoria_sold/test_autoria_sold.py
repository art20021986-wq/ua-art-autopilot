"""The AUTO.RIA figures reader and the weekly job, without network."""
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autoria_sold import job, page  # noqa: E402

# Verbatim fragment of the dealer page (snapshot AUTORIA-REVIEWS-COLLECT-20261026-R2).
LIVE = ('<div id="elementsSoldCarTitle" class="text-template" style=""><!--[--><!--[--><!--[--><span class="common-text '
        'ws-pre-wrap titleL" style="color:var(--contrastPrimary);"><!--[-->132<!--]--></span><!--]--><!--]--><!--]--></div>'
        '<!--]--><!--]--><!--]--><!--[--><!--[--><!--[--><div id="elementsSoldCar" class="text-template" style="">'
        '<!--[--><!--[--><!--[--><span class="common-text ws-pre-wrap footnote" style="color:var(--contrastPrimary);">'
        '<!--[-->Проданих авто<!--]--></span></div>'
        '<div id="elementsWorkWith" class="text-template-builder mt-12 mx-16  horizontal-center" style=""><strong '
        'class="common-text ws-pre-wrap titleS" style="color:var(--contrastPrimary);">5+ років</strong><span class="common-text '
        'ws-pre-wrap body" style="color:var(--contrastPrimary);"> працює з AUTO.RIA</span></div>'
        '<label for="tabsIdrevs" class="label"><!--[--><!----><!--[--><!--[--><span class="common-text ws-pre-wrap body" '
        'style="color:var(--contrastPrimary);"><!--[-->Відгуки<!--]--></span><!--]--><!--]--><span class="common-badge '
        'contrast small" style="" data-v-cbadbc86><!--[-->18<!--]--></span><!--]--></label>')
FIGURES = {'years': '5+', 'sold': 132, 'reviews': 18}
MONDAY = datetime(2026, 11, 16, 8, 41, tzinfo=job.KYIV)
TUESDAY = datetime(2026, 11, 17, 8, 41, tzinfo=job.KYIV)


class PageTests(unittest.TestCase):
    def test_live_fragment(self):
        self.assertEqual(page.sold_count(LIVE), 132)

    def test_thousands_with_spaces(self):
        self.assertEqual(page.sold_count('<div id="elementsSoldCarTitle"><span>1 204</span></div>'), 1204)

    def test_missing_or_not_a_number(self):
        for html in ('', '<div id="elementsSoldCar"><span>Проданих авто</span></div>',
                     '<div id="elementsSoldCarTitle"><span>—</span></div>',
                     '<div id="elementsSoldCarTitle"><span>0</span></div>',
                     '<div id="elementsSoldCarTitle"><span>132+</span></div>'):
            self.assertIsNone(page.sold_count(html))

    def test_years_and_reviews_from_the_live_fragment(self):
        self.assertEqual(page.figures(LIVE), FIGURES)
        self.assertEqual(page.years('<div id="elementsWorkWith"><strong>1 рік</strong> працює з AUTO.RIA</div>'), '1')
        self.assertEqual(page.years('<div id="elementsWorkWith"><strong>12 років</strong></div>'), '12')

    def test_unreadable_years_and_reviews(self):
        for html in ('<div id="elementsWorkWith"><strong>давно</strong></div>',
                     '<div id="elementsWorkWith"><strong>0 років</strong></div>',
                     '<label for="tabsIdrevs"><span>Відгуки</span><span class="common-badge">—</span></label>',
                     '<label for="tabsIdads"><span class="common-badge">1</span></label>'):
            self.assertEqual(page.figures(html), {})


class JobTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.out = Path(directory.name) / 'video/brand/autoria-sold.json'
        self.calls = []

    def run_job(self, now, html=LIVE, robots=True):
        def get(url):
            self.calls.append(url)
            return html
        return job.main(now, self.out, get, lambda url: robots)

    def test_monday_writes_the_figures(self):
        self.assertEqual(self.run_job(MONDAY), 0)
        self.assertEqual(json.loads(self.out.read_text()), {**FIGURES, 'checked': '2026-11-16'})
        self.assertEqual(self.calls, [job.DEALER_URL])

    def test_other_days_do_nothing_once_the_file_exists(self):
        self.run_job(MONDAY)
        self.calls.clear()
        self.assertEqual(self.run_job(TUESDAY, html='<div id="elementsSoldCarTitle">140</div>'), 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(json.loads(self.out.read_text())['sold'], 132)

    def test_missing_file_is_built_on_any_day(self):
        self.assertEqual(self.run_job(TUESDAY), 0)
        self.assertEqual(json.loads(self.out.read_text())['sold'], 132)

    def test_unreadable_page_keeps_the_last_number(self):
        self.run_job(MONDAY)
        self.assertEqual(self.run_job(MONDAY, html='<html>changed design</html>'), 1)
        self.assertEqual(json.loads(self.out.read_text())['sold'], 132)

    def test_unread_figure_keeps_its_last_value(self):
        self.run_job(MONDAY)
        self.assertEqual(self.run_job(MONDAY, html='<div id="elementsSoldCarTitle">140</div>'), 0)
        self.assertEqual(json.loads(self.out.read_text()), {**FIGURES, 'sold': 140, 'checked': '2026-11-16'})

    def test_file_without_a_figure_is_completed_on_any_day(self):
        # The file written by the first version holds only "sold".
        self.out.parent.mkdir(parents=True)
        self.out.write_text('{"sold": 136, "checked": "2026-11-11"}')
        self.assertEqual(self.run_job(TUESDAY), 0)
        self.assertEqual(json.loads(self.out.read_text()), {**FIGURES, 'checked': '2026-11-17'})

    def test_robots_refusal_reads_nothing(self):
        self.assertEqual(self.run_job(MONDAY, robots=False), 1)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
