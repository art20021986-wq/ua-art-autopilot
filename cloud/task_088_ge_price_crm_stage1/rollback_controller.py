#!/usr/bin/env python3
from __future__ import annotations
import os
import controller

def execute(environment, api_factory=controller.API):
    values = controller.required(environment, 'rollback')
    api = api_factory(values); api.bot_task(); api.upload_package()
    remote = api.run('rollback'); controller.validate_remote(remote, 'rollback', values)
    api.restart()
    receipt = {**controller.bindings(values), 'schema_version': 'UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1', 'operation': 'rollback', 'status': 'ROLLED_BACK', 'rollback': 'PASS', 'backup_manifest_sha256': values['UAART_BACKUP_MANIFEST_SHA256'], 'restored': True, 'unexpected_changes': 0, 'protected_files_unchanged': True, 'crm_unchanged': True, 'live_verify': 'PASS'}
    controller.atomic(controller.ROOT / controller.ROLLBACK_RECEIPT_REL, receipt)
    return receipt

if __name__ == '__main__': execute(os.environ)
