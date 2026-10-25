"""Google tag release (GA4 G-6SRBQK6GY4 on public pages, leads as events); no private source in this package."""
PREVIEW_TASK = 'GA4-TAG-PREFLIGHT-20261025'
INSTALL_TASK = 'GA4-TAG-INSTALL-20261025'
PACKAGE = 'cloud/ga4_tag_001'
NEW_MODULES = ('ua_google_tag.py',)
REPLACED_MODULES = ('ua_seo_metadata.py', 'ua_seo_index.py')
PATCHED_MODULES = ('publish_transaction_guard.py',)
