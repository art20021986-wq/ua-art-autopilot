#!/usr/bin/env python3
import pathlib, os, tempfile, hashlib
ROOT=pathlib.Path("/home/Carix")
TARGET=ROOT/"video/google609494476a22f741.html"
VALUE=b"google-site-verification: google609494476a22f741.html\n"
if TARGET.parent.resolve(strict=True)!=(ROOT/"video").resolve(strict=True): raise SystemExit("scope")
if TARGET.is_symlink(): raise SystemExit("symlink")
fd,tmp=tempfile.mkstemp(prefix=".gsc-",dir=str(TARGET.parent))
try:
    with os.fdopen(fd,"wb") as f: f.write(VALUE); f.flush(); os.fsync(f.fileno())
    os.chmod(tmp,0o644); os.replace(tmp,TARGET)
finally:
    try: os.unlink(tmp)
    except FileNotFoundError: pass
if TARGET.read_bytes()!=VALUE: raise SystemExit("readback")
print("GSC_HTML_VIDEO_INSTALL_PASS sha256="+hashlib.sha256(VALUE).hexdigest())
