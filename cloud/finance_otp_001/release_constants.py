"""OTP Bank credit on the finance page (FINANCE-OTP-001); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'FINANCE-OTP-PREFLIGHT-20261104-R3'  # R1: before the in-transit block; R2 PASS, storage du race
INSTALL_TASK = 'FINANCE-OTP-INSTALL-20261104'
PACKAGE = 'cloud/finance_otp_001'
