"""BOT-GUARD-001: the guard module, the two edits on the saved live sources and the candidate smoke run."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import candidate_builder as builder
import deployment_remote as remote
import ua_bot_guard as guard

HERE = Path(__file__).resolve().parent
PHONE = 'Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Mobile Safari/537.36'
PEOPLE = (PHONE,
          'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1',
          'Mozilla/5.0 (Linux; Android 13; Cubot X30) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36',
          'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148 Instagram 300.0.0',
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36')
ROBOTS = ('Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
          'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0)',
          'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 HeadlessChrome/131.0 Safari/537.36',
          'TelegramBot (like TwitterBot)', 'python-requests/2.31.0', 'curl/8.5.0', 'Go-http-client/1.1',
          'Mozilla/5.0 (compatible; AhrefsBot/7.0)', 'Scrapy/2.11', '')


class GuardTests(unittest.TestCase):
    def test_people_pass_robots_do_not(self):
        for agent in PEOPLE:
            self.assertFalse(guard.is_robot(agent), agent)
        for agent in ROBOTS:
            self.assertTrue(guard.is_robot(agent), agent)

    def test_limit_per_address_and_window(self):
        clock = [0.0]
        limiter = guard.Limiter(limit=3, seconds=60, capacity=10, clock=lambda: clock[0])
        self.assertEqual([limiter.allow('a') for _ in range(5)], [True, True, True, False, False])
        self.assertTrue(limiter.allow('b'))
        clock[0] = 60.0
        self.assertTrue(limiter.allow('a'))

    def test_capacity_is_bounded(self):
        limiter = guard.Limiter(limit=1, seconds=60, capacity=3, clock=lambda: 0.0)
        for key in 'abcde':
            limiter.allow(key)
        self.assertEqual(list(limiter._entries), ['c', 'd', 'e'])

    def test_address_prefers_the_proxy_header(self):
        self.assertEqual(guard.address({'HTTP_X_REAL_IP': '203.0.113.5', 'REMOTE_ADDR': '10.0.0.1'}), '203.0.113.5')
        self.assertEqual(guard.address({'REMOTE_ADDR': '10.0.0.1'}), '10.0.0.1')

    def test_allow(self):
        limiter = guard.Limiter(limit=1, clock=lambda: 0.0)
        self.assertFalse(guard.allow({'HTTP_USER_AGENT': ROBOTS[0], 'HTTP_X_REAL_IP': '1.1.1.1'}, limiter))
        self.assertTrue(guard.allow({'HTTP_USER_AGENT': PHONE, 'HTTP_X_REAL_IP': '1.1.1.1'}, limiter))
        self.assertFalse(guard.allow({'HTTP_USER_AGENT': PHONE, 'HTTP_X_REAL_IP': '1.1.1.1'}, limiter))


class EditTests(unittest.TestCase):
    def source(self, name):
        return (HERE/'fixtures'/(name[:-3] + '.txt')).read_text(encoding='utf-8')

    def test_edits_apply_once_and_compile(self):
        for name in builder.EDITS:
            text = builder.edit(name, self.source(name))
            compile(text, name, 'exec')
            self.assertEqual(text.count(builder.TAG), 1)
            with self.assertRaisesRegex(ValueError, 'ALREADY_APPLIED'):
                builder.edit(name, text)

    def test_changed_fragment_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'BOT_GUARD_FRAGMENT'):
            builder.edit('analitika_wsgi.py', self.source('analitika_wsgi.py').replace('ya.zapisat(dannye)', 'ya.zap(d)'))

    def test_only_the_two_lines_change(self):
        for name in builder.EDITS:
            before = self.source(name).splitlines()
            after = builder.edit(name, self.source(name)).splitlines()
            added = [line for line in after if line not in before]
            self.assertLessEqual(len(added), 3, name)
            self.assertTrue(all(line in after for line in before if 'ya.zapisat' not in line), name)

    def test_candidate_smoke_on_saved_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            after = Path(folder)/'after'
            after.mkdir()
            built = builder.build({n: self.source(n).encode() for n in builder.EDITS}, {})
            for name, value in built.items():
                (after/name).write_bytes(value)
            with patch.object(remote, 'ROOT', Path(folder)/'none'):
                value = remote.smoke(Path(folder))
        self.assertEqual(value, {'person': 1, 'robots': 0, 'flood_recorded_of_130': 120, 'other_paths': True,
                                 'script_webdriver': 1})


if __name__ == '__main__':
    unittest.main()
