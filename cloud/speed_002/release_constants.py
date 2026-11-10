"""Speed and single card URL release (SPEED-002); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'SPEED2-PREFLIGHT-20261108-R6'  # R5 PASS, its storage probe is too old for the R2 install
INSTALL_TASK = 'SPEED2-INSTALL-20261108-R2'  # R1 rolled back by its K5 check (no K5 cars on sale)
PACKAGE = 'cloud/speed_002'
