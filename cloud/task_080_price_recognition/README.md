# TASK 080 — CRM sale-price recognition

Verified release candidate for deterministic recognition of the vehicle sale
price from text, voice transcripts, photo captions, and the explicit price UI.

Key files:

- `src/price_parser.py` — shared zero-LLM deterministic parser;
- `src/crm_price_atomic.py` — atomic price/history/audit writer;
- `src/integration_patcher.py` — exact hash-gated in-memory integration;
- `tests/` and `run_tests.py` — 58 sandbox/canary regressions;
- `live_gate_a.py` — current-card and active-code GET-only audit;
- `candidate_gate_a.py` — fresh live-source in-memory compile gate;
- `evidence/live_gate_a.json` and `evidence/candidate_gate_a.json` — sanitized evidence;
- `GATE_B_PLAN.md` and `BACKUP_ROLLBACK.md` — prepared release controls.

Current state: `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`.
Nothing in production has been changed by this task round.
