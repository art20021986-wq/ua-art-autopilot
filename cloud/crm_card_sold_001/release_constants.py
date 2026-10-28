"""Two-file card sold release; no private source in this package."""
PREVIEW_TASK = 'CRM-CARD-SOLD-PREFLIGHT-20261028-R3'
INSTALL_TASK = 'CRM-CARD-SOLD-INSTALL-20261028'
NEW_MODULE = 'ua_card_sold.py'
PACKAGE = 'cloud/crm_card_sold_001'
# Car already marked sold before this fix; the install catalog repair must remove it.
SOLD_CAR = 'UA-0020'
