"""Drive of a lot, only as the auction writes it (KOREA-DRIVE-001, owner 2026-11-17: «привод указывать»).

The lot page has no drive field (probe LOT-PROBE-20261117): the auction names the drive only inside the trim
(«Trim Level»: «3.8 AWD 7», «520d xDrive», «2.5 2WD 5»). The explicit marks come first. Without them, models sold
in Korea with front-wheel drive only, in every version (FRONT_ONLY, owner «да» 17.11 to the model list), are «front»;
any model that also comes with all-wheel drive (Grandeur, K5, Tucson, Santa Fe, Genesis …) is left out — nothing is
guessed. Keys: full, front, rear, two (2WD: one axle, the auction does not say which).
"""
import re

MARKS = (
    ('full', ('AWD', '4WD', '4X4', 'XDRIVE', '4MATIC', 'QUATTRO', 'HTRAC', 'ALL4', '4MOTION', 'E4WD')),
    ('front', ('FWD',)),
    ('rear', ('RWD',)),
    ('two', ('2WD', '4X2')),
)
_WORDS = re.compile(r'[A-Za-z0-9]+')
# Lot titles (collect.display_name) of front-wheel-drive-only models of the Korean market.
FRONT_ONLY = frozenset((
    'Hyundai Avante', 'Hyundai Accent', 'Hyundai i30', 'Hyundai i40', 'Hyundai Casper', 'Hyundai Venue',
    'Hyundai Veloster', 'Hyundai Ioniq', 'Hyundai Sonata',
    'Kia Morning', 'Kia Ray', 'Kia K3', 'Kia K7', 'Kia Forte', 'Kia Pride', 'Kia Stonic', 'Kia Niro', 'Kia Niro Plus',
    'Kia Carens', 'Kia Carnival', 'Kia Soul',
    'Chevrolet Spark', 'Chevrolet Matiz', 'Chevrolet Aveo', 'Chevrolet Cruze', 'Chevrolet Malibu', 'Chevrolet Volt',
    'Renault SM3', 'Renault SM5', 'Renault SM6', 'Renault SM7', 'Renault Clio', 'Renault XM3', 'Renault QM3',
    'Renault Zoe',
))


def key(trim, title=''):
    """The trim text (then the lot title) -> a drive key, or None when neither names one (or the trim names two)."""
    # BMW writes the drive and the engine as one word («xDrive40i»): its xDrive part counts.
    words = {'XDRIVE' if w.upper().startswith('XDRIVE') else w.upper() for w in _WORDS.findall(trim or '')}
    found = {name for name, marks in MARKS if words & set(marks)}
    if title in FRONT_ONLY and found <= {'two', 'front'}:
        return 'front'  # no mark, or 2WD of a front-wheel-drive-only model
    return found.pop() if len(found) == 1 else None
