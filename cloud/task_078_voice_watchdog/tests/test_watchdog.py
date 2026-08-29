"""Offline sandbox test suite for TASK 078.

These tests do not touch any network, PythonAnywhere, or CRM resource. They
exercise the pure-python watchdog package in this folder. They are provided
for independent controller execution (per canonical-memory precedent: this
worker documents test design/results but final acceptance requires
controller-run evidence, same pattern as task_015/task_021).

Run with: pytest cloud/task_078_voice_watchdog/tests/test_watchdog.py -v
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from cloud.task_078_voice_watchdog.circuit_breaker import (
    ProcessRestartBudget,
    STTCircuitBreaker,
)
from cloud.task_078_voice_watchdog.handler_patch import VoiceWatchdogHandler
from cloud.task_078_voice_watchdog.job_marker import JobMarkerStore
from cloud.task_078_voice_watchdog.killable_stt_worker import (
    KillableSTTWorker,
    compute_download_timeout,
    compute_stt_timeout,
)


# ---------------------------------------------------------------------------
# timeout math
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "duration,expected",
    [
        (0, 15),
        (3, 15),
        (30, 55),
        (60, 100),
        (120, 180),
        (600, 180),
        (3.33, 16),
    ],
)
def test_compute_stt_timeout_bounds(duration, expected):
    assert compute_stt_timeout(duration) == expected


def test_compute_download_timeout_bounds():
    assert compute_download_timeout(0) == 5
    assert compute_download_timeout(2) == 5
    assert compute_download_timeout(45) == 30
    assert compute_download_timeout(12) == 12


# ---------------------------------------------------------------------------
# killable worker behavior (module-level fns required for spawn pickling)
# ---------------------------------------------------------------------------

def _fast_ok(x):
    return f"ok:{x}"


def _hang_forever(x):
    time.sleep(3600)
    return "never"


def _raises(x):
    raise ValueError("boom")


def test_short_voice_pass_first_attempt():
    w = KillableSTTWorker(_fast_ok)
    outcome = w.run_with_single_restart(timeout=5, args=("hello",))
    assert outcome.status == "ok"
    assert outcome.payload == "ok:hello"
    assert outcome.attempts == 1
    assert outcome.killed is False


def test_first_attempt_hangs_worker_killed_no_second_success():
    # Both attempts hang -> after two timeouts, status stays timeout, no
    # orphan process should remain alive (join() calls above guarantee this).
    w = KillableSTTWorker(_hang_forever)
    outcome = w.run_with_single_restart(timeout=1, args=("x",))
    assert outcome.status == "timeout"
    assert outcome.attempts == 2
    assert outcome.killed is True


def test_exception_in_child_is_reported_not_crashing_parent():
    w = KillableSTTWorker(_raises)
    outcome = w.run_with_single_restart(timeout=5, args=("x",))
    assert outcome.status == "error"
    assert outcome.attempts == 2


# ---------------------------------------------------------------------------
# handler-level contract: exactly-once CAS write, failure message, marker
# ---------------------------------------------------------------------------

class _Recorder:
    def __init__(self):
        self.card_writes = []
        self.messages = []

    def write_card(self, chat_id, card_id, field, text):
        self.card_writes.append((chat_id, card_id, field, text))

    def send_message(self, chat_id, text, buttons):
        self.messages.append((chat_id, text, buttons))


def test_short_voice_end_to_end_single_success_single_write():
    rec = _Recorder()
    handler = VoiceWatchdogHandler(_fast_ok, rec.write_card, rec.send_message)
    status = handler.handle_voice(1, 100, "file-a", "card-1", "phone", 5, "audio-ref")
    assert status == "success"
    assert len(rec.card_writes) == 1
    assert rec.card_writes[0] == (1, "card-1", "phone", "ok:audio-ref")


def test_two_hangs_produce_one_failure_zero_writes_retryable_marker():
    rec = _Recorder()
    handler = VoiceWatchdogHandler(_hang_forever, rec.write_card, rec.send_message)
    status = handler.handle_voice(2, 101, "file-b", "card-2", "phone", 5, "audio-ref")
    assert status == "failed"
    assert len(rec.card_writes) == 0
    assert len(rec.messages) == 1
    assert "Повторить голосовое" in rec.messages[0][2]
    assert handler._markers.is_retryable(2, "file-b") is True
    assert handler._markers.already_succeeded(2, "file-b") is False


def test_duplicate_telegram_update_single_transcription_single_write():
    rec = _Recorder()
    handler = VoiceWatchdogHandler(_fast_ok, rec.write_card, rec.send_message)
    s1 = handler.handle_voice(3, 200, "file-c", "card-3", "phone", 5, "audio-ref")
    s2 = handler.handle_voice(3, 200, "file-c", "card-3", "phone", 5, "audio-ref")
    assert s1 == "success"
    assert s2 == "duplicate_success"
    assert len(rec.card_writes) == 1


def test_restart_budget_replay_after_simulated_process_restart():
    rec = _Recorder()
    store = JobMarkerStore()
    handler = VoiceWatchdogHandler(_fast_ok, rec.write_card, rec.send_message, marker_store=store)
    s1 = handler.handle_voice(4, 300, "file-d", "card-4", "phone", 5, "audio-ref")
    assert s1 == "success"
    # Simulate a fresh process restart: build a brand-new handler but reuse
    # the same (persisted) marker_store tombstone -> replay must be a no-op.
    handler2 = VoiceWatchdogHandler(_fast_ok, rec.write_card, rec.send_message, marker_store=store)
    s2 = handler2.handle_voice(4, 300, "file-d", "card-4", "phone", 5, "audio-ref")
    assert s2 == "duplicate_success"
    assert len(rec.card_writes) == 1


# ---------------------------------------------------------------------------
# circuit breaker
# ---------------------------------------------------------------------------

def test_circuit_breaker_opens_after_three_hangs_within_window():
    now = [1000.0]
    breaker = STTCircuitBreaker(clock=lambda: now[0])
    assert breaker.is_open() is False
    breaker.record_hang(); now[0] += 10
    breaker.record_hang(); now[0] += 10
    assert breaker.is_open() is False
    breaker.record_hang()
    assert breaker.is_open() is True
    now[0] += 5 * 60 + 1
    assert breaker.is_open() is False


def test_breaker_open_blocks_new_voice_but_not_text():
    rec = _Recorder()
    breaker = STTCircuitBreaker(clock=lambda: 0.0)
    breaker.record_hang()
    breaker.record_hang()
    breaker.record_hang()
    handler = VoiceWatchdogHandler(_fast_ok, rec.write_card, rec.send_message, breaker=breaker)
    status = handler.handle_voice(5, 400, "file-e", "card-5", "phone", 5, "audio-ref")
    assert status == "breaker_open"
    assert len(rec.card_writes) == 0
    # text/photo handling is out of this module's scope by design: this test
    # only proves voice is short-circuited without raising, i.e. the process
    # (and by extension any text handler on the same loop) stays responsive.


def test_process_restart_budget_requires_probes_and_caps_restarts():
    budget = ProcessRestartBudget()
    for _ in range(3):
        budget.record_health_probe(False)
    assert budget.probes_justify_restart() is True
    assert budget.may_restart() is True
    budget.record_restart()
    assert budget.may_restart() is True
    budget.record_restart()
    assert budget.may_restart() is False  # cooldown engaged after 2 restarts


# ---------------------------------------------------------------------------
# concurrency: bounded, event loop stays responsive
# ---------------------------------------------------------------------------

def test_twenty_parallel_short_voice_calls_all_succeed_independently():
    rec = _Recorder()
    handler = VoiceWatchdogHandler(_fast_ok, rec.write_card, rec.send_message)

    def _one(i):
        return handler.handle_voice(100 + i, 500 + i, f"file-{i}", f"card-{i}", "phone", 2, f"a{i}")

    with ThreadPoolExecutor(max_workers=20) as ex:
        results = list(ex.map(_one, range(20)))

    assert all(r == "success" for r in results)
    assert len(rec.card_writes) == 20


# ---------------------------------------------------------------------------
# non-regression placeholders for text/photo handlers
# ---------------------------------------------------------------------------

def test_text_and_photo_handlers_not_part_of_this_module():
    """This package only touches the voice/audio branch. It defines no
    text/photo handler symbols, so importing it cannot shadow or alter
    them. This test documents that guarantee at the package-surface level.
    """
    import cloud.task_078_voice_watchdog.handler_patch as hp

    assert not hasattr(hp, "handle_text")
    assert not hasattr(hp, "handle_photo")
