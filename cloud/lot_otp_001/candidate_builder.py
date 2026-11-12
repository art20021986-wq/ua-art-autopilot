"""Build the LOT-OTP candidate from the live Korea page; only video/korea.html changes."""
import edit_korea
from release_constants import KOREA

SOURCE_FILES = (KOREA,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {KOREA: edit_korea.build(source[KOREA])}
