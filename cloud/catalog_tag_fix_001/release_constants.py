"""Catalog design guard repair (CATALOG-TAG-FIX-001); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'CATALOG-TAG-FIX-PREFLIGHT-20261103-R4'  # R1/R2 map link; R3 the live file is regenerated from the golden shell
INSTALL_TASK = 'CATALOG-TAG-FIX-INSTALL-20261103'
PACKAGE = 'cloud/catalog_tag_fix_001'
