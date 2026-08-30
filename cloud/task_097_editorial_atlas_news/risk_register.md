# Risk register — future NEWS module (specification only)

| # | Risk | Category | Likelihood | Impact | Mitigation |
|---|---|---|---|---|---|
| 1 | Prompt injection via malicious source HTML/text | Security | Medium | High | Treat every external fetch as untrusted input; strip/ignore any embedded instructions; the editorial engine only reads structured extracted fields, never raw HTML as an instruction channel |
| 2 | XSS via source-provided HTML in headline/body | Security | Medium | High | Sanitize/escape all external HTML before storage and before render; never store raw `<script>`-bearing HTML |
| 3 | SSRF via a source URL pointing at an internal/private address | Security | Low-Medium | High | Validate every outbound URL scheme (`http`/`https` only) and resolve/deny private-IP ranges (RFC1918, loopback, link-local) before fetching; deny non-standard schemes (`file://`, `ftp://`, etc.) |
| 4 | Open redirect abused to reach an unintended target | Security | Low | Medium | Cap redirect hops; log and flag the final resolved URL; require the final domain to remain within the allowlisted source's registered domain unless a manual redirect confirmation is recorded (as already flagged for KR-01/KR-08/EU-05/KR-10 in this audit) |
| 5 | Secret leakage (API keys, tokens) into logs/evidence | Security | Low | High | No secret is ever written into `cloud/` artifacts, evidence files, or logs; connectors read credentials only from a secret store, never from a file under version control |
| 6 | Duplicate publication of the same event under two STORY IDs | Data integrity | Medium | Medium | Dedup thresholds and merge bands (`dedup_scoring_autopilot.md` §1); unique constraints on `(story_id, language)` |
| 7 | Partial publish (one language public, the other not) | Data integrity | Medium | High | Atomic bilingual publish transaction (`data_model_pipeline.md` §4); no partial commit path exists |
| 8 | A false or unverified legal/regulatory claim gets published | Editorial/legal | Medium | High | Sensitive-category gate forces `MANUAL_ONLY` + official-primary-source requirement regardless of NEWS SCORE |
| 9 | A malformed publish corrupts the public sitemap | SEO/technical | Low | Medium | The news sitemap is generated only from rows where `is_indexable = TRUE`; generation is a separate, idempotent, re-runnable step, never a direct hand-edit |
| 10 | NEWS module load impacts CRM responsiveness | Operational | Low (by design) | High if it occurred | Fully separate DB/schema, separate process, separate lock/queue (no shared `cross_process_lock.py`/`sqlite_ownership.py`); enforced as an architectural boundary in `current_architecture_audit.md` §4 |
| 11 | Infinite retry loop on a chronically failing source | Operational | Medium | Medium | Bounded exponential backoff, hard attempt cap, dead-letter table (`failed_jobs`) |
| 12 | A source is compromised/spoofed (e.g. a lookalike domain) | Security/editorial | Low-Medium | High | Manual confirmation required for any observed domain change (already flagged PENDING for KR-01/KR-08/EU-05/KR-10); source allowlist is closed, not auto-expanding |
| 13 | Autopilot mis-scored a story as TOP NEWS when it should not have autopublished | Editorial | N/A at this stage | High | Autopilot is not built or enabled by this task; when built, the sensitive-category gate and the full `AUTOPILOT_ELIGIBLE` gate in `dedup_scoring_autopilot.md` §4 both apply, plus a global manual kill switch |
| 14 | Image used without confirmed rights | Legal | Medium | Medium | `IMAGE_RIGHTS_CONFIDENCE` defaults to UNKNOWN/0; publish validation blocks any image without a confirmed status |
| 15 | Encoding/mojibake corrupts extracted text (observed for KR-03, JP-03 in this audit) | Data quality | Confirmed for 2 sources | Low-Medium | Charset-aware parsing required before those sources are scheduled; flagged `APPROVE_LATER`/`MANUAL_ONLY`, not silently ingested |

## Explicit non-goal for this task

No mitigation code was written or deployed. This register defines what must exist before the corresponding SANDBOX/production gate can be considered safe.
