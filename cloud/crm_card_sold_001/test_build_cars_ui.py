#!/usr/bin/env python3
import ast
import hashlib
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('build_cars_ui', HERE / 'build_cars_ui.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

SOURCE = (b'import db\n\nasync def mark_sold(update, context):\n    return "ask"\n\n'
          b'async def mark_sold_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):\n'
          b'    set_field(cid, "status", "sold", 1)\n\n'
          b'def register(app):\n    return "kept"\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


class BuildTests(unittest.TestCase):
    def test_replaces_only_mark_sold_ok(self):
        out = b.build(SOURCE, expected=sha(SOURCE)).decode()
        self.assertIn('_ua_card_sold.mark_sold', out)
        self.assertNotIn('set_field(cid, "status"', out)
        self.assertIn('return "ask"', out)
        self.assertIn('return "kept"', out)
        names = [n.name for n in ast.parse(out).body if hasattr(n, 'name')]
        self.assertEqual(names, ['mark_sold', 'mark_sold_ok', 'register'])

    def test_refuses_other_source_or_duplicates(self):
        with self.assertRaises(b.BuildError):
            b.build(SOURCE)
        twice = SOURCE + b'\nasync def mark_sold_ok(u, c):\n    pass\n'
        with self.assertRaises(b.BuildError):
            b.build(twice, expected=sha(twice))

    def test_handler_keeps_callback_and_back_button(self):
        self.assertIn("callback_data='car_open:%d' % cid", b.HANDLER)
        self.assertIn('raise ApplicationHandlerStop', b.HANDLER)


if __name__ == '__main__':
    unittest.main()
