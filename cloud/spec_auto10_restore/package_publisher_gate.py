#!/usr/bin/env python3
"""Reproduce the eight reviewed publisher v2 ZIP entries from tracked files.

No production source is included or imported. Exact content hashes match the
server-tested v2 bundle. ZIP timestamps and permissions are fixed, so repeated
builds are byte-identical. Output creation is exclusive and never overwrites.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
CURRENT_HASHES = {
    "stranica.py": "42aa5fc9db162e59fcf36b7ee9b2002360205827023786a65cf2205ab16066cc",
    "master_card.py": "f64e0b82b11bfd6089509510e5b131a91b03d40bed97b16075ab2ec60da380ce",
    "catalog_design_guard.py": "51127bbc2be949e1d37f7b6995c0e5a7a32a497c8436139322ce5b0fea308d60",
    "db.py": "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
}
CANDIDATE_HASHES = {
    "publikaciya.py": "224d140151e26ff597962f17f45ec928f0716fb873e139e9686aac0256de87e8",
    "publish_transaction_guard.py": "eb8a37c5bba85b74cf3d6ed4c326d20d69a92274dee1e75f80108b5fa9834912",
    "ua_additional_spec.py": "5a03cb99d1f4514539956f32a75e09e119e2e9049a91da6326adb32877518e56",
    "spec_publication.py": "3e2ed470ebc06a9cbf03357858aeaf63cc6262045384867fca6b7b95bb181718",
    "card_shell.py": "9d764eae5f73e8b75e8c863abb9c3ae8c3a44f0bd1fa2918a28a80e996556b0a",
    "vin_spec_service.py": "a4468d2de5fd35d0778dea0ee15ad382dcb680ec4aa344da217cfce67f088c16",
    "source_policy.py": "e9590c1630a8c81bcacf05d620e273a341aaf407f39c3a1bd184258c17ce3f0d",
    "profile_library.py": "6784b5641a1bd6f8e094a0bc7ca4769596f91082f46891515463a933d2225eb6",
    "card_lifecycle.py": "a0f65fedcf91cbe01f0b891ddde31b97186e9c7ae77e51cef905cf29a81b55b7",
}
# Ordered exactly as the server-tested manifest; preserve its literal bytes.
FROZEN_FILES = {
    "current-manifest.json": "3bbc63aee147a0848ba38b6b79b1a047b1bb3a6011892bf246751f5022f646ab",
    "repair_master_shell.py": "fb01f9de8b17e5b37babb56c1554de3f2cc3067668fc8db63237d9f47aafcac4",
    "full_publisher_rehearsal.py": "8f8597a64c85f8b34ad36bc9855606b0bf8d45de5b3bcce9e5ea2b0d6bcd2f4f",
    "repair_public_contract.py": "69765b84749f61e97ca6ac99c1a28c9bc9864a98fb38c82a527383b8c063287b",
    "publisher_server_gate.py": "faf580a6504f2b24d7b3712e16f04ad44faa9eda6722222d022d38e20f3ef070",
    "candidate-manifest.json": "ab3824cd9e5d851168769e585a25f9b60563fdde3d3c2d5c9bd18908bb0b4e78",
    "tests/test_full_publisher_rehearsal.py": "ba4fe1b5053a95c2a5a72eb9ff04fc127cfe5aa5de97e8130bca5a908f6e48aa",
}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def entries(source_root=HERE):
    values = {
        "current-manifest.json": json.dumps({name: {"sha256": value} for name, value in CURRENT_HASHES.items()}, indent=2).encode(),
        "candidate-manifest.json": json.dumps({name: {"sha256": value} for name, value in CANDIDATE_HASHES.items()}, indent=2).encode(),
    }
    source_root = Path(source_root).resolve()
    for name, expected in FROZEN_FILES.items():
        if name not in values:
            path = source_root / name
            if path.is_symlink() or path.resolve() != path or not path.is_file():
                raise ValueError("PUBLISHER_PACKAGE_SOURCE_PATH:" + name)
            values[name] = path.read_bytes()
        if _sha(values[name]) != expected:
            raise ValueError("PUBLISHER_PACKAGE_SOURCE_SHA:" + name)
    values["bundle-manifest.json"] = json.dumps({
        "scope": "TRUSTED_CODE_ISOLATED_PUBLISHER", "files": FROZEN_FILES,
    }, indent=2).encode()
    return {"bundle-v2/" + name: data for name, data in values.items()}


def archive_bytes(source_root=HERE):
    members = entries(source_root)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    data = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if len(archive.infolist()) != 8 or set(archive.namelist()) != set(members):
            raise ValueError("PUBLISHER_PACKAGE_MEMBER_SET")
        if any(archive.read(name) != expected for name, expected in members.items()):
            raise ValueError("PUBLISHER_PACKAGE_MEMBER_READBACK")
    return data, {name: _sha(value) for name, value in sorted(members.items())}


def package(output, source_root=HERE):
    output = Path(output).absolute()
    if output.parent.resolve() != output.parent or output.is_symlink() or output.exists():
        raise ValueError("PUBLISHER_PACKAGE_OUTPUT_EXISTS_OR_NOT_CANONICAL")
    data, hashes = archive_bytes(source_root)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    owned = os.fstat(descriptor)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # Remove only the exact inode this call exclusively created.
        try:
            current = output.lstat()
            if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                output.unlink()
        except OSError:
            pass
        raise
    return {"output": str(output), "sha256": _sha(data), "bytes": len(data), "member_sha256": hashes,
            "reproducibility": "fixed ZIP metadata; exact server-tested v2 member bytes",
            "production_source_included": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.output), indent=2))


if __name__ == "__main__":
    main()
