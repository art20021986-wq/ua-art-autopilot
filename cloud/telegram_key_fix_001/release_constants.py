"""Ключ Telegram: обычные рабочие сообщения (цена + VIN) не принимаются за ключ (TELEGRAM-KEY-FIX, координатор 24.11)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'TELEGRAM-KEY-FIX-PREFLIGHT-20261124-R3'  # R1 PASS on f8dc61b4; R2 PASS (run 45413438081) on d45dd4cd; R3: fresh storage for the install
INSTALL_TASK = 'TELEGRAM-KEY-FIX-INSTALL-20261124'
PACKAGE = 'cloud/telegram_key_fix_001'
NEW_MODULES = ()
