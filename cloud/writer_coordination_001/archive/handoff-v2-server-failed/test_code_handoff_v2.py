"""Synthetic files/fake authority only; real flock contention. No production I/O."""
import os
from pathlib import Path
import multiprocessing
import fcntl
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import code_handoff_v2 as h
import server_fence as sf

def _compete(names):
    for name in names:
        fd = os.open(name, os.O_RDWR)
        try:
            try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError: pass
            else: raise SystemExit(9)
        finally: os.close(fd)

class Authority:
    """Deliberately synthetic test authority; never a production adapter."""
    def __init__(self):
        self.enabled, self.calls, self.custom = True, [], None
    def __call__(self, plan, challenge, phase):
        self.calls.append(phase)
        if not self.enabled:
            raise h.HandoffError('TEST_DRAIN_PROOF_UNAVAILABLE')
        now = time.time()
        result = {'status': h.PROOF_STATUS, 'challenge': challenge, 'session': plan['session'],
                  'install_plan_sha256': plan['install_plan_sha256'],
                  'coordination_plan_sha256': plan['coordination_plan_sha256'],
                  'candidate_manifest_sha256': h.MANIFEST_SHA256,
                  'issued_at': now, 'expires_at': now + 20,
                  'authorization_receipt_sha256': 'a'*64, 'pause_readback_sha256': 'b'*64,
                  'drain_receipt_sha256': 'c'*64}
        result.update(self.custom or {})
        return result

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root, self.control = self.base/'fixture', self.base/'control'
        self.root.mkdir(); self.control.mkdir()
        nonce = '1'*64
        (self.control/'sessions'/nonce).mkdir(parents=True)
        self.session = {'repository':'art20021986-wq/ua-art-autopilot', 'account':'Carix',
                        'production_root':'/home/Carix', 'task_id':'HANDOFF-TEST-001',
                        'expected_main':'2'*40, 'plan_sha256':'3'*64, 'run_id':'123',
                        'run_attempt':1, 'nonce':nonce, 'epoch':1,
                        'source_sha256':sf.sha(Path(sf.__file__).read_bytes())}
        for name in sf.LOCK_NAMES: (self.root/name).write_bytes(b'')
        self.lease = sf.FenceLease(self.root,self.control,self.session)
        self.lease.acquire(); self.addCleanup(self.lease.close)
        self.candidate = self.base/'candidate'; self.candidate.mkdir()
        self.names = ['m%02d.py'%i for i in range(16)]+['nested/installer.py']
        self.before, entries = {}, {}
        for i,name in enumerate(self.names):
            target = self.root/name; target.parent.mkdir(exist_ok=True,parents=True)
            if i != 2:
                target.write_bytes(('LEGACY = %d\n'%i).encode()); os.chmod(target,0o640)
                os.utime(target,ns=(123000000000,123000000000))
                self.before[name] = h.sha(target.read_bytes())
            else: self.before[name] = None
            output = self.candidate/name; output.parent.mkdir(exist_ok=True,parents=True)
            output.write_bytes(('FIXED = %d\n'%i).encode())
            entries[name] = {'after_sha256':h.sha(output.read_bytes()), 'before_sha256':'d'*64}
        (self.root/'render.py').write_bytes(b'render = True\n')
        manifest = {'candidate_id':'UA-ART-SPEC-AUTO10-COMPLETE-17-V2','module_count':17,
                    'target_root':'/home/Carix','files':entries,
                    'execution_dependency_pins':{'render.py':h.sha(b'render = True\n')}}
        raw = h.canonical(manifest)+b'\n'; (self.candidate/'manifest.json').write_bytes(raw)
        pin = patch.object(h,'MANIFEST_SHA256',h.sha(raw)); pin.start(); self.addCleanup(pin.stop)
        self.authority = Authority()
        self.plan = h.make_install_plan(self.session,self.candidate,self.before,coordination_plan_sha256='4'*64)
        self.worker = self.new_worker()
    def new_worker(self): return h.CodeHandoff(self.lease,self.candidate,self.plan,verify_window=self.authority)
    def assert_before(self): self.worker._all(self.before)
    def test_install_code_only_keeps_all_locks(self):
        result = self.worker.install()
        self.assertEqual(result['status'],'CODE_INSTALLED_READBACK')
        self.assertFalse(result['unpause_authorized']); self.assertFalse(result['loaded_runtime_verified'])
        self.assertEqual(result['crm_html_media_writes'],0); self.assertEqual(result['overall_gate_b'],'NOT_EVALUATED')
        self.lease._check(); self.assertTrue(self.lease.held)
        self.assertEqual((self.root/self.names[0]).stat().st_mode & 0o777,0o640)
        self.assertIn('INSTALL_READBACK',self.authority.calls)
    def test_rejects_local_bool(self):
        self.worker.verifier = lambda *args: True
        with self.assertRaisesRegex(h.HandoffError,'VERIFIED_WINDOW_REQUIRED'): self.worker.install()
        self.assertFalse(self.worker.transaction.exists()); self.assert_before()
    def test_missing_authority(self):
        self.authority.enabled = False
        with self.assertRaisesRegex(h.HandoffError,'DRAIN_PROOF'): self.worker.install()
        self.assertFalse(self.worker.transaction.exists())
    def test_stale_or_wrong_binding(self):
        for value in ({'issued_at':time.time()-40},{'challenge':'0'*64},{'session':{}},
                      {'drain_receipt_sha256':None},{'install_plan_sha256':'0'*64}):
            self.authority.custom = value
            with self.assertRaises(h.HandoffError): self.worker.install()
        self.assert_before()
    def test_no_repeat(self):
        self.worker.install()
        with self.assertRaises(h.HandoffError): self.new_worker().install()
        self.assertTrue(self.lease.held)
    def test_actual_writes_rolled_back(self):
        original,count = self.worker._replace,0
        def fail(name,data,expected,**kwargs):
            nonlocal count
            count += 1; original(name,data,expected,**kwargs)
            if count == 4: raise RuntimeError('fourth actual write')
        self.worker._replace = fail
        with self.assertRaisesRegex(RuntimeError,'fourth'): self.worker.install()
        self.assert_before(); self.assertFalse((self.root/self.names[2]).exists())
        for name in self.names:
            if self.before[name] is not None: self.assertEqual((self.root/name).stat().st_mtime_ns,123000000000)
        self.assertTrue((self.worker.transaction/'terminal-CODE_ROLLED_BACK_READBACK.json').exists())
    def test_interruption_after_replace_rolls_back_only(self):
        class Crash(BaseException): pass
        original = self.worker._replace
        def crash(name,data,expected,**kwargs):
            original(name,data,expected,**kwargs); raise Crash()
        self.worker._replace = crash
        with self.assertRaises(Crash): self.worker.install()
        other = self.new_worker()
        with self.assertRaises(h.HandoffError): other.install()
        self.assertEqual(other.rollback_only()['status'],'CODE_ROLLED_BACK_READBACK'); self.assert_before()
    def test_new_file_post_link_crash_cleans_only_owned_stage(self):
        class Crash(BaseException): pass
        original_unlink = h.os.unlink
        original_link = h.os.link
        linked = False
        def linked_then_interrupt(*args, **kwargs):
            nonlocal linked
            result = original_link(*args, **kwargs)
            linked = True
            return result
        def interrupt_cleanup(path, *args, **kwargs):
            if linked and str(path).startswith('.uaart-install-'):
                raise Crash('interrupted between hardlink and stage unlink')
            return original_unlink(path, *args, **kwargs)
        with patch.object(h.os, 'link', linked_then_interrupt), patch.object(h.os, 'unlink', interrupt_cleanup):
            with self.assertRaises(Crash): self.worker.install()
        self.assertEqual((self.root/self.names[2]).stat().st_nlink, 2)
        result = self.new_worker().rollback_only()
        self.assertEqual(result['status'], 'CODE_ROLLED_BACK_READBACK')
        self.assert_before()
        self.assertFalse(list(self.root.glob('.uaart-install-*')))
    def test_foreign_write_not_destroyed(self):
        original = self.worker._replace
        def foreign(name,data,expected,**kwargs):
            original(name,data,expected,**kwargs)
            (self.root/name).write_bytes(b'foreign owner write'); raise RuntimeError()
        self.worker._replace = foreign
        with self.assertRaisesRegex(h.HandoffError,'ROLLBACK_BLOCKED'): self.worker.install()
        self.assertEqual((self.root/self.names[0]).read_bytes(),b'foreign owner write')
        self.assertTrue(self.lease.held); self.assertFalse(list(self.worker.transaction.glob('terminal-*')))
    def test_proof_loss_leaves_incomplete(self):
        original = self.worker._replace
        def lose(name,data,expected,**kwargs):
            original(name,data,expected,**kwargs); self.authority.enabled = False
        self.worker._replace = lose
        with self.assertRaisesRegex(h.HandoffError,'ROLLBACK_BLOCKED'): self.worker.install()
        self.assertTrue(self.lease.held); self.assertFalse(list(self.worker.transaction.glob('terminal-*')))
    def test_competing_process_cannot_acquire_any_six_locks(self):
        original = self.worker._replace
        def check(name,data,expected,**kwargs):
            process = multiprocessing.get_context('fork').Process(target=_compete,
                args=([str(self.root/n) for n in sf.LOCK_NAMES],))
            process.start(); process.join(10)
            self.assertFalse(process.is_alive()); self.assertEqual(process.exitcode,0)
            original(name,data,expected,**kwargs)
        self.worker._replace = check; self.worker.install()
    def test_precondition_drift(self):
        (self.root/self.names[0]).write_bytes(b'drift')
        with self.assertRaisesRegex(h.HandoffError,'TARGET_READBACK'): self.worker.install()
        self.assertFalse(self.worker.transaction.exists())
    def test_dependency_drift(self):
        (self.root/'render.py').write_bytes(b'drift')
        with self.assertRaisesRegex(h.HandoffError,'DEPENDENCY_DRIFT'): self.worker.install()
    def test_extra_candidate_file(self):
        (self.candidate/'extra.py').write_bytes(b'')
        with self.assertRaisesRegex(h.HandoffError,'EXACT_CANDIDATE_FILE_SET'): self.new_worker()
    def test_epoch_replay(self):
        self.plan['session']['epoch'] += 1
        with self.assertRaisesRegex(h.HandoffError,'INSTALL_PLAN_CHANGED'): self.new_worker()
    def test_wrong_holder_process(self):
        self.lease.pid = -1
        with self.assertRaises(sf.FenceError): self.worker.install()
        self.lease.pid = os.getpid()
    def test_incomplete_preconditions(self):
        before = dict(self.before); del before[self.names[2]]
        with self.assertRaisesRegex(h.HandoffError,'EXACT_LIVE_PRECONDITIONS'):
            h.make_install_plan(self.session,self.candidate,before,coordination_plan_sha256='4'*64)
    def test_backup_tampering(self):
        self.worker.install(); next((self.worker.transaction/'backup').glob('*.bin')).write_bytes(b'tampered')
        with self.assertRaisesRegex(h.HandoffError,'BACKUP_BYTES_CHANGED'): self.new_worker().rollback_only()
    def test_partial_journal(self):
        self.worker.install()
        with self.worker.journal_path.open('ab') as stream: stream.write(b'{')
        with self.assertRaisesRegex(h.HandoffError,'JOURNAL_INCOMPLETE'): self.new_worker().rollback_only()
    def test_terminal_replay_reads_same_result_without_reinstall(self):
        result = self.worker.install()
        journal = self.worker.journal_path.read_bytes()
        self.assertEqual(self.new_worker().read_terminal(), result)
        self.assertEqual(self.worker.journal_path.read_bytes(), journal)
        (self.root/self.names[0]).write_bytes(b'drift')
        with self.assertRaisesRegex(h.HandoffError, 'TARGET_READBACK'):
            self.new_worker().read_terminal()
    def test_verifier_cannot_drop_lease_and_still_permit_write(self):
        original = self.worker.verifier
        def drop(plan, challenge, phase):
            result = original(plan, challenge, phase)
            if phase.startswith('BEFORE_WRITE:'): self.lease.close()
            return result
        self.worker.verifier = drop
        with self.assertRaises(sf.FenceError): self.worker.install()
        self.assert_before()
    def test_old_installed_receipt_not_current_after_rollback(self):
        self.worker.install()
        result = self.new_worker().rollback_only()
        self.assertTrue((self.worker.transaction/'terminal-CODE_INSTALLED_READBACK.json').exists())
        self.assertEqual(self.new_worker().read_terminal(), result)
        self.assertEqual(result['status'], 'CODE_ROLLED_BACK_READBACK')
    def test_no_unpause_after_rollback(self):
        self.worker.install(); result = self.new_worker().rollback_only()
        self.assertFalse(result['unpause_authorized']); self.assertFalse(result['tasks_resumed'])
        with self.assertRaisesRegex(h.HandoffError,'ALREADY_ROLLED_BACK'): self.new_worker().rollback_only()

if __name__ == '__main__': unittest.main(verbosity=2)
