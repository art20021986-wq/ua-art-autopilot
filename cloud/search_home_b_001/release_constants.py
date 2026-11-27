"""The home page top block «Пошук авто на аукціонах світу» (SEARCH-HOME-001 B, owner «Да» 2026-11-27)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'SEARCH-HOME-B-PREFLIGHT-20261127-R3'  # R1, R2 requests superseded (module changed), never launched
INSTALL_TASK = 'SEARCH-HOME-B-INSTALL-20261127'
PACKAGE = 'cloud/search_home_b_001'
# Checked before and after the install: only pages that exist before it (this release adds no page).
HEALTH_CHECKS = ('https://www.uaart.com.ua/video/index.html', 'https://www.uaart.com.ua/video/katalog.html',
                 'https://www.uaart.com.ua/video/korea.html')
