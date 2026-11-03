"""Card publication check repair (CARD-CANONICAL-FIX-001); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'CARD-CANONICAL-FIX-PREFLIGHT-20261103-R4'  # R1 exec in a test; R2 smoke scope; R3 lock of R2, request consumed
INSTALL_TASK = 'CARD-CANONICAL-FIX-INSTALL-20261103'
PACKAGE = 'cloud/card_canonical_fix_001'
