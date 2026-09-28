#!/usr/bin/env python3
import pathlib, os, tempfile, hashlib
ROOT=pathlib.Path("/home/Carix")
TARGET=ROOT/"google609494476a22f741.html"
VALUE=b"google-site-verification: google609494476a22f741.html\n"
assert TARGET.parent == ROOT
if TARGET.is_symlink(): raise SystemExit("target symlink refused")
fd,tmp=tempfile.mkstemp(prefix=".gsc-",dir=str(ROOT))
try:
    with os.fdopen(fd,"wb") as f:
        f.write(VALUE); f.flush(); os.fsync(f.fileno())
    os.chmod(tmp,0o644); os.replace(tmp,TARGET)
finally:
    try: os.unlink(tmp)
    except FileNotFoundError: pass
if TARGET.read_bytes()!=VALUE: raise SystemExit("readback mismatch")
print("GSC_HTML_VERIFY_INSTALL_PASS sha256="+hashlib.sha256(VALUE).hexdigest())
