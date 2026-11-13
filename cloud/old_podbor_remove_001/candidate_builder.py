"""Build the OLD-PODBOR-REMOVE-001 candidate: the abandoned old order page video/order/podbor.html is removed.

The page is the old stand-alone order form (title «Авто під замовлення», main#ua-order, order.js beside it; in a browser
it shows «Форма тимчасово недоступна»); video/podbor.html replaced it. ANALYTICS-AUDIT-PROBE-20261113: no request to it in
10 days of the access log and no public page links to it. order.js / order.css stay (the current page uses them).
"""
OLD_PAGE = 'video/order/podbor.html'
# Its own markup (the browser texts are drawn by order.js and are not in the file; R1 refused on them).
MARKS = ('<title>Авто під замовлення — UA ART COMPANY</title>', 'id="ua-order"', 'src="order.js?v=')
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
