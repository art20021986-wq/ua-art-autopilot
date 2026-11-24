"""Повторная загрузка удалённых фото в карточку CRM-бота (PHOTO-ADD-001, владелец 19.11)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'PHOTO-ADD-PREFLIGHT-20261119-R3'  # R1 PASS (run 44450249373); R2 PASS (run 44451774419, + photos only); R3: fresh storage for the install
INSTALL_TASK = 'PHOTO-ADD-INSTALL-20261119'
PACKAGE = 'cloud/photo_add_001'
NEW_MODULES = ()
