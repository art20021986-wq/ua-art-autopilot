"""Isolated fake collectors for the scheduler's process-boundary tests."""
import time


def partial_then_stall(card, request_timeout, emit):
    emit("nhtsa_vpic", {"status": "FRESH", "facts": 1}, [{"field_key": "fake_test_key", "display_value": "1"}])
    time.sleep(20)


def complete(card, request_timeout, emit):
    return {"facts": [], "sources": {"nhtsa_vpic": {"status": "NO_CONFIDENT_MATCH"}}}


def failing(card, request_timeout, emit):
    raise RuntimeError("synthetic failure")
