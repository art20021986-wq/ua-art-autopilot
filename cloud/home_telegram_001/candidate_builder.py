"""Build the HOME-TELEGRAM candidate from the installed sources (after HOME-ORDER-INSTALL-20261110).

ua_korea_home.py: the new version also leaves the «Написати в Telegram» button out of the home hero (and keeps
doing it at every home rewrite through site_ge_inject.inject_html); video/index.html gets it now.
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
    return {MODULE: (HERE / MODULE).read_bytes(), HOME: home.replace(pair, ua_korea_home.PICK_TO).encode('utf-8')}


def is_page(name):
    return name == HOME
