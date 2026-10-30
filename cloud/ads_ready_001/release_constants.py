"""Google Ads readiness release (ADS-READY-001); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'ADS-READY-PREFLIGHT-20261030'
INSTALL_TASK = 'ADS-READY-INSTALL-20261030'
PACKAGE = 'cloud/ads_ready_001'
# Installed path -> file of this package.
REPLACED_FILES = {'ua_order/attribution.py': 'attribution.py', 'ua_seo_order_models.py': 'ua_seo_order_models.py',
                  'ua_seo_quick_form.py': 'ua_seo_quick_form.py', 'ua_site_leads.py': 'ua_site_leads.py'}
# Installed path -> (module, attribute) holding its text.
ASSETS = {'video/order/quick-lead.js': ('quick_assets', 'JS'), 'video/order/quick-lead.css': ('quick_assets', 'CSS'),
          'video/order/attribution.js': ('attribution_assets', 'JS')}
