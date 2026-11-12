"""Build the KOREA-WEEK-DAYS candidate from the live page; only video/korea.html changes."""
import week_days
from release_constants import KOREA

# The page changes with other publications; it is pinned by the plan instead.
SOURCE_FILES = (KOREA,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {KOREA: week_days.build(source[KOREA].decode('utf-8')).encode('utf-8')}
