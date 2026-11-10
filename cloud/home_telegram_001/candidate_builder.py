"""Build the HOME-TELEGRAM candidate from the installed sources (after HOME-ORDER-INSTALL-20261110).

ua_korea_home.py: the new version also leaves the «Написати в Telegram» button out of the home hero and names the
auctions block button «Дивитися аукціони» (and keeps doing it at every home rewrite through
site_ge_inject.inject_html); video/index.html gets it now.
"""
from pathlib import Path

import ua_korea_home

HERE = Path(__file__).resolve().parent
HOME = 'video/index.html'
MODULE = 'ua_korea_home.py'
SOURCE_FILES = (MODULE, HOME)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    installed = source[MODULE].decode('utf-8')
    if 'ORDER = (' not in installed or 'TELEGRAM' in installed:
        raise ValueError('HOME_TELEGRAM_MODULE_UNEXPECTED')
    home = source[HOME].decode('utf-8')
    pair = ua_korea_home.PICK_TO + ua_korea_home.TELEGRAM
    if ua_korea_home.LAYOUT not in home or home.count(pair) != 1:
        raise ValueError('HOME_TELEGRAM_HOME_UNEXPECTED')
    if home.count(ua_korea_home.GO_FROM) != 1:
        raise ValueError('HOME_TELEGRAM_BUTTON_UNEXPECTED')
    new = home.replace(pair, ua_korea_home.PICK_TO).replace(ua_korea_home.GO_FROM, ua_korea_home.GO_TO)
    return {MODULE: (HERE / MODULE).read_bytes(), HOME: new.encode('utf-8')}


def is_page(name):
    return name == HOME
