"""Build the CATALOG-TAG-FIX-001 candidate: the live catalog_design_guard.py whose shell comparison leaves out
the site's Google tag block."""
import edit_catalog_guard

SOURCE_FILES = (edit_catalog_guard.NAME,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {edit_catalog_guard.NAME: edit_catalog_guard.build(edit_catalog_guard.NAME, source[edit_catalog_guard.NAME])}
