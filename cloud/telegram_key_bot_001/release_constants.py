"""Владелец присылает ключ Telegram API боту CRM одним сообщением (TELEGRAM-KEY-BOT, владелец 19.11)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'TELEGRAM-KEY-PREFLIGHT-20261119-R2'  # R1 PASS (run 44498598851); R2: fresh storage for the install, after SEO
INSTALL_TASK = 'TELEGRAM-KEY-INSTALL-20261119'
PACKAGE = 'cloud/telegram_key_bot_001'
NEW_MODULES = ('ua_telegram_key.py',)
