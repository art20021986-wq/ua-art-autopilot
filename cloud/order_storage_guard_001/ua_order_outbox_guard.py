"""Short order-storage outages are logged, not reported; one report after a long outage (BOT-ORDER-STORAGE-001)."""
import logging
import time

log = logging.getLogger(__name__)
REPORT_AFTER = 300  # seconds of failures in a row before the owner is told


class OutageGuard:
    def __init__(self, report_after=REPORT_AFTER, clock=time.monotonic):
        self.report_after, self.clock = report_after, clock
        self.since, self.reported = None, False

    def failed(self):
        """Record a failed run; True exactly once per outage, when it has lasted report_after seconds."""
        now = self.clock()
        if self.since is None:
            self.since = now
        log.warning('order storage unavailable for %d s', now - self.since)
        if not self.reported and now - self.since >= self.report_after:
            self.reported = True
            return True
        return False

    def ok(self):
        self.since, self.reported = None, False
