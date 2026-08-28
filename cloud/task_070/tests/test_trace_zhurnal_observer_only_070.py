"""Gate A: trace_zhurnal_070 candidate must not mutate timeout/pragma and
must never swallow exceptions.
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "candidate"))
from trace_zhurnal import _Obertka, _ua_connect  # noqa: E402


def test_ua_connect_does_not_inject_timeout():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "t.db")
        conn = _ua_connect(db_path, timeout=0.05)
        # sqlite3.Connection does not directly expose 'timeout' post-hoc,
        # so we validate behaviourally: caller-specified short timeout is
        # respected by attempting a lock contention and expecting a fast
        # OperationalError rather than a long stall.
        conn2 = sqlite3.connect(db_path, timeout=0.05)
        conn2.execute("BEGIN EXCLUSIVE")
        import time
        t0 = time.monotonic()
        try:
            conn.execute("BEGIN IMMEDIATE")
            raised = False
        except sqlite3.OperationalError:
            raised = True
        dt = time.monotonic() - t0
        conn2.execute("COMMIT")
        conn2.close()
        conn.close()
        assert raised is True
        assert dt < 1.0, "trace_zhurnal_070 must not escalate the caller's short timeout"


def test_obertka_never_swallows_exceptions():
    class Boom(Exception):
        pass

    raised = False
    try:
        with _Obertka(label="test"):
            raise Boom("synthetic")
    except Boom:
        raised = True
    assert raised is True, "_Obertka must never suppress exceptions"
