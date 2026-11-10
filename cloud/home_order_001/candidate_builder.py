"""Build the HOME-ORDER candidate from the installed sources (after KOREA-FLAG-INSTALL-20261110).

ua_korea_home.py: the new version also orders the home page (auctions block, ticker, individual order, cars in stock,
the rest) and keeps doing it at every home rewrite through site_ge_inject.inject_html; video/index.html gets it now.
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
    if 'FLAG_TO' not in installed or 'LAYOUT' in installed:
        raise ValueError('HOME_LAYOUT_MODULE_UNEXPECTED')
    home = source[HOME].decode('utf-8')
    if home.count(ua_korea_home.FLAG_TO) != 1 or ua_korea_home.LAYOUT in home:
        raise ValueError('HOME_LAYOUT_HOME_UNEXPECTED')
    new = ua_korea_home.apply(home)
    if new.count(ua_korea_home.LAYOUT) != 1:
        raise ValueError('HOME_LAYOUT_STRUCTURE_UNKNOWN')
    return {MODULE: (HERE / MODULE).read_bytes(), HOME: new.encode('utf-8')}


def is_page(name):
    return name == HOME
