"""JAPAN-STOCK-001 step 2: the site with Japan (home titles, catalog «Выкуплены» and the country row, card texts)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'JAPAN-SITE-PREFLIGHT-20261126'
INSTALL_TASK = 'JAPAN-SITE-INSTALL-20261126'
PACKAGE = 'cloud/japan_site_001'
NEW_MODULES = ('ua_country_site.py',)
