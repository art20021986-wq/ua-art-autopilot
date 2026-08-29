# TASK 083 — transactional CRM publication

Production repair for UA-0012 and UA-0013 plus a generic publication guard.

The package stages a diagnostic placeholder, backs up all bounded targets,
uses the active master card generator, rebuilds both catalogs through the
stage/category guard, verifies read-back and rolls back on every failure. The
CRM handler now sends exactly one result and restores `published`, `status`
and `publish_pending` on a failed publication.

Runtime LLM tokens: 0.

