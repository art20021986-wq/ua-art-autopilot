"""Home page steps 2-5 (ORDER-PROCESS-001, owner 2026-11-11): country switcher and Korea terms; no private source here."""
PREVIEW_TASK = 'HOME-STEPS-PREFLIGHT-20261111-R4'  # R1/R2 never ran (halt); R3 PASS but its install waited too long in the queue
INSTALL_TASK = 'HOME-STEPS-INSTALL-20261111-R2'  # R1 cancelled in the queue before any step (storage probe would be stale)
PACKAGE = 'cloud/home_steps_001'
HOME = 'video/index.html'
