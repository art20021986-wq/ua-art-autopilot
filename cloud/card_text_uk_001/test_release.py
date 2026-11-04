#!/usr/bin/env python3
"""CARD-TEXT-UK-001: the phrase joins the uk dictionary exactly once, nothing else changes."""
import json
import unittest

import candidate_builder
import edit_languages

SCRIPT = ('(function(){var dictionaries = {"ru":{"Повторити":"Повторить"},"uk":{"Повторить":"Повторити"},'
          '"ka":{"Повторить":"გამეორება"}};})();')


def uk(text):
    start = text.index('var dictionaries = ') + len('var dictionaries = ')
    return json.JSONDecoder().raw_decode(text[start:])[0]


class ReleaseTests(unittest.TestCase):
    def test_phrase_added_others_kept(self):
        out = candidate_builder.build({edit_languages.NAME: SCRIPT.encode()}, {})[edit_languages.NAME].decode()
        before, after = uk(SCRIPT), uk(out)
        self.assertEqual(after['uk'][edit_languages.RUSSIAN], edit_languages.UKRAINIAN)
        self.assertEqual({k: v for k, v in after['uk'].items() if k != edit_languages.RUSSIAN}, before['uk'])
        self.assertEqual((after['ru'], after['ka']), (before['ru'], before['ka']))
        with self.assertRaisesRegex(ValueError, 'LANGUAGES_FRAGMENT'):
            edit_languages.build(out.encode())


if __name__ == '__main__':
    unittest.main()
