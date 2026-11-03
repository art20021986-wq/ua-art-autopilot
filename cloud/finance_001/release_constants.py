"""Finance partners release (FINANCE-001); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'FINANCE-PREFLIGHT-20261103-R4'  # R1: fixtures as .py refused; R2/R3: logo changes
INSTALL_TASK = 'FINANCE-INSTALL-20261103'
PACKAGE = 'cloud/finance_001'
# New server modules: installed path -> file of this package.
NEW_MODULES = {'ua_finance_partners.py': 'ua_finance_partners.py', 'ua_seo_finance.py': 'ua_seo_finance.py',
               'ua_finance_crm.py': 'ua_finance_crm.py'}
