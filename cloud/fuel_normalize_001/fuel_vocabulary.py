"""The owner's fuel vocabulary (2026-10-22): дизель, газ, LPI, бензин."""
SPELLINGS = {
    'дизель': ('дизель', 'дізель', 'diesel'),
    'газ': ('газ', 'gas', 'lpg'),
    'LPI': ('lpi', 'лпи', 'лпі'),
    'бензин': ('бензин', 'petrol', 'gasoline'),
}
CANONICAL = {spelling: name for name, spellings in SPELLINGS.items() for spelling in spellings}


def normalize(value):
    """The canonical fuel for a known spelling (any case, outer spaces), else None."""
    if not isinstance(value, str):
        return None
    return CANONICAL.get(' '.join(value.split()).casefold())
