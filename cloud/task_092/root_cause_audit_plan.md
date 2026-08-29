# Root-Cause Audit Plan (Task 092)

This is the exact procedure that will be run once source material is available. No step below has been executed yet against real files; each row is a checklist, not a result.

## Per-surface audit table (to be filled with real findings)

| Surface | Creating file/function | Data source | Update trigger | Cache layer | Competing writer present? |
|---|---|---|---|---|---|
| Homepage stage cards | PENDING | PENDING | PENDING | PENDING | PENDING |
| Homepage counters (Kyiv/Georgia/Sea/Korea/total) | PENDING | PENDING | PENDING | PENDING | PENDING |
| Full catalog list | PENDING | PENDING | PENDING | PENDING | PENDING |
| Stage filters | PENDING | PENDING | PENDING | PENDING | PENDING |
| UA-0001..UA-0013 individual cards | PENDING (x13) | PENDING | PENDING | PENDING | PENDING |
| ETA/days fields (catalog view) | PENDING | PENDING | PENDING | PENDING | PENDING |
| ETA/days fields (full card view) | PENDING | PENDING | PENDING | PENDING | PENDING |
| Container number field | PENDING | PENDING | PENDING | PENDING | PENDING |
| RU/UA language toggle | PENDING | PENDING | PENDING | PENDING | PENDING |

## Specific hypotheses named by the owner/task to test first

1. **Multiple generators writing homepage vs catalog independently** — check whether `master_card.py`, `fitfix.py`, `yadro.py`, and any cron job each write a homepage snippet or a catalog snippet, and whether they run on different schedules → would explain 10-vs-13 mismatch and ferry count 4-vs-7 mismatch.
2. **Stale static homepage** — check whether the homepage HTML is a static file that is only rebuilt by a specific trigger, while the catalog is rendered dynamically or rebuilt more often → would explain homepage lagging catalog for UA-0011/0012/0013.
3. **Partial non-atomic publish** — check whether a publish step writes homepage, catalog, and cards as separate file writes without a single transaction/build_id, so a crash or interruption mid-publish leaves surfaces out of sync.
4. **Browser/Cloudflare cache mismatch** — only acceptable as a finding if a concrete cache rule, TTL, or purge log entry is produced; "probably cache" alone is explicitly rejected by the task.
5. **Old script overwriting new renderer** — check execution order of cron entries / process manager to see if a legacy script runs after the new renderer and reintroduces old counts (e.g., `start_safe.py` running after a newer builder).

## UA-0009 specific audit

UA-0009 catalog-vs-card ETA/day mismatch must be traced to the exact function computing ETA/days in each surface. Two independent computations (one in catalog renderer, one in card renderer) reading different timestamp fields is the leading hypothesis and must be confirmed or refuted with the real files before any fix is proposed.

## UA-0012 mileage anomaly

`342 km` must not be silently "corrected". The audit must locate the original CRM entry and any diagnostic evidence (odometer photo, OBD log) before any value is changed. If no corroborating evidence exists, the field must be flagged for owner clarification rather than auto-modified.

## Output required once real files are supplied

A completed version of the per-surface table above, each row backed by: file path, function name, git blame or mtime, and either a cache rule name/TTL or an explicit "no cache layer, direct render" statement.
