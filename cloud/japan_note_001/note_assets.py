"""Look of the card note (JAPAN-NOTE-001), published as /video/order/model-note.css.

Kept as text in a Python module because the release pipeline ships only Python files (as gallery_assets.py).
The note spans the whole card, under the photo and buttons: a column card on wide screens; on phones the row card
wraps it to a new line and the gallery grid gives it the full row (both as in order.css / gallery.css, ≤640px).
"""
FILES = {
    'video/order/model-note.css': (
        '.ua-order .model > .model-note{margin:0 12px 12px;padding:8px 10px;border-left:3px solid #f0a63c;'
        'border-radius:6px;background:rgba(240,166,60,.08);font-size:13px;line-height:1.4;color:#e8eef8}\n'
        '@media(max-width:640px){'
        '.ua-order .model:has(> .model-note){flex-wrap:wrap}'
        '.ua-order .model > .model-note{box-sizing:border-box;width:calc(100% - 24px)}'
        '.ua-order .model:has(> .model-media > .gallery) > .model-note{grid-column:1 / -1;width:auto;margin:0}}\n'),
}
