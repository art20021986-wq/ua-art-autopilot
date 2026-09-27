import contextlib
import copy
import time

import inspect
import pathlib
import tempfile
import unittest

from spec_retry84 import APPROVED_SOURCES, Queue, Runtime, blank_outcomes, collect_bounded


CARD = {"car_uid": "UA-0017", "vin": "WAUZZZ4G3GN081840", "published": True}


def empty_collect(*args, **kwargs):
    return {"facts": [], "sources": blank_outcomes(["nhtsa_vpic"], "EMPTY"), "collection_error": None}


def runtime(queue, card, collect=empty_collect, commits=None, clock=lambda: 100):
    commits = commits if commits is not None else []
    return Runtime(queue, read_card=lambda uid: card, collector="spec84_test_adapters:complete",
                   connected_sources=["nhtsa_vpic"], commit_guard=lambda uid: contextlib.nullcontext(),
                   commit=lambda c, g, f, o: commits.append((g, copy.deepcopy(f))) or {"written": len(f)},
                   clock=clock, collect_fn=collect)


def test_four_slots_and_stage_or_repeat_events_never_reset(queue):
    first = queue.ensure_cycle(CARD, now=100)
    changed = dict(CARD, stage="В Киеве", price=9900)
    repeated = queue.ensure_cycle(changed, now=777)
    assert repeated["id"] == first["id"]
    assert [r["due_at"] for r in queue.report()["slots"]] == [100, 700, 1300, 1900]
    assert len(queue.report()["cycles"]) == 1


def test_drafts_never_schedule_or_publish(queue, status):
    assert queue.ensure_cycle(dict(CARD, published=status), now=100) is None
    assert not queue.report()["slots"]


def test_restart_reclaims_same_slot_not_new_logical_attempt(queue):
    queue.ensure_cycle(CARD, now=100)
    crashed = queue.claim(now=100, lease_seconds=20)
    restarted = Queue(queue.path)
    assert restarted.claim(now=119) is None
    reclaimed = restarted.claim(now=121)
    assert (reclaimed["cycle_id"], reclaimed["slot"]) == (crashed["cycle_id"], crashed["slot"])
    assert reclaimed["token"] != crashed["token"]
    assert not restarted.lease_valid(crashed, now=121)
    row = restarted.report()["slots"][0]
    assert row["runs"] == 2 and row["first_started_at"] == 100 and row["due_at"] == 100
    assert len(restarted.report()["slots"]) == 4


def test_empty_slots_all_finish_without_canceling_three_repeats(queue):
    queue.ensure_cycle(CARD, now=100)
    clock = [100]
    commits = []
    rt = runtime(queue, CARD, commits=commits, clock=lambda: clock[0])
    for now in (100, 700, 1300, 1900):
        clock[0] = now
        job = queue.claim(now=now)
        assert rt.execute(job) == "DONE"
        assert queue.claim(now=now) is None
    report = queue.report()
    assert len(commits) == 4 and all(facts == [] for _, facts in commits)
    assert len(report["sources"]) == 40
    assert report["cycles"][0]["state"] == "COMPLETE"
    assert queue.claim(now=1000000) is None
    rt.close()


def test_expired_claim_cannot_finish_after_reclaim(queue):
    queue.ensure_cycle(CARD, now=100)
    old = queue.claim(now=100, lease_seconds=1)
    new = queue.claim(now=102)
    assert not queue.finish(old, blank_outcomes(), {}, now=102)
    assert queue.finish(new, blank_outcomes(), {}, now=102)


def test_overdue_recovery_is_ordered_and_one_running_slot_per_cycle(queue):
    queue.ensure_cycle(CARD, now=100)
    for expected in range(4):
        job = queue.claim(now=4000)
        assert job["slot"] == expected
        assert queue.claim(now=4000) is None
        assert queue.finish(job, blank_outcomes(), {}, now=4000)
    assert queue.claim(now=4000) is None


