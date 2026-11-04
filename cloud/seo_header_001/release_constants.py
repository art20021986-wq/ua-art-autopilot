"""Site top block on the landing pages (FINANCE-001 stage 5, SEO-HEADER-001); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'SEO-HEADER-PREFLIGHT-20261104'
INSTALL_TASK = 'SEO-HEADER-INSTALL-20261104'
PACKAGE = 'cloud/seo_header_001'
# Installed path -> file of this package.
REPLACED_FILES = {'ua_seo_header.py': 'ua_seo_header.py'}
