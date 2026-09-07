# TASK120-PUBLISH-UA-0017-UA-0018

Fail-closed one-shot package for exact CRM rows `id=26 / UA-0017` and
`id=28 / UA-0018`. It writes only the two publication flags, exact approved
sidecar specification rows (18 Audi model-level facts and 12 Kia K5 LPI
model-level facts), target HTML/diagnostics and both catalogs.

Production execution requires `PYTHONANYWHERE_API_TOKEN` and:

```bash
python3 controller.py --execute --confirm TASK120-PUBLISH-UA-0017-UA-0018
```

The controller performs probe → backup → atomic publish → remote verification
→ public GET verification. Any failure after backup triggers exact rollback.
