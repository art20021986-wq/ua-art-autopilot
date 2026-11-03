"""«Кредити та лізинг» on every car card (FINANCE-001 stage 4, CARD-FINANCE-001); no private source here."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'CARD-FINANCE-PREFLIGHT-20261103-R2'  # R1 PASS (22/22); fresh run after CARD-CANONICAL-FIX
INSTALL_TASK = 'CARD-FINANCE-INSTALL-20261103'
PACKAGE = 'cloud/card_finance_001'
