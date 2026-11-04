#!/usr/bin/env python3
"""CARD-FINANCE-002: the yellow link on a live card (UA-0013 as FINANCE-PROBE read it) and the revision edit."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / 'finance_001'))  # ua_finance_partners, installed by FINANCE-001
import candidate_builder  # noqa: E402
import edit_metadata  # noqa: E402
import ua_card_finance  # noqa: E402

CARD = (HERE / 'fixtures' / 'UA-0013.html').read_text(encoding='utf-8')


class ReleaseTests(unittest.TestCase):
    def test_yellow_link_once_after_ask_question(self):
        out = ua_card_finance.add(CARD, 'UA-0013.html')
        self.assertEqual(out.count('id="ua-finance-link"'), 1)
        self.assertIn('style="background:var(--zoloto,#e8a33d);border-color:var(--zoloto,#e8a33d);color:#10202f;'
                      'font-weight:800"', out)
        self.assertNotIn('kn_kupit', ua_card_finance.link('UA-0013'))  # not a second primary button
        self.assertEqual(ua_card_finance.add(out, 'UA-0013.html'), out)

    def test_old_link_is_rewritten_not_doubled(self):
        old = CARD.replace("Задать вопрос по этой машине</a>",
                           'Задать вопрос по этой машине</a><a class="vtoraya" id="ua-finance-link" href="#">x</a>', 1)
        out = ua_card_finance.add(old, 'UA-0013.html')
        self.assertEqual(out.count('id="ua-finance-link"'), 1)
        self.assertIn(ua_card_finance.STYLE, out)

    def test_revision_edit(self):
        src = b"SEO_REVISION = 'CARD-FINANCE-001'\nX = 1\n"
        out = candidate_builder.build({edit_metadata.NAME: src}, {})
        self.assertEqual(out[edit_metadata.NAME], b"SEO_REVISION = 'CARD-FINANCE-002'\nX = 1\n")
        self.assertEqual(sorted(out), ['ua_card_finance.py', 'ua_seo_metadata.py'])
        with self.assertRaisesRegex(ValueError, 'METADATA_REVISION'):
            edit_metadata.build(out[edit_metadata.NAME])


if __name__ == '__main__':
    unittest.main()
