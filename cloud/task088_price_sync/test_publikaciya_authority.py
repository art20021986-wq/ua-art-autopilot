"""Targeted real primitive checks; private source is pinned/extracted, not imported.

Set UA114_CURRENT_BASE to the retained private source directory. All file writes
are isolated fixtures. No production read, bot import, or historical suite runs.
"""
import ast
import contextlib
import copy
import hashlib
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'task088_v5_writer_fence'))
import patch_publikaciya as patcher
import publication_fence
import visibility_lifecycle as visibility


class PublisherAuthorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(os.environ['UA114_CURRENT_BASE']) / 'publikaciya.py'
        cls.source = path.read_bytes()
        if hashlib.sha256(cls.source).hexdigest() != patcher.SOURCE_SHA256:
            raise RuntimeError('EXACT_PRIVATE_PUBLISHER_REQUIRED')
        cls.candidate, cls.report = patcher.patch_publikaciya(cls.source)
        cls.original_tree = ast.parse(cls.source)
        cls.candidate_tree = ast.parse(cls.candidate)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='publisher-authority-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / 'site' / 'UA-0001.html'
        self.target.parent.mkdir()
        self.target.write_text('OPERATOR_BEFORE')
        namespace = {'io': io, 'os': os, 'shutil': shutil, 'BASE': str(self.root)}
        primitives = []
        for node in self.candidate_tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == '_otkat':
                primitives.append(node)
            if isinstance(node, ast.FunctionDef) and node.name == '_zapisat_atomarno':
                if any(isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                       and isinstance(call.func.value, ast.Name) and call.func.value.id == 'os'
                       and call.func.attr == 'replace' for call in ast.walk(node)):
                    primitives.append(node)
        self.assertEqual(len(primitives), 2)
        exec(compile(ast.Module(body=primitives, type_ignores=[]), '<exact-private-primitives>', 'exec'), namespace)
        self.forward = namespace['_zapisat_atomarno']
        self.restore = namespace['_otkat']
        ge = types.ModuleType('site_ge_inject')
        ge.inject_html = lambda text: text
        self.ge = ge
        modules = mock.patch.dict(sys.modules, {'site_ge_inject': ge})
        modules.start()
        self.addCleanup(modules.stop)

    def backup(self):
        backup = self.root / 'backup'
        backup.mkdir()
        (backup / 'site__UA-0001.html').write_text('BACKED_UP')
        return str(backup)

    def test_rejects_source_drift_and_reapplication(self):
        for value in (self.source + b'\n', self.candidate, bytearray(self.source)):
            with self.assertRaisesRegex(ValueError, 'SOURCE_SHA256_MISMATCH'):
                patcher.patch_publikaciya(value)

    def test_removing_exact_hooks_restores_complete_original_AST(self):
        tree = copy.deepcopy(self.candidate_tree)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name == '_otkat':
                self.assertIsInstance(node.body[0], ast.ImportFrom)
                self.assertIsInstance(node.body[1], ast.With)
                node.body = node.body[1].body
            elif node.name == '_zapisat_atomarno':
                node.body = [item for item in node.body
                    if not (isinstance(item, ast.ImportFrom) and item.module == 'visibility_lifecycle')
                    and not (isinstance(item, ast.Expr) and isinstance(item.value, ast.Call)
                             and isinstance(item.value.func, ast.Name)
                             and item.value.func.id == '_task088_require_active_authority')]
        self.assertTrue(ast.dump(tree, include_attributes=False) ==
                        ast.dump(self.original_tree, include_attributes=False))

    def test_legacy_atomic_write_unchanged_outside_context(self):
        self.forward(str(self.target), 'NEW_PAGE')
        self.assertEqual(self.target.read_text(), 'NEW_PAGE')
        self.assertFalse(Path(str(self.target) + '.rem2tmp').exists())

    def test_expiry_during_render_blocks_actual_forward_switch(self):
        state = {'expired': False, 'checks': 0}
        def check():
            state['checks'] += 1
            if state['expired']:
                raise visibility.VisibilityError('EXPIRED_FIXTURE_AUTHORITY')
        def render(text):
            state['expired'] = True
            self.target.write_text('NEWER_OPERATOR_PAGE')
            return text
        self.ge.inject_html = render
        with visibility.authority_scope(check), mock.patch.object(os, 'replace', wraps=os.replace) as switch:
            with self.assertRaisesRegex(visibility.VisibilityError, 'EXPIRED_FIXTURE_AUTHORITY'):
                self.forward(str(self.target), 'MUST_NOT_PUBLISH')
            self.assertEqual(switch.call_count, 0)
        self.assertEqual(state['checks'], 2)
        self.assertEqual(self.target.read_text(), 'NEWER_OPERATOR_PAGE')

    def test_legacy_compensation_unchanged_outside_context(self):
        self.restore(self.backup(), [str(self.target)])
        self.assertEqual(self.target.read_text(), 'BACKED_UP')

    def test_recovery_ownership_refusal_propagates_before_swallowed_copy(self):
        backup = self.backup()
        self.target.write_text('NEWER_OPERATOR_PAGE')
        def reject():
            raise visibility.VisibilityError('JOURNAL_OR_OPERATOR_ROW_CHANGED')
        with visibility.authority_scope(lambda: None, recovery_check=reject):
            with mock.patch.object(publication_fence, 'require_publication_fence', return_value=None):
                with mock.patch.object(shutil, 'copy2', wraps=shutil.copy2) as restore:
                    with self.assertRaisesRegex(visibility.VisibilityError, 'JOURNAL_OR_OPERATOR_ROW_CHANGED'):
                        self.restore(backup, [str(self.target)])
                    self.assertEqual(restore.call_count, 0)
        self.assertEqual(self.target.read_text(), 'NEWER_OPERATOR_PAGE')

    def test_owned_compensation_can_finish_after_expiry_and_scope_is_restored(self):
        state = {'expired': False, 'recovery_checks': 0}
        def check():
            if state['expired']:
                raise visibility.VisibilityError('EXPIRED_FIXTURE_AUTHORITY')
        def recovery_check():
            state['recovery_checks'] += 1
        backup = self.backup()
        with visibility.authority_scope(check, recovery_check=recovery_check):
            state['expired'] = True
            with mock.patch.object(publication_fence, 'require_publication_fence', return_value=None) as fence:
                self.restore(backup, [str(self.target)])
                self.assertEqual(fence.call_count, 1)
            with self.assertRaisesRegex(visibility.VisibilityError, 'EXPIRED_FIXTURE_AUTHORITY'):
                self.forward(str(self.target), 'MUST_NOT_ESCAPE_RECOVERY')
        self.assertEqual(state['recovery_checks'], 1)
        self.assertEqual(self.target.read_text(), 'BACKED_UP')


if __name__ == '__main__':
    unittest.main()
