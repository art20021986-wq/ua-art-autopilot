## UA-ART-GE-PRICE-CRM-001 · Stage 1

Offline Stage 1 package for Issue #88.

Sources used:
- `/home/runner/work/ua-art-autopilot/ua-art-autopilot/tasks/UA-ART-GE-UA-MARKET-PRICE-001-v3.1.md`
- `/home/runner/work/ua-art-autopilot/ua-art-autopilot/cloud/task_070/evidence/real_context.json`
- `/home/runner/work/ua-art-autopilot/ua-art-autopilot/cloud/task_066_stage_anchor/evidence/current.json`
- `/home/runner/work/ua-art-autopilot/ua-art-autopilot/cloud/task_067/evidence/read_only_audit.json`
- `/home/runner/work/ua-art-autopilot/ua-art-autopilot/cloud/task_084_ua0011_korea_reset/evidence/live_gate_a_inventory.json`

Contents:
- `stage1_patch.diff` — minimal CRM-only patch proposal.
- `simulator.py` — synthetic local CRM harness for Stage 1 verification.
- `tests/test_stage1.py` — automated checks for write → DB → read-back and field independence.
- `report.md` — Stage 1 result and evidence summary.
- `evidence.json` — machine-readable results generated from the simulator.

Production, public site, publisher, cards, stages, VIN, media, counters, SEO, languages, CTA and PythonAnywhere are not touched here.
