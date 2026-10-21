"""Read-only CRM list helpers for UA-ART-CRM-DELETE-RECOVERY-002.

The CRM supplies the rows; a verified catalog supplies only a site-status hint.
No writes, imports from the production application, or background jobs occur here.
"""


def stable_catalog_ids(path, parse_catalog):
    """Reject an unavailable, malformed or concurrently replaced catalog."""
    before = path.stat()
    source = path.read_text(encoding="utf-8")
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if tuple(getattr(before, key) for key in fields) != tuple(
            getattr(after, key) for key in fields):
        raise ValueError("Catalog changed while reading")
    ids = parse_catalog(source)
    if isinstance(ids, (str, bytes, dict)):
        raise ValueError("Invalid catalog identity collection")
    ids = frozenset(ids)
    if not all(isinstance(value, str) and value for value in ids):
        raise ValueError("Invalid catalog identity")
    return ids


def partition_crm_cards(cards, catalog_ids):
    """Never manufacture CRM cards for orphan catalog IDs."""
    groups = {"catalog": [], "unpublished": []}
    for card in cards:
        # A malformed row is retained so the UI can identify the problem without
        # suppressing otherwise valid CRM rows.
        try:
            number = card.get("auto_number")
            published = isinstance(number, str) and number in catalog_ids
        except (AttributeError, TypeError):
            published = False
        groups["catalog" if published else "unpublished"].append(card)
    return groups
