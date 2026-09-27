import ast
from html.parser import HTMLParser
from pathlib import Path
import unittest
from urllib.parse import urlsplit, parse_qs

from ua_tracking_links import normalize, reference_kind, tracking_links
from ua_tracking_widget import START, END, render_tracking
from card_tracking import STAGE_START, STAGE_END, Elements, upgrade_card
from build_candidate import replace_metadata, BEGIN, AFTER


def card(meta=''):
    return '<h1>PRICE VIN PHOTO UNCHANGED</h1>' + STAGE_START + (
        '<section class="ua-delivery-v1"><div class="ua-stage-v1-route">STAGE</div>'
        + meta + '<div class="ua-stage-v1-eta">DATE</div></section>') + STAGE_END + '<footer>VIDEO</footer>'


class TrackingTests(unittest.TestCase):
    def test_container_keeps_all_four_prefix_letters(self):
        for number in ('FBLU0045137', 'CSQU3054383', 'MSCU6639870', 'TCLU1234567', 'ONEU1234567'):
            self.assertEqual(reference_kind(number), 'container')
            urls = tracking_links(number)
            self.assertEqual(len(urls), 1)
            self.assertEqual(urls[0][0], 'SeaRates')
            self.assertEqual(parse_qs(urlsplit(urls[0][1]).query), {'number': [number], 'sealine': ['AUTO']})
            self.assertEqual(urlsplit(urls[0][1]).netloc, 'www.searates.com')
            self.assertEqual(urlsplit(urls[0][1]).path, '/container/tracking/')

    def test_one_bill_preserves_full_reference_for_searates(self):
        number = 'ONEYTEST123456'
        urls = tracking_links(number)
        self.assertEqual(len(urls), 1)
        self.assertEqual(parse_qs(urlsplit(urls[0][1]).query)['number'], [number])

    def test_unknown_reference_does_not_claim_carrier(self):
        links = tracking_links('BOOK/2026-12345')
        self.assertNotIn('ONE', [x[0] for x in links])
        self.assertEqual(parse_qs(urlsplit(links[0][1]).query)['number'], ['BOOK/2026-12345'])
        self.assertEqual(parse_qs(urlsplit(links[0][1]).query)['sealine'], ['AUTO'])

    def test_spacing_and_case(self):
        self.assertEqual(normalize(' csqu 305 438 3\n'), 'CSQU3054383')

    def test_untrusted_or_invalid_values_have_no_links(self):
        for value in (None, '', '0', '??', 'a'*65, '<img src=x onerror=alert(1)>',
                      'javascript:alert(1)', 'https://evil.test', 'АВСU1234567', {'number': 'X'}):
            with self.subTest(value=value):
                self.assertEqual(tracking_links(value), [])
                self.assertNotIn('<a ', render_tracking(value))
                self.assertNotIn('<img', render_tracking(value))

    def test_links_explicit_and_no_automatic_external_requests(self):
        value = render_tracking('CSQU3054383')
        self.assertNotIn('<iframe', value)
        self.assertNotIn('fetch(', value)
        self.assertNotIn('setInterval', value)
        self.assertNotIn('<script', value)
        self.assertNotIn('<details>', value)
        self.assertNotIn('data-copy-tracking', value)
        self.assertEqual(value.count('rel="noopener noreferrer"'), 1)
        self.assertIn('Отследить контейнер', value)
        self.assertLess(value.index('ua-stage-v1-badge">'), value.index('<a '))
        parsed = Elements(value)
        link = parsed.with_class('ua-stage-v1-track-link')[0]
        self.assertNotIn('https://', link['text'])
        self.assertNotIn('SeaRates', link['text'])
        for lang in ('ru', 'uk', 'ka'):
            self.assertIn('data-' + lang + '=', value)

    def test_no_number_is_explicit(self):
        value = render_tracking('')
        self.assertIn('Номер отправки ещё не указан', value)
        self.assertNotIn('<details>', value)

    def test_existing_one_row_replaced_preserving_dates_and_other_content(self):
        meta = '<div class="ua-stage-v1-meta"><span class="ua-stage-v1-container-row"><span class="ua-stage-v1-badge">Контейнер: <b>ONEYOLD123</b></span><a class="ua-stage-v1-track-link" href="https://example.org">OLD</a></span><span class="ua-stage-v1-badge">Отправлен: <b>20.09.2026</b></span></div>'
        original = card(meta)
        updated = upgrade_card(original, 'CSQU3054383')
        self.assertNotIn('ONEYOLD123', updated)
        self.assertNotIn('href="https://example.org"', updated)
        self.assertIn('Отправлен: <b>20.09.2026</b>', updated)
        for marker in ('STAGE', 'DATE', 'PRICE VIN PHOTO UNCHANGED', '<footer>VIDEO</footer>'):
            self.assertIn(marker, updated)
        self.assertEqual(upgrade_card(updated, 'CSQU3054383'), updated)

    def test_existing_without_metadata_and_number_changes(self):
        initial = upgrade_card(card(), None)
        updated = upgrade_card(initial, 'ONEYTEST123456')
        self.assertEqual(updated.count(START), 1)
        self.assertNotIn('Номер отправки ещё не указан', updated)
        self.assertEqual(upgrade_card(updated, None), initial)

    def test_non_one_badge_is_upgraded(self):
        original = card('<div class="ua-stage-v1-meta"><span class="ua-stage-v1-badge">Контейнер: <b>CSQU3054383</b></span></div>')
        updated = upgrade_card(original, 'CSQU3054383')
        self.assertEqual(updated.count('<a '), 1)
        self.assertEqual(updated.count('class="ua-stage-v1-badge"'), 1)
        self.assertEqual(upgrade_card(updated, 'CSQU3054383'), updated)

    def test_ambiguous_card_rejected(self):
        for original in ('', card()+card(), card().replace(STAGE_START, STAGE_END)):
            with self.assertRaises(ValueError):
                upgrade_card(original, 'CSQU3054383')

    def test_source_patch_is_local_and_idempotent(self):
        source = ('before = 1\ndef _ua_delivery_stage_anchor(m):\n' + BEGIN
                  + '    tracking_href = "legacy"\n' + AFTER + '    return out\nafter = 2\n')
        updated = replace_metadata(source)
        self.assertIn('before = 1', updated)
        self.assertIn('after = 2', updated)
        self.assertNotIn('tracking_href =', updated)
        self.assertEqual(replace_metadata(updated), updated)
        with self.assertRaises(ValueError):
            replace_metadata(source+source)


if __name__ == '__main__':
    unittest.main()
