"""UA-BOT-GUARD-001: may this request write to the own counter (/ua/a/e)? No I/O, standard library only.

Not recorded: requests whose browser line names a robot or an automation tool, and events beyond LIMIT per
minute from one address (a person sends a few per page). Search engines, ads checks and Google Analytics never
reach this module: it is asked only by the counter's event endpoint.
"""
from collections import OrderedDict
import re
from threading import Lock
import time

# «Cubot» is a phone brand, not a robot.
ROBOT = re.compile(r'(?<!cu)bot|crawl|spider|slurp|headless|phantom|selenium|puppeteer|playwright|lighthouse|'
                   r'python|curl|wget|httpclient|okhttp|go-http|libwww|scrapy|axios|node-fetch', re.I)
LIMIT = 120     # events per address per WINDOW seconds
WINDOW = 60
CAPACITY = 4096  # addresses kept per web worker; the oldest are forgotten first


class Limiter:
    """Fixed-window counter per key, bounded and thread-safe, per process."""

    def __init__(self, limit=LIMIT, seconds=WINDOW, capacity=CAPACITY, clock=time.monotonic):
        self.limit, self.seconds, self.capacity, self.clock = limit, seconds, capacity, clock
        self._entries = OrderedDict()
        self._lock = Lock()

    def allow(self, key):
        now = self.clock()
        with self._lock:
            start, count = self._entries.pop(key, (now, 0))
            if now - start >= self.seconds:
                start, count = now, 0
            count += 1
            self._entries[key] = (start, count)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)
            return count <= self.limit


_LIMITER = Limiter()


def address(environ):
    """The visitor's address: PythonAnywhere passes it in X-Real-IP."""
    return environ.get('HTTP_X_REAL_IP') or environ.get('REMOTE_ADDR') or ''


def is_robot(agent):
    return not agent or bool(ROBOT.search(agent))


def allow(environ, limiter=_LIMITER):
    return not is_robot(environ.get('HTTP_USER_AGENT', '')) and limiter.allow(address(environ))
