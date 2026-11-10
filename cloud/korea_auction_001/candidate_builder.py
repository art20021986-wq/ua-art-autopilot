"""Build the JPAUTO-KOREA-001 site candidate from the exact installed sources (owner 2026-11-10).

- ua_korea_home.py (new) + site_ge_inject.inject_html: the home page keeps the «● Аукціони онлайн» mark and the
  ticker slot at every rewrite; video/index.html gets them now.
- video/korea.html (new): the Korea online auctions page, built from the live home page layout.
- ua_order/auction.py (new) + contract.py / crm.py hand-offs: the auction access enquiry (auction.v1).
- video/order/quick-lead.js: the shared «Зв'язатися з менеджером» dialog opens from the Korea page buttons.
- video/order/order-strings.json: the selection page heading «Індивідуальне замовлення автомобіля».
"""
from pathlib import Path

import edit_intake
import edit_order_strings
import edit_quick_js
import ua_korea_home
import ua_korea_page

HERE = Path(__file__).resolve().parent
HOME = 'video/index.html'
PAGE = 'video/korea.html'
INJECT = 'site_ge_inject.py'
SOURCE_FILES = (INJECT, HOME, edit_quick_js.PATH, edit_order_strings.PATH) + tuple(edit_intake.EDITS)
DEPENDENCY_SHA256 = {}
NEW_FILES = {'ua_korea_home.py': 'ua_korea_home.py', 'ua_order/auction.py': 'auction.py'}
HOOK = ('\n\n# JPAUTO-KOREA-001: the Korea online auctions mark and ticker slot on the home page.\n'
        '_ua_korea_base_inject = inject_html\n'
        'def inject_html(source):\n'
        '    import ua_korea_home\n'
        '    return ua_korea_home.apply(_ua_korea_base_inject(source))\n')


def inject(value):
    text = value.decode('utf-8')
    if 'JPAUTO-KOREA-001' in text or 'def inject_html(' not in text:
        raise ValueError('KOREA_INJECT_HOOK')
    return (text.rstrip('\n') + HOOK).encode('utf-8')


def build(source, dependencies):
    """{installed path: new bytes}."""
    home = source[HOME].decode('utf-8')
    new_home = ua_korea_home.apply(home)
    if new_home == home:
        raise ValueError('KOREA_HOME_UNCHANGED')
    result = {target: (HERE / name).read_bytes() for target, name in NEW_FILES.items()}
    result[INJECT] = inject(source[INJECT])
    result[HOME] = new_home.encode('utf-8')
    result[PAGE] = ua_korea_page.build(home).encode('utf-8')
    result[edit_quick_js.PATH] = edit_quick_js.build(source[edit_quick_js.PATH])
    result[edit_order_strings.PATH] = edit_order_strings.build(source[edit_order_strings.PATH])
    result.update({name: edit_intake.build(name, source[name]) for name in edit_intake.EDITS})
    return result


def is_page(name):
    """The home page may be rewritten by the CRM sync after the install; it then still carries the mark."""
    return name == HOME
