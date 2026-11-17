"""Drive of a lot, only as the auction writes it (KOREA-DRIVE-001, owner 2026-11-17: «привод указывать»).

The lot page has no drive field (probe LOT-PROBE-20261117): the auction names the drive only inside the trim
(«Trim Level»: «3.8 AWD 7», «520d xDrive», «2.5 2WD 5»). Only these explicit marks are read; nothing is guessed
from the model. Keys: full, front, rear, two (2WD: one axle, the auction does not say which).
"""
import re

MARKS = (
    ('full', ('AWD', '4WD', '4X4', 'XDRIVE', '4MATIC', 'QUATTRO', 'HTRAC', 'ALL4', '4MOTION', 'E4WD')),
    ('front', ('FWD',)),
    ('rear', ('RWD',)),
    ('two', ('2WD', '4X2')),
)
_WORDS = re.compile(r'[A-Za-z0-9]+')


def key(trim):
    """The trim text -> a drive key, or None when it names no drive (or names two different ones)."""
    # BMW writes the drive and the engine as one word («xDrive40i»): its xDrive part counts.
    words = {'XDRIVE' if w.upper().startswith('XDRIVE') else w.upper() for w in _WORDS.findall(trim or '')}
    found = {name for name, marks in MARKS if words & set(marks)}
    return found.pop() if len(found) == 1 else None
