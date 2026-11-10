"""Korea online auctions on the site (JPAUTO-KOREA-001): home mark and ticker slot, the Korea page with the
manager dialog, the auction enquiry in the order package, the selection page heading."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'KOREA-AUCTION-PREFLIGHT-20261110-R2'  # R1 PASS; its storage probe went stale before the install
INSTALL_TASK = 'KOREA-AUCTION-INSTALL-20261110-R2'  # R1 halted in prepare: stale storage probe (archived)
PACKAGE = 'cloud/korea_auction_001'
