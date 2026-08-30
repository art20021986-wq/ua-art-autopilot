#!/usr/bin/env python3
from __future__ import annotations
import base64
import pathlib
import zlib

ROOT = pathlib.Path(__file__).resolve().parent
PARTS = sorted((ROOT / 'payload').glob('part*.b85'))
if not PARTS:
    raise SystemExit('TASK096_PAYLOAD_MISSING')
encoded = b''.join(path.read_bytes().strip() for path in PARTS)
source = zlib.decompress(base64.b85decode(encoded))
target = ROOT / 'task096_runtime.py'
target.write_bytes(source)
compile(source.decode('utf-8'), str(target), 'exec')
print(target)
