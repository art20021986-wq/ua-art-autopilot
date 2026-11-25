"""ADS-KEYS-002: the keys one by one, in one message, wrong values, ordinary messages, expiry, memory only."""
import unittest
from unittest.mock import patch

import candidate_builder
import ua_google_ads_key as key

TOKEN = 'TEST' + 'x' * 18
CLIENT = '1' * 12 + '-' + 'test' * 8 + '.apps.' + 'googleusercontent.com'
SECRET = 'GOC' + 'SPX-' + 'test' * 7


class CollectTests(unittest.TestCase):
    def setUp(self):
        key.PENDING.clear()
        self.saved = []
        auth = type('Auth', (), {'save_client': lambda *a: self.saved.append(a), 'auth_url': lambda: 'https://link'})
        self.enterContext(patch.dict('sys.modules', {'ua_google_ads_auth': auth}))

    def test_step_by_step_any_order(self):
        self.assertTrue(key.collect(1, SECRET, 0).startswith('Секрет клиента'))
        self.assertIn('идентификатор клиента', key.collect(1, '  ' + SECRET + '\n', 1))  # resend keeps the state
        self.assertIn('токен разработчика', key.collect(1, CLIENT, 2))
        self.assertTrue(key.collect(1, TOKEN, 3).startswith('Ключи Google Ads сохранены'))
        self.assertEqual(self.saved, [(TOKEN, CLIENT, SECRET)])
        self.assertEqual(key.PENDING, {})

    def test_one_message(self):
        self.assertIn('https://link', key.collect(2, TOKEN + '\n' + CLIENT + '\n' + SECRET, 0))

    def test_exact_reason(self):
        self.assertEqual(key.collect(3, '123-a.apps.googleusercontent.com', 0), key.BAD['client_id'])
        self.assertEqual(key.collect(3, 'GOCSPX-short', 0), key.BAD['client_secret'])
        key.collect(3, CLIENT, 0)
        self.assertEqual(key.collect(3, 'Токен: ' + TOKEN, 1), key.BAD['developer_token'])
        self.assertEqual(self.saved, [])

    def test_lone_word_only_while_collecting(self):
        self.assertIsNone(key.collect(4, TOKEN, 0))
        key.collect(4, CLIENT, 0)
        self.assertIsNone(key.collect(4, TOKEN, key.WAIT_SECONDS + 1))  # expired
        self.assertNotIn(4, key.PENDING)

    def test_parse_unchanged(self):
        self.assertEqual(key.parse('%s %s %s' % (SECRET, TOKEN, CLIENT)), (TOKEN, CLIENT, SECRET))
        self.assertIsNone(key.parse(CLIENT + ' ' + SECRET))

    def test_builder_pins_the_installed_file(self):
        with self.assertRaisesRegex(ValueError, 'UA_GOOGLE_ADS_KEY_UNEXPECTED'):
            candidate_builder.build({'ua_google_ads_key.py': b'other'})
        installed = (candidate_builder.HERE.parent / 'ads_keys_001' / 'ua_google_ads_key.py').read_bytes()
        self.assertEqual(set(candidate_builder.build({'ua_google_ads_key.py': installed})), {'ua_google_ads_key.py'})


if __name__ == '__main__':
    unittest.main()
