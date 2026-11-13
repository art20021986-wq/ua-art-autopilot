"""«💳 Платежи» in the CRM bot order card (CRM-PAYMENTS-001, owner «да» 2026-11-12); no private source in this package."""
PREVIEW_TASK = 'CRM-PAYMENTS-PREFLIGHT-20261113'  # 20261112: R1 exec; R2 name; R3 NBU 404; R4 PASS; R5 du journal; R6 PASS (fresh probe for install)
INSTALL_TASK = 'CRM-PAYMENTS-INSTALL-20261113'
PACKAGE = 'cloud/crm_payments_001'
NEW_MODULES = ('ua_pay_rules.py', 'ua_pay_store.py', 'ua_pay_lot.py', 'ua_pay_view.py', 'ua_pay_bot.py')
