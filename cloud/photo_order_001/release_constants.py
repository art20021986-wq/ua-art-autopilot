"""Фото в карточке CRM-бота — в порядке отправки (PHOTO-ORDER-001, владелец 19.11)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'PHOTO-ORDER-PREFLIGHT-20261119-R3'  # R1 run 44465192910 FAIL at persist (package file changed during the run; reconciled #1857); R2 run 44468694465 RESOURCE_BUSY (R1 claim)
INSTALL_TASK = 'PHOTO-ORDER-INSTALL-20261119'
PACKAGE = 'cloud/photo_order_001'
NEW_MODULES = ()
