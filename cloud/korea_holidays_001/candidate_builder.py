"""Build the KOREA-HOLIDAYS candidate (owner 2026-11-17): the Korea page day buttons say why a day has no lots —
the holiday name (korea_holidays) or «Вихідний» on Saturday/Sunday — instead of «0 авто» (day_reason_page).
Nothing else in video/korea.html changes.
"""
import day_reason_page

PAGE = 'video/korea.html'
SOURCE_FILES = (PAGE,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {PAGE: day_reason_page.build(source[PAGE])}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
