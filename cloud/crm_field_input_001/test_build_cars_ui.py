#!/usr/bin/env python3
"""Builder tests on a fixture that copies the installed drop_wait/edit_ask/client_ask lines."""
import ast
import asyncio
import hashlib
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('build_cars_ui', HERE / 'build_cars_ui.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

SOURCE = b'''class ApplicationHandlerStop(Exception):
    pass


def drop_wait(context):
    """\xd0\x9e\xd1\x82\xd0\xba\xd1\x80\xd1\x8b\xd0\xbb\xd0\xb8 \xd0\xb4\xd1\x80\xd1\x83\xd0\xb3\xd0\xbe\xd0\xb9 \xd1\x8d\xd0\xba\xd1\x80\xd0\xb0\xd0\xbd."""
    try:
        context.user_data.pop('car_wait', None)
        context.user_data.pop('car_media_wait', None)
    except Exception:
        pass


async def edit_ask(update, context):
    q = update.callback_query
    _, cid, field = q.data.split(':')
    context.user_data['car_wait'] = {'card_id': int(cid), 'field': field}
    raise ApplicationHandlerStop


async def client_ask(update, context):
    q = update.callback_query
    _, cid, field = q.data.split(':')
    context.user_data['car_wait'] = {'card_id': int(cid), 'field': field, 'client': True}
    raise ApplicationHandlerStop


def catch_text(context):
    """Installed catch_message order: a media wait swallows routing before car_wait."""
    if context.user_data.get('car_media_wait'):
        return 'intake'
    return 'field' if context.user_data.get('car_wait') else 'intake'
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(source):
    """Import the given source as a real module from a temporary file."""
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'cars_ui_fixture.py'
        path.write_bytes(source)
        module_spec = importlib.util.spec_from_file_location('cars_ui_fixture', path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    return vars(module)


def prompt(module, name, data, user_data):
    context = SimpleNamespace(user_data=user_data)
    update = SimpleNamespace(callback_query=SimpleNamespace(data=data))
    try:
        asyncio.run(module[name](update, context))
    except module['ApplicationHandlerStop']:
        pass
    return context


STALE = {'car_media_wait': {'card_id': 17, 'target': 'condition_videos'},
         'cont_wait': {'card_id': 3, 'field': 'sea_container'},
         'ua099_spec_edit': {'cid': 3, 'spec_id': 9}, 'car_last': 17}


class BuildTests(unittest.TestCase):
    def build(self):
        return b.build(SOURCE, expected=sha(SOURCE))

    def test_fixture_reproduces_owner_report(self):
        old = load(SOURCE)
        context = prompt(old, 'edit_ask', 'car_setf:17:diag_link', dict(STALE))
        self.assertEqual(old['catch_text'](context), 'intake')

    def test_link_prompt_after_media_upload_reaches_field(self):
        new = load(self.build())
        for name, data, wait in (
                ('edit_ask', 'car_setf:17:diag_link', {'card_id': 17, 'field': 'diag_link'}),
                ('edit_ask', 'car_setf:17:diag_text', {'card_id': 17, 'field': 'diag_text'}),
                ('client_ask', 'car_setc:17:phone', {'card_id': 17, 'field': 'phone', 'client': True})):
            context = prompt(new, name, data, dict(STALE))
            self.assertEqual(new['catch_text'](context), 'field')
            self.assertEqual(context.user_data, {'car_wait': wait, 'car_last': 17})

    def test_only_two_lines_change_plus_helper(self):
        out = self.build().decode()
        self.assertEqual(out.count('_ua_wait_text(context, {'), 2)
        self.assertNotIn("context.user_data['car_wait'] = {", out)
        names = [n.name for n in ast.parse(out).body if hasattr(n, 'name')]
        self.assertEqual(names, ['ApplicationHandlerStop', 'drop_wait', '_ua_wait_text',
                                 'edit_ask', 'client_ask', 'catch_text'])
        removed = set(SOURCE.decode().splitlines()) - set(out.splitlines())
        self.assertEqual(len(removed), 2)

    def test_refuses_other_source_duplicates_and_rebuild(self):
        with self.assertRaises(b.BuildError):
            b.build(SOURCE)
        twice = SOURCE + b'\nasync def edit_ask(u, c):\n    pass\n'
        with self.assertRaises(b.BuildError):
            b.build(twice, expected=sha(twice))
        built = self.build()
        with self.assertRaises(b.BuildError):
            b.build(built, expected=sha(built))


if __name__ == '__main__':
    unittest.main()
