"""Fuel type of a lot: the lot page's text ('Gasoline', 'Gasoline+Electric', 'Diesel', 'LPG' ...) -> one key.

Keys: gasoline, diesel, hybrid, electric, lpg, hydrogen. One responsibility, shared by the ticker and the lot list.
"""


def key(value):
    """The lot page's fuel text -> a fuel key, or None when it names no known fuel."""
    v = (value or '').lower()
    if 'hydrogen' in v:
        return 'hydrogen'
    if 'electric' in v:
        return 'hybrid' if ('gasoline' in v or 'diesel' in v or 'hybrid' in v or 'lpg' in v) else 'electric'
    if 'hybrid' in v:
        return 'hybrid'
    for name in ('diesel', 'lpg', 'gasoline'):
        if name in v:
            return name
    return 'gasoline' if 'petrol' in v else None
