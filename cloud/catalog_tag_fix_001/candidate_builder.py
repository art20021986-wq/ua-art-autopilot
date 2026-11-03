"""Build the CATALOG-TAG-FIX-001 candidate: the live catalog_design_guard.py whose shell comparison leaves out
the site's Google tag block, and the golden catalog with the approved office map link (MAPS-LINK-001)."""
import edit_catalog_guard
import edit_golden

EDITS = {edit_catalog_guard.NAME: edit_catalog_guard.build, edit_golden.NAME: edit_golden.build}
SOURCE_FILES = tuple(EDITS)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    return {name: edit(name, source[name]) for name, edit in EDITS.items()}