def test_vin_changes_generation_and_never_reuses_returning_vin(queue):
    first = queue.ensure_cycle(CARD, now=100)
    old = queue.claim(now=100)
    second = queue.ensure_cycle(dict(CARD, vin="WAUZZZ4G3GN081841"), now=200)
    third = queue.ensure_cycle(CARD, now=300)
    assert [first["generation"], second["generation"], third["generation"]] == [1, 2, 3]
    assert not queue.lease_valid(old, now=101)
    assert len(queue.report()["slots"]) == 12


def test_late_result_never_writes_changed_vin_or_unpublished_card(queue, mutation):
    card = dict(CARD)
    queue.ensure_cycle(card, now=100)
    job = queue.claim(now=100)
    calls = []
    def delayed_collect(*args, **kwargs):
        card.update(mutation)
        return dict(empty_collect(), facts=[{"field_key": "engine_type", "display_value": "wrong old VIN"}])
    rt = runtime(queue, card, collect=delayed_collect, commits=calls)
    assert rt.execute(job) == "STALE_OR_UNPUBLISHED"
    assert not calls
    assert len(queue.report()["sources"]) == 10
    rt.close()


def test_republished_same_vin_resumes_without_restarting_schedule(queue):
    queue.ensure_cycle(CARD, now=100)
    job = queue.claim(now=100)
    queue.pause(job)
    queue.ensure_cycle(CARD, now=555)
    report = queue.report()
    assert len(report["cycles"]) == 1 and report["cycles"][0]["state"] == "ACTIVE"
    assert [s["due_at"] for s in report["slots"]] == [100, 700, 1300, 1900]


def test_collection_has_hard_deadline_and_retains_partial_results():
    started = time.monotonic()
    result = collect_bounded(CARD, "spec84_test_adapters:partial_then_stall",
                             ["nhtsa_vpic", "danawa"], seconds=0.5)
    assert time.monotonic() - started < 2
    assert result["collection_error"] == "TIMEOUT"
    assert result["sources"]["nhtsa_vpic"]["status"] == "FRESH"
    assert result["sources"]["danawa"]["status"] == "TIMEOUT"
    assert result["sources"]["kia_korea"]["status"] == "NOT_CONNECTED"
    assert set(result["sources"]) == set(APPROVED_SOURCES) and len(result["facts"]) == 1


def test_collector_errors_have_ten_honest_outcomes():
    result = collect_bounded(CARD, "spec84_test_adapters:failing", ["nhtsa_vpic"], seconds=2)
    assert result["sources"]["nhtsa_vpic"]["status"] == "ERROR"
    assert len(result["sources"]) == 10 and not result["facts"]


def test_outcome_registry_cannot_be_silently_replaced(queue):
    queue.ensure_cycle(CARD, now=100)
    job = queue.claim(now=100)
    with unittest.TestCase().assertRaisesRegex(ValueError, "EXACT_APPROVED_TEN"):
        queue.finish(job, {"carwiki.co.kr": {"status": "PASS"}}, {}, now=100)


def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite()
    parameters = {
        "test_drafts_never_schedule_or_publish": [{"status": x} for x in [False, 0, "0", "false", ""]],
        "test_late_result_never_writes_changed_vin_or_unpublished_card": [
            {"mutation": {"vin": "WAUZZZ4G3GN081841"}}, {"mutation": {"published": False}}],
    }
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            for case in parameters.get(name, [{}]):
                def run_case(fn=fn, case=case):
                    with tempfile.TemporaryDirectory() as directory:
                        args = dict(case)
                        if "queue" in inspect.signature(fn).parameters:
                            args["queue"] = Queue(pathlib.Path(directory) / "schedule.db")
                        fn(**args)
                suite.addTest(unittest.FunctionTestCase(run_case, description=name + " " + repr(case)))
    return suite


if __name__ == "__main__":
    unittest.main(verbosity=2)
