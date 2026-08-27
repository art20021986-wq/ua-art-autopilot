# TASK 047 — Ferry Wording Phase 1: Contextual Transform + Bounded Read-Only Discovery

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope of this phase

This package implements ONLY what TASK 047 asked for:

1. `transform.py` — a deterministic, context-aware RU/UA text transform engine
   that rewrites the ferry-related wording (`В море` → `На пароме`,
   `У морі` → `На поромі`, short `Море` → `Паром`/`Пором`) inside HTML-like
   documents, while leaving internal identifiers (`data-stage="sea"`,
   `?f=sea`, IDs, URLs, CSS/JS/API/analytics/database enums), scripts,
   styles, comments, ordinary prose and legacy aliases byte-identical.
2. `discover.py` — a fail-closed, read-only, bounded discovery tool that
   inspects a fixed registry of candidate files under a single base
   directory (default `/home/Carix`, overridable only through the
   `FERRY_DISCOVERY_BASE_DIR` environment variable for testing) and a
   read-only CRM (`crm.db`) inspection routine.
3. Standard-library `unittest` tests for both modules.

This phase explicitly does **not** implement Gate A, a network controller,
a workflow, or any write to production, CRM, `crm.db`, the site, cards, or
the generator. It does not publish UA-0009. It never executes files found
by discovery; it only reads their bytes for hashing/identity checks.

## Why the previous attempt (TASK 045) failed

TASK 045 produced 17 in-memory files that were never committed because a
static check failed:

```
PYTHON_STATIC_CHECK_FAIL:cloud/task_045_ferry_wording/transform.py:line=5:offset=15
```

This phase starts from a clean, minimal, compile-checked implementation and
adds `py_compile` verification to `run_tests.py` specifically to prevent a
repeat of that failure.

## Contextual mapping implemented

| Context | Old RU | New RU | Old UA | New UA |
|---|---|---|---|---|
| status/chip/filter | В море | На пароме | У морі | На поромі |
| long | В море · … | На пароме · … | У морі · … | На поромі · … |
| heading | В море: … | На пароме: … | У морі: … | На поромі: … |
| short (proven stage node/attribute) | Море | Паром | Море | Пором |

A standalone `Море` node without a provable language (via `lang=`,
`data-lang=`, a `lang-ru`/`lang-uk` class, or a `data-ru`/`data-uk`
attribute name) is reported as `AMBIGUOUS` and left byte-identical. It is
never guessed.

`data-ru` and `data-uk` attributes are always processed together in the
same pass, using the language implied by the attribute name itself, with
the status/long/heading/short form auto-detected from the attribute value
content.

## Structural approach

The transformer is a lightweight tag/comment/doctype/text tokenizer (not a
full DOM), which:

- never rewrites text found inside `<script>`/`<style>` elements;
- never rewrites comments or the doctype;
- tracks a tag stack to resolve nearest ancestor `class`/`lang`/`data-lang`
  context for plain text nodes;
- preserves original tag/attribute byte layout (case, quoting, void
  elements, self-closing syntax) except for the exact `data-ru`/`data-uk`
  attribute values that match the ferry-wording patterns;
- leaves every other byte in the document untouched.

This is intentionally simpler than a full HTML5 parser. It is sufficient
for the exact fixtures and mapping rules in this phase and is documented
honestly as such — it is not claimed to be a general-purpose HTML rewriter.

## Discovery approach (fail-closed, read-only)

`discover.py` contains a fixed, bounded registry (no directory recursion)
of the exact candidate paths named in the task: video pages, site page
equivalents, UA-0001..UA-0009 diag/track candidates, the named Python
modules, and `crm.db`. For every present file it performs:

- canonical containment check under the base directory (rejects `..`
  escapes and symlinked parent directories);
- `lstat` on the final path (rejects symlinks, rejects non-regular files,
  rejects `nlink != 1`);
- `os.open` with `O_RDONLY | O_NOFOLLOW` (where supported);
- `fstat` before and after the bounded read, comparing dev/inode/size/
  mtime_ns for stability (fail-closed on any TOCTOU mismatch);
- a size cap with hard failure on oversize/truncated/concurrently-changed
  files;
- strict UTF-8 decoding (never `errors="ignore"`);
- a SHA-256 of the full byte content.

Missing files are reported honestly as `MISSING`, never fabricated.

## CRM read-only evidence

`crm_readonly_summary()` opens the database file only with
`sqlite3.connect("file:...?mode=ro", uri=True)`, immediately sets
`PRAGMA query_only=ON`, runs `PRAGMA quick_check`, and then discovers
schema strictly through an explicit table/column allowlist. If no table or
no identifiable id column matches the allowlist, the result is `BLOCKED`
with reason `AMBIGUOUS_SCHEMA*` — never an invented value. When a match is
found, only the nine `UA-0001..UA-0009` rows are queried by parametrized
exact match, and only allowlisted columns are ever selected. The file's
identity (dev/inode/size/mtime_ns) is verified unchanged both before
connecting and after closing the connection.

## Secret redaction

Before emitting the single JSON receipt, `discover.py` scans the fully
serialized string for `secret`, `token`, `password`, `api-key`,
`authorization`, `private-key`, `credential` (and token-like `key=value`
patterns) and redacts any match. In normal operation the receipt never
contains file content, only hashes/identities/statuses, so this scan is a
defense-in-depth safety net.

## Running the tests

```
python3 cloud/task_047_ferry_discovery/run_tests.py
```

This compiles both modules with `py_compile`, checks 10-run determinism and
idempotence of the transform, then runs the full `unittest` suite.

## Explicit non-claims

- No PythonAnywhere execution occurred.
- No production, CRM, `crm.db`, site, card, or generator file was written.
- No UA-0009 publication occurred; `UA0009_SAFE_TO_PUBLISH` remains `NO`.
- No Gate A or Gate B execution occurred.
- Real-file discovery results depend entirely on what exists at the fixed
  base directory when `discover.py` is actually run in the real
  environment; this phase does not claim to have inspected the real
  `/home/Carix` filesystem from within this sandbox.
