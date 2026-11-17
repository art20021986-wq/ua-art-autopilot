"""Card facts fix: UA-0021 past arrival date, UA-0023 year in text (owner 2026-11-17, SEO-AUDIT-20261116)."""
# R1 install rolled back: the ru/ua UA-0023 versions need the K5 dictionary entry (now in the same transaction).
PREVIEW_TASK = 'CARD-FACTS-PREFLIGHT-20261117-R3'
INSTALL_TASK = 'CARD-FACTS-INSTALL-20261117-R2'
PACKAGE = 'cloud/card_facts_001'
