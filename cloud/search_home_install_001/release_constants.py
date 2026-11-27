"""One place for the task names (SEARCH-HOME-001 install A, owner «Да» 2026-11-26; tasks/SEARCH-HOME-001.md)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'SEARCH-HOME-PREFLIGHT-20261126-R4'  # R1 .py-only contract; R2, R3 PASS; R4 for install R2
INSTALL_TASK = 'SEARCH-HOME-INSTALL-20261126-R2'  # R1 halted: pre-health asked for usa.html before it existed
PACKAGE = 'cloud/search_home_install_001'
# Pages checked BEFORE and after the install: only pages that already exist (R1 halted on the new usa.html, 404
# before the install). The new USA page and files are checked after the install by deployment_controller.EXPECTED.
HEALTH_CHECKS = ('https://www.uaart.com.ua/video/index.html', 'https://www.uaart.com.ua/video/korea.html',
                 'https://www.uaart.com.ua/video/podbor.html')
