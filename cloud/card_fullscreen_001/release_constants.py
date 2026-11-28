"""The phone full-screen auction lot card (CARD-FULLSCREEN-001, owner «Да» 2026-11-28)."""
PREVIEW_TASK = 'CARD-FULLSCREEN-PREFLIGHT-20261128-R2'  # R1 request superseded (pause timeout 480 s), never launched
INSTALL_TASK = 'CARD-FULLSCREEN-INSTALL-20261128'
PACKAGE = 'cloud/card_fullscreen_001'
# Checked before and after the install: only pages that exist before it.
HEALTH_CHECKS = ('https://www.uaart.com.ua/video/index.html', 'https://www.uaart.com.ua/video/korea.html',
                 'https://www.uaart.com.ua/video/japan.html')
