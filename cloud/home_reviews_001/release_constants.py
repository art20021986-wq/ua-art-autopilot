"""Home reviews release (AUTORIA-REVIEWS-001); no private source in this package.

Release 8 (owner 2026-11-11): the sold-cars number follows AUTO.RIA weekly (sold_loader + cloud/autoria_sold_001 job).
Release 7 (owner 2026-11-11): the official AUTO.RIA logo in the button and badge again (release 6 design kept); the
logo file video/brand/autoria-logo.svg is live since release 1 and is only checked, not written.
Release 6 (owner 2026-10-27): «AUTO.RIA» as plain text in the site's own design (site font, gold, thin frame); the
font file video/brand/roboto-700.woff2 is no longer referenced and stays on the server untouched.
Release 5 (owner 2026-10-27): the text mark «AUTO.RIA» in one colour, black, same Roboto, same white button and badge.
Release 4 (owner 2026-10-27): the text mark on white, «AUTO» red and «.RIA» blue letters, in Roboto served from
our site (new video/brand/roboto-700.woff2), the same on every device.
Release 3 (owner 2026-10-27): the AUTO.RIA logo replaced by a text mark in AUTO.RIA brand style; the old
video/brand/autoria-logo.svg is no longer referenced and stays on the server untouched.
Release 2 (owner «Ок 1.2», 2026-10-26): Georgian texts and the «autoria_click» Analytics event.
Release 1: HOME-REVIEWS-PREFLIGHT-20261026-R2 / HOME-REVIEWS-INSTALL-20261026 (block, badge, logo).
"""
# Release 2 ran as HOME-REVIEWS-KA-PREFLIGHT-20261026-R2 / HOME-REVIEWS-KA-INSTALL-20261026-R2,
# release 3 as HOME-REVIEWS-MARK-PREFLIGHT-20261027 / HOME-REVIEWS-MARK-INSTALL-20261027,
# release 4 as HOME-REVIEWS-FONT-PREFLIGHT-20261027 / HOME-REVIEWS-FONT-INSTALL-20261027,
# release 5 as HOME-REVIEWS-BLACK-PREFLIGHT-20261027 / HOME-REVIEWS-BLACK-INSTALL-20261027,
# release 6 as HOME-REVIEWS-OWN-PREFLIGHT-20261027 / HOME-REVIEWS-OWN-INSTALL-20261027,
# release 7 as HOME-REVIEWS-LOGO-PREFLIGHT-20261111 / HOME-REVIEWS-LOGO-INSTALL-20261111.
PREVIEW_TASK = 'HOME-REVIEWS-SOLD-PREFLIGHT-20261111-R5'  # R2-R4 never ran (queue cancel, suffix not in the package, R3 lock)
INSTALL_TASK = 'HOME-REVIEWS-SOLD-INSTALL-20261111'
PACKAGE = 'cloud/home_reviews_001'
HOME = 'video/index.html'
