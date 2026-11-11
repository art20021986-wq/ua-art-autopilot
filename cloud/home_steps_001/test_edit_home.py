"""Steps 2–5 on the home page: only the steps block and one CSS block change, three languages, prices, switcher."""
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import edit_home  # noqa: E402
import kr_prices  # noqa: E402
import steps_block  # noqa: E402
from release_constants import HOME  # noqa: E402

# Live home page of 2026-11-11 (public page, step 1 with «до 200 $»).
LIVE = (HERE / 'fixtures' / 'index_live.html').read_text()


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
        assert name == tag, (name, tag)
        if 'data-ru' in attrs:
            self.found.append(attrs)
            if texts != [attrs['data-uk']] or not attrs.get('data-ka'):
                self.bad.append((name, attrs, texts))
        elif self.stack:
            self.stack[-1][2].append('<child>')


def block(page):
    start = page.index(edit_home.START)
    return start, page.index('</section>', start) + len('</section>')


class EditHomeTests(unittest.TestCase):
    def setUp(self):
        self.result = edit_home.build(LIVE.encode()).decode()

    def test_only_the_steps_block_and_css_change(self):
        self.assertLess(self.result.index(steps_block.CSS), self.result.index('</head>'))
        result = self.result.replace(steps_block.CSS, '', 1)
        start, end = block(LIVE)
        new_start, new_end = block(result)
        self.assertEqual(new_start, start)
        self.assertEqual(result[:new_start] + result[new_end:], LIVE[:start] + LIVE[end:])
        inside = result[new_start:new_end]
        for piece in (steps_block.switcher(), steps_block.intro(), steps_block.korea_steps(), steps_block.other_note(),
                      steps_block.signature(), steps_block.SWITCH_SCRIPT, kr_prices.SCRIPT):
            self.assertEqual(inside.count(piece), 1)
            inside = inside.replace(piece, '', 1)
        for number in (2, 3, 4, 5):
            inside = inside.replace(edit_home.HIDDEN % number, '<li><i>%d</i>' % number, 1)
        self.assertEqual(inside, LIVE[start:end])
        self.assertIn(edit_home.CHECK, self.result)

    def test_step_one_and_other_countries_steps_stay(self):
        start, end = block(LIVE)
        self.assertIn(LIVE[LIVE.index('<li class="ua-step-free">', start):LIVE.index('<li><i>2</i>', start)],
                      self.result)
        for number in (2, 3, 4, 5):
            self.assertEqual(self.result.count(edit_home.HIDDEN % number), 1)
        self.assertIn('data-ua-for="other" hidden><p', self.result)

    def test_texts_switch_by_language_and_markup_is_valid(self):
        parser = Texts()
        start, end = block(self.result)
        parser.feed(self.result[start:end])
        self.assertEqual(parser.bad, [])
        self.assertGreater(len(parser.found), 80)
        self.assertEqual(parser.stack, [])

    def test_korea_first_and_eight_countries(self):
        switch = steps_block.switcher()
        self.assertEqual(switch.count('<button type="button" data-ua-country='), 8)
        self.assertTrue(switch.split('<button', 2)[1].startswith(' type="button" data-ua-country="korea" '
                                                                   'aria-pressed="true"'))
        self.assertEqual(switch.count('aria-pressed="true"'), 1)

    def test_prices_add_up(self):
        self.assertEqual(kr_prices.total(kr_prices.DEFAULTS), 3450)
        self.assertEqual(kr_prices.per_car(kr_prices.DEFAULTS), 1200)
        steps = steps_block.korea_steps()
        for key, shown in (('total', '3 450'), ('container', '4 800'), ('car_container', '1 200'),
                           ('fob', '600'), ('port', '250'), ('truck', '1 100'), ('broker', '150'),
                           ('cert', '150'), ('month', '11.2026')):
            self.assertIn('%s="%s">%s</span>' % (kr_prices.ATTR, key, shown), steps)
        self.assertIn("fetch('/video/korea/logistics.json'", kr_prices.SCRIPT)

    def test_owner_wording(self):
        steps = steps_block.intro() + steps_block.korea_steps() + steps_block.signature()
        for text in ('Вартість послуги — 600 $', 'за курсом НБУ', 'AutoPapa', 'вул. Перемоги, 20',
                     'розрахуємо вартість розмитнення', 'Усі наші ціни фіксовані', 'прихованих платежів',
                     'За 10 днів до митного оформлення', 'охоронюваній стоянці', 'UA ART COMPANY',
                     'Стоимость услуги — 600 $', 'Бесплатная парковка AutoPapa', 'პატივისცემით',
                     'купівля — 600 $, депозит — 1 000 $', 'Оформлення договору', 'Купівля автомобіля, логістика та супутні витрати', 'до завантаження на пором', 'Повний цикл придбання та доставки автомобіля', 'до 4 місяців', 'до 7 робочих днів', 'зараховується у витрати на автомобіль'):
            self.assertIn(text, steps)
        for note in ('Депозит 1 000 $ зараховується', 'Усі наші ціни фіксовані', 'розрахуємо вартість розмитнення', 'За 10 днів до митного',
                     'прихованих платежів', 'Безкоштовна парковка AutoPapa'):
            at = steps.index(note)
            self.assertIn('ua-kr-note', steps[steps.rindex('<', 0, steps.rindex('class=', 0, at)) - 60:at])

    def test_step_three_starts_with_the_car_purchase(self):
        step = steps_block.step3()
        body = step[step.index('</summary><div>') + len('</summary><div>'):]
        self.assertTrue(body.startswith('<p data-ru="После покупки выбранного'))
        self.assertLess(step.index('прихованих платежів'), step.index('Логістика з Кореї до Києва'))

    def test_step_four_has_three_stages_without_encar(self):
        step = steps_block.step4()
        self.assertEqual(step.count('<li><strong'), 3)
        self.assertNotIn('Encar', step)

    def test_refuses_second_run_and_missing_anchor(self):
        with self.assertRaises(ValueError):
            edit_home.build(self.result.encode())
        with self.assertRaises(ValueError):
            edit_home.build(LIVE.replace('<li><i>3</i>', '<li><i>03</i>').encode())

    def test_builder_changes_only_the_home_page(self):
        self.assertEqual(list(candidate_builder.build({HOME: LIVE.encode()}, {})), [HOME])

    def test_readable_and_accessible(self):
        for css in ('min-height:44px', 'button:focus-visible', '.ua-how [hidden]{display:none!important}'):
            self.assertIn(css, steps_block.CSS)
        self.assertIn('role="group"', steps_block.switcher())
        self.assertIn("setAttribute('aria-pressed'", steps_block.SWITCH_SCRIPT)


if __name__ == '__main__':
    unittest.main()
