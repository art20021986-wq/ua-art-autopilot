"""Execute the exact reviewed Bash writer against new local-only Git fixtures.

These tests use a synthetic receipt and a fake token; they do not authorize or
perform a production transition. Each origin is a freshly created local bare
repository. No remote host, existing checkout, or user Git configuration is used.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / '.github/workflows/uaart_transaction_watchdog.yml'
HALT_PATH = 'state/AUTOPILOT_HALT.json'
CANARY_PATH = 'state/recovery_route_receipts/UA-ART-RECOVERY-TASK120-002.json'
ARCHIVE_PATH = 'state/halt_history/UA-ART-RECOVERY-TASK120-002/halt.json'
RECEIPT_PATH = 'state/halt_history/UA-ART-RECOVERY-TASK120-002/receipt.json'
HALT = b'{"fixture":"original stop; not a production identity"}\n'


def writer_body(operation: str) -> str:
    """Extract the one fixed run scalar without importing any repository code."""
    source = WORKFLOW.read_text()
    block = source.split('  recovery_' + operation + ':\n', 1)[1]
    block = block.split('\n  recovery_', 1)[0]
    named = '      - name: Persist exact recovery ' + operation
    step = block.split(named, 1)[1].split('\n      - name:', 1)[0]
    body = step.split('        run: |\n', 1)[1]
    lines = body.rstrip().splitlines()
    if any(line.strip() and not line.startswith('          ') for line in lines):
        raise AssertionError('Unexpected Bash scalar indentation')
    return '\n'.join(line[10:] if line else '' for line in lines) + '\n'


class WorkflowWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='uaart-route-writer-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.folder = pathlib.Path(self.temp.name)
        self.origin = self.folder / 'origin.git'
        self.work = self.folder / 'work'
        self.runner = self.folder / 'runner-temp'
        self.runner.mkdir()
        self.proposal = self.runner / 'uaart-recovery-proposal'
        self.proposal.mkdir(mode=0o700)
        self.env = {
            'PATH': '/usr/bin:/bin',
            'LANG': 'C.UTF-8',
            'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_TERMINAL_PROMPT': '0',
            'GIT_ALLOW_PROTOCOL': 'file',
        }
        self.git('init', '--bare', '--initial-branch=main', str(self.origin), cwd=self.folder)
        self.git('clone', str(self.origin), str(self.work), cwd=self.folder)
        (self.work / 'state').mkdir()
        (self.work / HALT_PATH).write_bytes(HALT)
        (self.work / 'automation').mkdir()
        (self.work / 'automation/control_plane.py').write_text('# fixture only\n')
        (self.work / 'untouched.txt').write_bytes(b'must remain unchanged\n')
        self.git('add', '--all')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@invalid',
                 'commit', '-m', 'fixture baseline')
        self.parent = self.git('rev-parse', 'HEAD').strip()
        self.git('push', 'origin', 'HEAD:refs/heads/main')
        self.receipt = b'{"fixture_only":true,"owner_execution_authorized":false}\n'
        (self.proposal / 'receipt.json').write_bytes(self.receipt)
        (self.proposal / 'halt.json').write_bytes(HALT)
        self.env.update({
            'GH_TOKEN': 'LOCAL_FIXTURE_FAKE_TOKEN_NOT_A_CREDENTIAL',
            'RUNNER_TEMP': str(self.runner),
            'GITHUB_OUTPUT': str(self.runner / 'github-output'),
            'GITHUB_RUN_ID': '123456789',
            'WORKFLOW_SOURCE_COMMIT': self.parent,
            'PARENT': self.parent,
            'HALT_SHA256': hashlib.sha256(HALT).hexdigest(),
            'RECEIPT_SHA256': hashlib.sha256(self.receipt).hexdigest(),
        })

    def git(self, *args: str, cwd: pathlib.Path | None = None) -> str:
        return subprocess.check_output(
            ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', *args],
            cwd=cwd or self.work, env=self.env, text=True,
            stderr=subprocess.DEVNULL,
        )

    def remote_head(self) -> str:
        return self.git('--git-dir=' + str(self.origin), 'rev-parse', 'refs/heads/main').strip()

    def run_writer(self, operation: str) -> subprocess.CompletedProcess:
        # The extracted script's only origin is the new local bare fixture.
        self.assertEqual(self.git('remote', 'get-url', 'origin').strip(), str(self.origin))
        self.assertEqual(self.git('remote', 'get-url', '--push', 'origin').strip(), str(self.origin))
        return subprocess.run(
            ['/bin/bash', '-s'], input=writer_body(operation), text=True,
            cwd=self.work, env=self.env, capture_output=True, timeout=20,
        )

    def changed_paths(self, commit: str) -> list[str]:
        return self.git('diff-tree', '--no-commit-id', '--name-only', '-r', self.parent, commit).splitlines()

    def test_canary_adds_one_receipt_and_preserves_halt(self):
        run = self.run_writer('canary')
        self.assertEqual(run.returncode, 0, run.stderr)
        accepted = self.remote_head()
        self.assertNotEqual(accepted, self.parent)
        self.assertEqual(self.git('show', '-s', '--format=%P', accepted).strip(), self.parent)
        self.assertEqual(self.changed_paths(accepted), [CANARY_PATH])
        self.assertEqual(self.git('show', accepted + ':' + HALT_PATH).encode(), HALT)
        self.assertEqual(self.git('show', accepted + ':' + CANARY_PATH).encode(), self.receipt)
        proof = json.loads((self.proposal / 'remote-readback.json').read_text())
        self.assertEqual(proof['observed_remote_main'], accepted)
        self.assertTrue(proof['accepted_runtime_unchanged'])

    def test_execute_commits_exact_three_paths_and_original_archive(self):
        run = self.run_writer('execute')
        self.assertEqual(run.returncode, 0, run.stderr)
        accepted = self.remote_head()
        self.assertEqual(self.changed_paths(accepted), [HALT_PATH, ARCHIVE_PATH, RECEIPT_PATH])
        self.assertEqual(self.git('ls-tree', accepted, '--', HALT_PATH), '')
        self.assertEqual(self.git('show', accepted + ':' + ARCHIVE_PATH).encode(), HALT)
        self.assertEqual(self.git('show', accepted + ':' + RECEIPT_PATH).encode(), self.receipt)
        self.assertEqual(self.git('show', accepted + ':untouched.txt'), 'must remain unchanged\n')

    def test_parent_drift_refuses_any_remote_write(self):
        (self.work / 'unrelated.txt').write_text('concurrent actor\n')
        self.git('add', '--', 'unrelated.txt')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@invalid',
                 'commit', '-m', 'concurrent parent')
        drift = self.git('rev-parse', 'HEAD').strip()
        self.git('push', 'origin', 'HEAD:refs/heads/main')
        self.git('checkout', '--detach', self.parent)
        run = self.run_writer('canary')
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(self.remote_head(), drift)
        self.assertEqual(self.git('ls-tree', drift, '--', CANARY_PATH), '')
        self.assertEqual(self.git('show', drift + ':' + HALT_PATH).encode(), HALT)

    def test_repeat_writer_cannot_make_second_commit(self):
        first = self.run_writer('canary')
        self.assertEqual(first.returncode, 0, first.stderr)
        accepted = self.remote_head()
        repeat = self.run_writer('canary')
        self.assertNotEqual(repeat.returncode, 0)
        self.assertEqual(self.remote_head(), accepted)
        self.assertEqual(self.git('rev-list', '--count', self.parent + '..' + accepted).strip(), '1')

    def test_proposal_receipt_tamper_refuses_write(self):
        (self.proposal / 'receipt.json').write_bytes(b'altered fixture\n')
        run = self.run_writer('canary')
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(self.remote_head(), self.parent)


if __name__ == '__main__':
    unittest.main()
