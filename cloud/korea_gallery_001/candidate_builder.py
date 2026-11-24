"""Build the KOREA-GALLERY candidate (owner 2026-11-13): the Korea lot window shows its photos as the catalogue car
cards do — a large photo, a thumbnail strip, arrows, swipe, keyboard, «Фото N / M» (lot_gallery_page).
Nothing else in video/korea.html changes.
"""
import lot_gallery_page

PAGE = 'video/korea.html'
SOURCE_FILES = (PAGE,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {PAGE: lot_gallery_page.build(source[PAGE])}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
