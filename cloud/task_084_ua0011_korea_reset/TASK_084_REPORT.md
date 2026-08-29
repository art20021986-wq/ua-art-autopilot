# UA-0011-KOREA-CARD-RESET-001 v1.0 — LIVE GATE A

STATUS: **PASS**

- Production touched: **NO**
- CRM/PythonAnywhere methods: **GET only**
- Fresh CRM status: `kr_bought` / «В Корее»
- Stale incompatible values found: `sea_container=ONEYSELGF1046602`, `eta_manual=2026-12-12`
- Exact sandbox delta: clear `sea_container` and `eta_manual`; status remains `kr_bought`
- Other CRM fields unchanged: **PASS**
- Media: **35 photos**, 0 videos; no foreign-card references
- Cover: `video/foto/UA-0011/m/001.jpg`, SHA-256 `86850437f204c6d51fecd1e925317faca1ab727f1fec435b087f1934c1548d07`
- Visual cover check: **PASS** — front three-quarter facade view of the white Hyundai Sonata
- Ten repeated sandbox runs: **10/10 PASS**, duplicates 0, drift 0
- Full unified card structure without text-only fallback: canary contract **PASS**
- UA-0009 protected/read-only safety gate: **PASS**

## Root cause

The CRM stage callback writes only `status`; it does not clear logistics fields that become invalid when the car is returned to `kr_bought`. Therefore the row can simultaneously say «В Корее» and retain a container/ETA. Separately, the legacy catalog renderer allowed a narrow text-only fallback when the media mapping was not ready and did not force a rebuild after media sync.

The permanent production fix must make the transition atomic (`status` plus compatible logistics fields), reject ferry stages without confirmed loading evidence, and block catalog writes until the own cover photo is ready while always using the unified full-card renderer.

Production remains locked under TASK 084 until a separate written Gate B command.
