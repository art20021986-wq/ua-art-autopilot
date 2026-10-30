"""Build the W245 card candidate: the order.js version on the page, the card's gallery entry and its new photos."""
import base64

import asset_version
import card
import w245_assets

# Live files are pinned by the plan.
SOURCE_FILES = (asset_version.PAGE, card.DATA)
OWN_FILES = ()
DEPENDENCY_SHA256 = {}


def photos():
    return {path: base64.b64decode(text) for path, text in w245_assets.FILES.items()}


def build(source, dependencies):
    result = {asset_version.PAGE: asset_version.build(source[asset_version.PAGE]),
              card.DATA: card.build(source[card.DATA], w245_assets.ENTRY)}
    result.update(photos())
    return result
