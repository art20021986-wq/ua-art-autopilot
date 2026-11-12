"""«💳 Платежи» in the CRM bot order card (CRM-PAYMENTS-001, owner «да» 2026-11-12); no private source in this package."""
PREVIEW_TASK = 'CRM-PAYMENTS-PREFLIGHT-20261112-R4'  # R1 exec in a test; R2 task name; R3 PASS, NBU rate URL 404
INSTALL_TASK = 'CRM-PAYMENTS-INSTALL-20261112'
PACKAGE = 'cloud/crm_payments_001'
NEW_MODULES = ('ua_pay_rules.py', 'ua_pay_store.py', 'ua_pay_lot.py', 'ua_pay_view.py', 'ua_pay_bot.py')
