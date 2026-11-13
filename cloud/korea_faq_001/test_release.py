#!/usr/bin/env python3
"""KOREA-FAQ-001: the approved block lands once after «Чому аукціон вигідніше»; the Russian page check waits for it."""
from html import unescape
from pathlib import Path
import re
import unittest

import candidate_builder as builder
import deployment_controller as controller

HERE = Path(__file__).resolve().parent
LIVE = (HERE/'fixtures'/'korea_live.txt').read_bytes()  # public /video/korea.html, 2026-11-13
APPROVED = (HERE.parent/'korea_faq'/'approved.md').read_text(encoding='utf-8')


class BuildTests(unittest.TestCase):
    def test_block_after_anchor_rest_kept(self):
        page = builder.build({builder.PAGE: LIVE}, {})[builder.PAGE].decode('utf-8')
        live = LIVE.decode('utf-8')
        self.assertEqual(page.count('<!--UA-KOREA-FAQ-V1-->'), 1)
        self.assertEqual(page.replace(builder.block(), ''), live)  # only the block added
        anchor = page.index('Чому аукціон вигідніше</span></h2>')
        faq = page.index('<!--UA-KOREA-FAQ-V1-->')
        self.assertLess(anchor, faq)
        self.assertNotIn('<section', page[anchor:faq])  # right after that section
        self.assertTrue(page[faq - len('</section>'):faq] == '</section>')

    def test_texts_are_the_approved_ones(self):
        for (q_uk, _), (a_uk, _) in builder.QA:
            self.assertIn(q_uk, APPROVED)
            self.assertIn(a_uk, APPROVED)
        visible = unescape(re.sub(r'<[^>]+>', '\n', re.sub(r'(?s)<style>.*?</style>', '', builder.block())))
        self.assertEqual([x for x in visible.split('\n') if x.strip()],
                         [builder.TITLE[0]] + [t for q, a in builder.QA for t in (q[0], a[0])])
        self.assertNotIn('депозит', builder.block().lower())
        for _, ru in [q for q, _ in builder.QA] + [a for _, a in builder.QA]:
            self.assertIn('data-ru="%s"' % ru, builder.block())

    def test_refusals(self):
        page = builder.build({builder.PAGE: LIVE}, {})[builder.PAGE]
        with self.assertRaisesRegex(ValueError, 'KOREA_FAQ_ALREADY_APPLIED'):
            builder.build({builder.PAGE: page}, {})
        with self.assertRaisesRegex(ValueError, 'KOREA_FAQ_ANCHOR'):
            builder.build({builder.PAGE: LIVE.replace('Чому аукціон вигідніше'.encode(), b'X')}, {})


class PublicTests(unittest.TestCase):
    def test_korea_check(self):
        page = builder.build({builder.PAGE: LIVE}, {})[builder.PAGE].decode('utf-8')
        self.assertTrue(controller.EXPECTED['/video/korea.html'](page))
        self.assertFalse(controller.EXPECTED['/video/korea.html'](LIVE.decode('utf-8')))

    def test_russian_page_wait(self):
        done = 'Частые вопросы' + ''.join(controller.RU)
        pages = iter(['<html>', done])
        sleeps = []
        self.assertEqual(controller.russian_page_follows(lambda: next(pages), sleeps.append, lambda: 0), len(controller.RU))
        self.assertEqual(len(sleeps), 1)
        clock = iter([0, controller.RU_WAIT_SECONDS + 1])
        with self.assertRaisesRegex(RuntimeError, 'RU_PAGE_FAQ_MISSING:0'):
            controller.russian_page_follows(lambda: '<html>', lambda s: None, lambda: next(clock))


if __name__ == '__main__':
    unittest.main()
