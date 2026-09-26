#!/usr/bin/env python3
from __future__ import annotations
import os
import controller

def execute(environment, api_factory=controller.API):
    values = controller.required(environment, 'backup')
    api = api_factory(values); api.bot_task(); api.upload_package()
    remote = api.run('backup'); controller.validate_remote(remote, 'backup', values)
    receipt = {**controller.bindings(values), 'schema_version': 'UA-ART-PRODUCTION-BACKUP-RECEIPT-1', 'operation': 'backup', 'status': 'PASS', 'backup': 'PASS', 'backup_manifest_sha256': remote['backup_manifest_sha256'], 'unexpected_changes': 0}
    controller.atomic(controller.ROOT / controller.BACKUP_RECEIPT_REL, receipt)
    return receipt

if __name__ == '__main__': execute(os.environ)
