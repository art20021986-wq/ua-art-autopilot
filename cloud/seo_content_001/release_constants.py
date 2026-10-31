"""SEO content release (SEO-CONTENT-001); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'SEO-CONTENT-PREFLIGHT-20261031'
INSTALL_TASK = 'SEO-CONTENT-INSTALL-20261031'
PACKAGE = 'cloud/seo_content_001'
# Installed path -> file of this package.
REPLACED_FILES = {'ua_seo_order_models.py': 'ua_seo_order_models.py'}
