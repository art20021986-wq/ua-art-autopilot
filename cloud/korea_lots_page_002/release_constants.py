"""Korea lot list: «Ціна — на торгах» instead of «$0», no empty score (JPAUTO-KOREA-001, owner 2026-11-10)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'KOREA-LOTS-PAGE2-PREFLIGHT-20261110-R2'
INSTALL_TASK = 'KOREA-LOTS-PAGE2-INSTALL-20261110-R2'  # R1 bundle not launched: its storage probe would expire
PACKAGE = 'cloud/korea_lots_page_002'
