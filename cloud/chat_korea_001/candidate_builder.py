"""Build the CHAT-KOREA candidate: the Korea auctions page gets the floating «Зв'язатися з менеджером» button look
that every other page has had since CHAT-BUTTON-001 (owner «да» 2026-11-12).

Only video/korea.html changes: the same style block (ua_chat_button.HTML) before its last </body>. The style comes from
the module already installed on the server; the release refuses to build if the live module differs from this copy.
"""
import hashlib
from pathlib import Path

import ua_chat_button

PAGE = 'video/korea.html'
SOURCE_FILES = (PAGE,)
MODULE = 'ua_chat_button.py'
DEPENDENCY_SHA256 = {MODULE: hashlib.sha256((Path(__file__).resolve().parent / MODULE).read_bytes()).hexdigest()}


def apply(page):
    if ua_chat_button.MARK in page or page.count('</body>') < 1 or 'wa.me' not in page:
        raise ValueError('CHAT_KOREA_PAGE_UNEXPECTED')
    return ua_chat_button.apply(page)


def build(source, dependencies):
    if hashlib.sha256(dependencies[MODULE]).hexdigest() != DEPENDENCY_SHA256[MODULE]:
        raise ValueError('CHAT_KOREA_LIVE_MODULE_DIFFERS')
    return {PAGE: apply(source[PAGE].decode('utf-8')).encode('utf-8')}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
