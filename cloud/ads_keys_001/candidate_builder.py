"""Build the ADS-KEYS-001 candidate from the live sources (owner «Да» 2026-11-25, tasks/ADS-API-001.md).

- new: ua_google_ads_auth.py (keys file, consent link, code exchange), ua_google_ads_key.py (CRM bot: the keys
  message), ua_google_ads_oauth_web.py (site: GET /api/google-ads/oauth);
- cars_ui.py: one block at the end that registers the bot handler;
- ua_order/host.py: one guarded mount of the callback in front of the site.
Nothing else changes; every edit of a live file must match exactly once.
"""
from pathlib import Path

import edit_cars_ui
import edit_order_host

HERE = Path(__file__).resolve().parent
NEW_FILES = ('ua_google_ads_auth.py', 'ua_google_ads_key.py', 'ua_google_ads_oauth_web.py')
SOURCE_FILES = (edit_cars_ui.NAME, edit_order_host.NAME)
DEPENDENCY_SHA256 = {}


def build(source, dependencies=None):
    if set(source) != set(SOURCE_FILES):
        raise ValueError('UNPLANNED')
    candidate = {name: (HERE / name).read_bytes() for name in NEW_FILES}
    candidate[edit_cars_ui.NAME] = edit_cars_ui.build(source[edit_cars_ui.NAME])
    candidate[edit_order_host.NAME] = edit_order_host.build(source[edit_order_host.NAME])
    return candidate
