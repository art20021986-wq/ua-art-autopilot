"""Build the OLD-PODBOR-REMOVE-001 candidate: the abandoned old order page video/order/podbor.html is removed.

The page («Форма тимчасово недоступна», no menu, no countries) was replaced by video/podbor.html; ANALYTICS-AUDIT-PROBE-
20261113: no request to it in 10 days of the access log and no public page links to it. Nothing else changes.
"""
OLD_PAGE = 'video/order/podbor.html'
MARKS = ('Індивідуальне замовлення автомобіля', 'Форма тимчасово недоступна')
DEPENDENCY_SHA256 = {}


def targets(root):
    return (OLD_PAGE,)


def build(source, dependencies):
    """{OLD_PAGE: None}: only the abandoned page itself, recognised by its own texts."""
    text = source[OLD_PAGE].decode('utf-8', 'replace')
    if not all(mark in text for mark in MARKS):
        raise ValueError('OLD_PAGE_NOT_RECOGNISED')
    return {OLD_PAGE: None}


def is_page(name):
    return False  # the removed page is never accepted as rewritten
