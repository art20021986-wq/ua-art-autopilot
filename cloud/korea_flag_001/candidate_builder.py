"""Build the KOREA-FLAG candidate from the installed sources (after KOREA-AUCTION-INSTALL-20261110-R3).

ua_korea_home.py: the new version also switches the Korea flag link to korea.html (and keeps doing it at every
home rewrite through site_ge_inject.inject_html); video/index.html gets the switch now. Nothing else changes.
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
    if 'FLAG_TO' in installed or 'ua-korea-ticker' not in installed:
        raise ValueError('KOREA_FLAG_MODULE_UNEXPECTED')
    home = source[HOME].decode('utf-8')
    if ua_korea_home.MARK not in home or home.count(ua_korea_home.FLAG_FROM) != 1:
        raise ValueError('KOREA_FLAG_HOME_UNEXPECTED')
    return {MODULE: (HERE / MODULE).read_bytes(),
            HOME: home.replace(ua_korea_home.FLAG_FROM, ua_korea_home.FLAG_TO).encode('utf-8')}


def is_page(name):
    return name == HOME
