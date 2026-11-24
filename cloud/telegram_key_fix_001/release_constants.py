"""Ключ Telegram: обычные рабочие сообщения (цена + VIN) не принимаются за ключ (TELEGRAM-KEY-FIX, координатор 24.11)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'TELEGRAM-KEY-FIX-PREFLIGHT-20261124-R2'  # R1 PASS (run 45397208357) on f8dc61b4; R2 on the STAFF-FULL-ACCESS file
INSTALL_TASK = 'TELEGRAM-KEY-FIX-INSTALL-20261124'
PACKAGE = 'cloud/telegram_key_fix_001'
NEW_MODULES = ()
