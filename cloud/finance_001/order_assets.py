"""Look of the order page «Кредити та лізинг» link (FINANCE-001), published as /video/order/finance-link.css.

Kept as text in a Python module because the release pipeline ships only Python files (as price_assets.py).
The link carries the site's own .button class (order.css: the gold button look); this file gives it the
place and size the card's calculate button had: full width under «Отримати пропозицію…», and on phones the
same slot in the photo-and-buttons grid of gallery cards (gallery.css), with the offer button above it.
"""
FILES = {
    'video/order/finance-link.css': (
        '.ua-order .model .finance-link{display:flex;align-items:center;justify-content:center;box-sizing:border-box;'
        'width:100%;margin-top:0}\n'
        '@media(max-width:640px){'
        '.ua-order .model .finance-link{padding:9px}'
        # The offer button is now the card's only <button>: gallery.css's :only-of-type rule would stretch it over
        # both rows, so it is put back in its own row (selector one pseudo-class stronger than that rule).
        '.ua-order .model:has(> .model-media > .gallery) .model-info > button.quick-offer:only-of-type{grid-row:2;align-self:auto}'
        '.ua-order .model:has(> .model-media > .gallery) .model-info > .finance-link{grid-column:2;grid-row:3;'
        'padding:6px 8px;font-size:13px;line-height:1.3}}\n'),
}
