"""Analytics release 3: photo/button clicks and read depth by the own counter; a per-page block in the bot report."""
PREVIEW_TASK = 'ANALYTICS3-PREFLIGHT-20261112'
INSTALL_TASK = 'ANALYTICS3-INSTALL-20261112'
PACKAGE = 'cloud/analytics_003'
NEW_MODULES = ('ua_page_depth.py',)
PATCHED_MODULES = ('analitika_yadro.py', 'analitika_otchet.py')
