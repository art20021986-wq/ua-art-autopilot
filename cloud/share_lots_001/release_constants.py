"""«Поділитися» in the auction lot card (SHARE-LOTS-001, owner «да» 2026-11-28 06:33 UTC via the coordinator)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'SHARE-LOTS-PREFLIGHT-20261128'
INSTALL_TASK = 'SHARE-LOTS-INSTALL-20261128'
PACKAGE = 'cloud/share_lots_001'
# Checked before and after the install: only pages that exist before it.
HEALTH_CHECKS = ('https://www.uaart.com.ua/video/index.html', 'https://www.uaart.com.ua/video/korea.html',
                 'https://www.uaart.com.ua/video/japan.html')
