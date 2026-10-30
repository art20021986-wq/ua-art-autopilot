"""Order page asset version (MODEL-GALLERY-W245): a new order.js version on video/podbor.html.

order.js loads model-gallery.json with its own version query, so the raised version makes browsers read the new
gallery data instead of a cached copy. order.js itself and the other page files stay as they are.
"""
import re

VERSION = '20261030.1'
PAGE = 'video/podbor.html'
SCRIPT_TAG = re.compile(r'order/order\.js\?v=[0-9.]+')
CHECK_PAGE = 'order/order.js?v=' + VERSION


def build(source):
    text = source.decode('utf-8')
    if len(SCRIPT_TAG.findall(text)) != 1 or CHECK_PAGE in text:
        raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + PAGE)
    return SCRIPT_TAG.sub(CHECK_PAGE, text).encode('utf-8')
