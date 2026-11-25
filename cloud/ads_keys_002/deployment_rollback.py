"""Bind the standard production rollback phase."""
import os
from deployment_controller import run

if __name__ == '__main__':
    if os.environ.get('UAART_OPERATION') != 'rollback':
        raise SystemExit('OPERATION_SCOPE')
    raise SystemExit(run('rollback'))
