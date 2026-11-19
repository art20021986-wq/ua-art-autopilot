"""Body colour of a lot, as the lot page writes it (KOREA-DRIVE-001 package, owner 2026-11-17: a colour filter).

The lot page text gives «… Color <value> Mileage …» (empty value: «Color Mileage»; lots.parse_detail reads it).
The words are mapped to a few families; a value naming none or several of them is «other»; empty is None.
"""
import re

FAMILIES = (
    ('white', ('WHITE', 'PEARL', 'IVORY')),
    ('black', ('BLACK',)),
    ('gray', ('GRAY', 'GREY', 'GUN', 'GUNMETAL', 'CHARCOAL')),
    ('silver', ('SILVER',)),
    ('blue', ('BLUE', 'NAVY')),
    ('red', ('RED', 'WINE', 'BURGUNDY')),
    ('brown', ('BROWN',)),
    ('beige', ('BEIGE',)),
    ('green', ('GREEN', 'KHAKI')),
    ('yellow', ('YELLOW',)),
    ('orange', ('ORANGE',)),
)
_WORDS = re.compile(r'[A-Za-z]+')


def key(value):
    """The page's colour text -> a family key, 'other', or None when the page gives no colour."""
    words = {w.upper() for w in _WORDS.findall(value or '')}
    if not (value or '').strip():
        return None
    found = [name for name, marks in FAMILIES if words & set(marks)]
    return found[0] if len(found) == 1 else 'other'
