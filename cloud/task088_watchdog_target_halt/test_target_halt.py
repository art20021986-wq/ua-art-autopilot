"""Exercise the actual read-only inline workflow guard against isolated Git trees."""

import ast
import hashlib
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/uaart_transaction_watchdog.yml'
FIXTURE = pathlib.Path(__file__).parent / 'fixtures/task120-halt.json'


def guard_source():
    workflow = WORKFLOW.read_text(encoding='utf-8')
    step = workflow.split('      - name: Identify exact TASK120 halt before scheduled recovery\n', 1)[1]
    step = step.split('\n      - name:', 1)[0]
    source = step.split("          python3 -I - <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
    return '\n'.join(line[10:] for line in source.splitlines()) + '\n'


class TargetHaltGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = pathlib.Path(self.temporary.name)
        self.repo = self.folder / 'repo'
        self.repo.mkdir()
        (self.repo / 'state').mkdir()
        self.halt = self.repo / 'state/AUTOPILOT_HALT.json'
        self.output = self.folder / 'github-output'
        self.git('init', '-q')
        self.git('config', 'user.name', 'isolated-test')
        self.git('config', 'user.email', 'isolated-test@example.invalid')
        self.git('commit', '-q', '--allow-empty', '-m', 'fixture root')

    def git(self, *args):
        return subprocess.check_output(['/usr/bin/git', *args], cwd=self.repo, text=True)

    def commit_halt(self, payload=None):
        self.halt.write_bytes(FIXTURE.read_bytes() if payload is None else payload)
        self.git('add', 'state/AUTOPILOT_HALT.json')
        self.git('commit', '-q', '-m', 'fixture halt')

    def run_guard(self):
        before = self.git('status', '--porcelain=v1', '--untracked-files=all')
        head = self.git('rev-parse', 'HEAD')
        env = dict(os.environ, GITHUB_OUTPUT=str(self.output))
        result = subprocess.run([sys.executable, '-I', '-c', guard_source()], cwd=self.repo,
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('status', '--porcelain=v1', '--untracked-files=all'), before)
        return result

    def assert_rejected(self, code):
        result = self.run_guard()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(code, result.stderr)
        self.assertFalse(self.output.exists(), 'Failed validation must not publish a false/true gate output')

    def test_absent_halt_outputs_false_without_mutation(self):
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), 'task120_halt_present=false\n')

    def test_exact_committed_target_outputs_true_without_mutation(self):
        self.commit_halt()
        original = self.halt.read_bytes()
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text(), 'task120_halt_present=true\n')
        self.assertEqual(self.halt.read_bytes(), original)

    def test_target_fixture_matches_current_runtime_constant(self):
        tree = ast.parse((ROOT / 'automation/transaction_watchdog.py').read_text())
        expected = next(ast.literal_eval(node.value) for node in tree.body
                        if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == 'RECOVERY_HALT_SHA' for t in node.targets))
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), expected)
        self.assertIn(repr(expected), guard_source())

    def test_changed_target_or_other_halt_fails_closed(self):
        self.commit_halt(FIXTURE.read_bytes().replace(b'TASK120-PUBLISH', b'TASK999-PUBLISH'))
        self.assert_rejected('WATCHDOG_TARGET_HALT_IDENTITY_MISMATCH')

    def test_malformed_halt_fails_closed(self):
        self.commit_halt(b'{malformed\n')
        self.assert_rejected('WATCHDOG_TARGET_HALT_IDENTITY_MISMATCH')

    def test_deleted_tracked_halt_is_drift_not_absence(self):
        self.commit_halt()
        self.halt.unlink()
        self.assert_rejected('WATCHDOG_TARGET_HALT_WORKTREE_DRIFT')

    def test_uncommitted_target_change_fails_closed(self):
        self.commit_halt()
        self.halt.write_bytes(self.halt.read_bytes() + b'\n')
        self.assert_rejected('WATCHDOG_TARGET_HALT_WORKTREE_DRIFT')

    def test_untracked_exact_halt_cannot_authorize_recovery(self):
        self.halt.write_bytes(FIXTURE.read_bytes())
        self.assert_rejected('WATCHDOG_TARGET_HALT_UNTRACKED')

    def test_directory_and_dangling_symlink_fail_closed(self):
        self.halt.mkdir()
        self.assert_rejected('WATCHDOG_TARGET_HALT_FILE_INVALID')
        self.halt.rmdir()
        self.halt.symlink_to(self.folder / 'does-not-exist')
        self.assert_rejected('WATCHDOG_TARGET_HALT_FILE_INVALID')

    def test_symlink_to_valid_target_does_not_authorize(self):
        outside = self.folder / 'outside.json'
        outside.write_bytes(FIXTURE.read_bytes())
        self.halt.symlink_to(outside)
        self.assert_rejected('WATCHDOG_TARGET_HALT_FILE_INVALID')

    def test_oversized_halt_fails_closed(self):
        self.halt.write_bytes(b' ' * 65537)
        self.assert_rejected('WATCHDOG_TARGET_HALT_FILE_INVALID')

    def test_state_symlink_fails_closed(self):
        (self.repo / 'state').rmdir()
        outside = self.folder / 'outside-state'
        outside.mkdir()
        (self.repo / 'state').symlink_to(outside, target_is_directory=True)
        self.assert_rejected('WATCHDOG_TARGET_HALT_STATE_INVALID')

    def test_scheduled_canary_requires_complete_discovery_and_exact_target(self):
        workflow = WORKFLOW.read_text()
        job = workflow.split('\n  recovery_canary:\n', 1)[1].split('\n  recovery_execute:', 1)[0]
        header = job.split('\n    runs-on:', 1)[0]
        self.assertRegex(header, r"github.event_name == 'schedule' && needs\.discover\.result == 'success' &&\s+"
                         r"needs\.discover\.outputs\.transaction_status == 'NONE' &&\s+"
                         r"needs\.discover\.outputs\.task120_halt_present == 'true'")
        self.assertIn("task120_halt_present: ${{ steps.target_halt.outputs.task120_halt_present }}", workflow)
        step = workflow.split('        id: target_halt\n', 1)[1].split('\n      - name:', 1)[0]
        self.assertIn("if: steps.orphan.outputs.transaction_status == 'NONE'", step)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.operation == 'canary'", header)
        self.assertIn("github.run_attempt == 1", header)


if __name__ == '__main__':
    unittest.main(verbosity=2)
