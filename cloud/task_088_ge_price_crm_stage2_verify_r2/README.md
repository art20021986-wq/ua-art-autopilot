# Stage 2 GET-only verification R2

R2 preserves successful evidence when one explicitly allowed source is absent. It performs ten fixed GET requests: cars_ui.py, db.py, price_parser.py, start_safe.py and the historical Stage 1 receipt, each read twice. Path-specific errors and inconsistent snapshots remain explicit. There are no upload/process endpoints or database downloads.

The immutable local Stage 1 receipt is required. Complete downloaded source stays in memory and is never imported or executed. Only selected helpers/constants passing the no-secret policy are exported. The reviewed local hash-pinned patcher compiles a complete original-source candidate; independent AST proof checks unrelated code and existing statements. A source change rejects candidate verification while retaining useful diagnostic evidence. Parser import handling is inspected as syntax; absent optional parser does not discard cars_ui/db evidence.

FINISHED means diagnostic evidence collection only. Check candidate_verification and each path status separately. Live schema, process imports, UI price saving and Stage 2 installation remain NOT_PERFORMED or NOT_VERIFIED.

The package contains no calls to exec or eval. Its local pinned patcher is loaded through importlib; downloaded source is compiled only. Production fixture-execution tests from the separate Stage 2 development package are not copied into this diagnostics package.
