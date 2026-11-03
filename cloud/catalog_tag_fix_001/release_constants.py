"""Catalog design guard repair (CATALOG-TAG-FIX-001); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'CATALOG-TAG-FIX-PREFLIGHT-20261103-R2'  # R1: the shell differs beyond the tag; R2 reports it
INSTALL_TASK = 'CATALOG-TAG-FIX-INSTALL-20261103'
PACKAGE = 'cloud/catalog_tag_fix_001'
