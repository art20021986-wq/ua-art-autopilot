"""Card language versions release (CARD-LANG-001); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'CARD-LANG-PREFLIGHT-20261030-R2'  # R1: 12/19 cards complete; texts added
INSTALL_TASK = 'CARD-LANG-INSTALL-20261030'
PACKAGE = 'cloud/card_lang_001'
# Installed path -> file of this package.
NEW_FILES = {'ua_card_lang.py': 'ua_card_lang.py', 'ua_card_lang_job.py': 'ua_card_lang_job.py'}
