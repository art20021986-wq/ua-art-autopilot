"""Look of the card price line (KOREA-JAPAN-PRICE-001), published as /video/order/model-price.css.

Kept as text in a Python module because the release pipeline ships only Python files (as note_assets.py).
Placed like the card note (model-note.css): the whole card width, under the photo and buttons, above a note.
"""
FILES = {
    'video/order/model-price.css': (
        '.ua-order .model > .model-price{margin:0 12px 12px;padding:8px 10px;border-left:3px solid #4cc27a;'
        'border-radius:6px;background:rgba(76,194,122,.12);font-size:14px;font-weight:600;line-height:1.4;color:#e8eef8}\n'
        '@media(max-width:640px){'
        '.ua-order .model:has(> .model-price){flex-wrap:wrap}'
        '.ua-order .model > .model-price{box-sizing:border-box;width:calc(100% - 24px)}'
        '.ua-order .model:has(> .model-media > .gallery) > .model-price{grid-column:1 / -1;width:auto;margin:0}}\n'),
}
