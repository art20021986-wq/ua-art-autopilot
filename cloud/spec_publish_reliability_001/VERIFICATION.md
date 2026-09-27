# Production verification

Installed 2026-09-27 at 20:28 UTC; source revision `1c80f330d419770d4341a1abe79c670e1fbabe9c`.
Source hashes were checked before replacement and read back after replacement.
Backup: `/home/Carix/spec_reliability_backup_20260927_202844` (includes the configured active specification DB and its durable queue).

The existing CRM always-on task 266084 restarted at 20:34 UTC; the new worker's heartbeat was RUNNING with 22 published cards. The existing recovery scan launched the backfill without manual republishing.

57 tests pass locally and on server Python 3.10 with isolated temporary databases and copies of the actual installed dependencies. Server run: 20.603 seconds. This includes simulated restart/lease recovery, all four retry slots, new VINs, two-source confirmation, purchase-price rejection, manual/hidden fields, rollback and both page projections. An initial test run exposed connection lifetimes on the server filesystem; the runtime now closes SQLite connections deterministically.

Public HTTP and rendered-HTML row audit: 22/22 HTTP 200; 22/22 have a non-empty additional specification; every previously displayed specification row remains present; no purchase-price field labels/values appear in the specification sections. No new listing or test car was published to production.

| Card | Before | After |
|---|---:|---:|
| UA-0001 | 43 | 43 |
| UA-0003 | 25 | 25 |
| UA-0004 | 25 | 25 |
| UA-0005 | 44 | 44 |
| UA-0006 | 25 | 25 |
| UA-0007 | 47 | 47 |
| UA-0008 | 47 | 47 |
| UA-0009 | 25 | 25 |
| UA-0010 | 25 | 25 |
| UA-0011 | 29 | 29 |
| UA-0012 | 25 | 25 |
| UA-0013 | 40 | 40 |
| UA-0014 | 47 | 47 |
| UA-0015 | 31 | 31 |
| UA-0016 | 25 | 25 |
| UA-0017 | 12 | 18 |
| UA-0018 | 13 | 16 |
| UA-0019 | 47 | 47 |
| UA-0020 | 0 | 8 |
| UA-0021 | 0 | 8 |
| UA-0022 | 0 | 11 |
| UA-0023 | 0 | 11 |

Collection is automatic for future published cards. The durable schedule remains immediate plus three retries at 10-minute intervals. The later production slots were not artificially accelerated; their timing and restart behavior are covered by the tests.

Ten approved sources are configured; availability is recorded per source. This does not mean every source yields data for every vehicle. Dated audited catalogue fallback is distinguished from freshly extracted evidence. Unknown or conflicting trim data is not invented.
