"""Own counter release (counter on cards, diagnostics and landing pages; source and Kyiv day fixes)."""
PREVIEW_TASK = 'OWN-COUNTER-PREFLIGHT-20261107'
INSTALL_TASK = 'OWN-COUNTER-INSTALL-20261107'
PACKAGE = 'cloud/own_counter_001'
NEW_MODULES = ('ua_own_counter.py',)
PATCHED_MODULES = ('ua_seo_metadata.py', 'ua_seo_index.py', 'analitika_yadro.py', 'analitika_otchet.py')
