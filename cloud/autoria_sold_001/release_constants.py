"""Weekly AUTO.RIA figures: a daily server job that works on Mondays (AUTORIA-SOLD-001, owner 2026-11-11).

Release 1 (AUTORIA-SOLD-PREFLIGHT/INSTALL-20261111): the sold-cars number. Release 2 (owner «Да, конечно, сделать»
2026-11-11): also years on AUTO.RIA and the reviews count; the installed job files are replaced.
"""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'AUTORIA-FIGURES-PREFLIGHT-20261111'
INSTALL_TASK = 'AUTORIA-FIGURES-INSTALL-20261111'
PACKAGE = 'cloud/autoria_sold_001'
