"""Korea online auctions on the site (JPAUTO-KOREA-001): home mark and ticker slot, the Korea page with the
manager dialog, the auction enquiry in the order package, the selection page heading."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'KOREA-AUCTION-PREFLIGHT-20261110-R3'  # R2 PASS; R2 install RESOURCE_BUSY (R1 claim not closed)
INSTALL_TASK = 'KOREA-AUCTION-INSTALL-20261110-R3'  # R1 halted (stale probe), R2 RESOURCE_BUSY at intake
PACKAGE = 'cloud/korea_auction_001'
