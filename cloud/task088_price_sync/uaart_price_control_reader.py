#!/usr/bin/env python3
"""Authenticated read-only GitHub control reader; explicit installation required.

Never creates credentials, GitHub writes, a task, a deployment approval or an
anchor. The only outputs are reviewed private cache paths. Missing authentication,
ambiguous 404s, partial trees, drift and stale observations fail closed.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

CONTRACT = "UA-ART-GITHUB-CONTROL-READER-1"
REPOSITORY = "art20021986-wq/ua-art-autopilot"
ORIGIN = "https://api.github.com"
MODE = "state/EXECUTION_MODE.json"
MANUAL = "state/MANUAL_MODE.md"
HALT = "state/AUTOPILOT_HALT.json"
VERIFIER = "automation/control_plane.py"
MAX_BODY = 8 * 1024 * 1024


def workflow_path(path):
    """Match the complete directory enumerated by the canonical verifier."""
    pure = PurePosixPath(path)
    return pure.parent == PurePosixPath(".github/workflows") and pure.suffix in (".yml", ".yaml")


class ReaderError(Exception):
    """Messages are fixed codes, never server errors, credentials or payloads."""


def encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ReaderError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ReaderError("INVALID_JSON") from None
    if type(value) is not dict:
        raise ReaderError("JSON_OBJECT_REQUIRED")
    return value


def relative(value):
    if type(value) is not str:
        raise ReaderError("EXPLICIT_RELATIVE_PATH_REQUIRED")
    pure = PurePosixPath(value)
    if (not pure.parts or pure.is_absolute() or pure.as_posix() != value
            or any(part in (".", "..") for part in pure.parts)):
        raise ReaderError("PATH_OUTSIDE_REVIEWED_ROOT")
    return pure


def local(root, value):
    pure = relative(value)
    for path in (root, *(root.joinpath(*pure.parts[:i]) for i in range(1, len(pure.parts)+1))):
        if path.is_symlink():
            raise ReaderError("SYMLINK_FORBIDDEN")
    return root.joinpath(*pure.parts)


def read(path, *, private=False, limit=MAX_BODY):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ReaderError("BOUNDED_REGULAR_FILE_REQUIRED")
        if private and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise ReaderError("PRIVATE_OWNER_FILE_REQUIRED")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(limit+1)
        if len(raw) > limit:
            raise ReaderError("FILE_TOO_LARGE")
        return raw
    finally:
        os.close(descriptor)


def atomic(path, raw):
    temporary = path.with_name(path.name + ".tmp-" + secrets.token_hex(12))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
    finally:
        if temporary.exists(): temporary.unlink()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReaderError("AUTHENTICATED_REDIRECT_FORBIDDEN")


class GitHub:
    """GET-only fixed-origin API client. No anonymous or redirect fallback."""
    def __init__(self, token_path):
        self.token_path = token_path
        self.opener = urllib.request.build_opener(NoRedirect())

    def get(self, suffix):
        if not re.fullmatch(r"(?:/git/ref/heads/main|/git/commits/[0-9a-f]{40}|/git/trees/[0-9a-f]{40}\?recursive=1|/git/blobs/[0-9a-f]{40})", suffix):
            raise ReaderError("GET_ENDPOINT_NOT_ALLOWED")
        raw = read(self.token_path, private=True, limit=4096).strip()
        if not raw or any(byte < 33 or byte > 126 for byte in raw):
            raise ReaderError("EXPLICIT_GITHUB_READER_CREDENTIAL_REQUIRED")
        request = urllib.request.Request(ORIGIN + "/repos/" + REPOSITORY + suffix,
            method="GET", headers={"Authorization":"Bearer " + raw.decode("ascii"),
                "Accept":"application/vnd.github+json", "X-GitHub-Api-Version":"2026-03-10",
                "User-Agent":"UA-ART-price-control-reader/1", "Cache-Control":"no-cache"})
        del raw
        try:
            with self.opener.open(request, timeout=8) as response:
                if response.status != 200:
                    raise ReaderError("AUTHENTICATED_READ_NOT_200")
                body = response.read(MAX_BODY+1)
            if len(body) > MAX_BODY:
                raise ReaderError("API_RESPONSE_TOO_LARGE")
            return parse(body)
        except urllib.error.HTTPError as exc:
            # In particular a 404 never proves that HALT is absent.
            raise ReaderError("GITHUB_HTTP_" + str(exc.code)) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ReaderError("AUTHENTICATED_GITHUB_READ_FAILED") from None


def verify_canonical(snapshot, expected_sha):
    """Execute only the exact installed/pinned canonical read-only verifier.

    A child process receives no token or inherited credential environment.
    It calls the existing full verify_execution_mode, not a replacement mode flag.
    """
    if sha(read(snapshot / VERIFIER)) != expected_sha:
        raise ReaderError("CANONICAL_VERIFIER_PIN_MISMATCH")
    script = """import importlib.util,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);s=importlib.util.spec_from_file_location('canonical_price_controls',p/'automation/control_plane.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
r=m.verify_execution_mode(root=p,required_mode='AUTOMATIC')
print(json.dumps(r))
"""
    result = subprocess.run([sys.executable,"-I","-B","-c",script,str(snapshot)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20,
        env={"PATH":"/usr/bin:/bin"}, check=False)
    if result.returncode != 0:
        raise ReaderError("CANONICAL_EXECUTION_MODE_REJECTED")
    record = parse(result.stdout)
    if (record.get("status") != "PASS" or record.get("mode") != "AUTOMATIC"
            or record.get("automatic_production") is not True):
        raise ReaderError("CANONICAL_AUTOMATIC_PRODUCTION_REQUIRED")
    return record


class Reader:
    def __init__(self, config_path, expected_sha256, *, test_root=None, test_api=None, clock=None):
        self.root = Path("/home/Carix") if test_root is None else Path(test_root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ReaderError("EXPLICIT_OWNER_ROOT_REQUIRED")
        self.path = Path(config_path)
        if self.path != local(self.root,str(self.path.relative_to(self.root))):
            raise ReaderError("CONFIG_OUTSIDE_ROOT")
        self.raw = read(self.path,private=True)
        if not re.fullmatch(r"[0-9a-f]{64}",expected_sha256) or sha(self.raw) != expected_sha256:
            raise ReaderError("INSTALLER_CONFIG_PIN_MISMATCH")
        self.config_sha = expected_sha256
        c = self.config = parse(self.raw)
        if (c.get("contract") != CONTRACT or c.get("repository") != REPOSITORY or c.get("ref") != "refs/heads/main"
                or c.get("environment") != ("TEST" if test_root is not None else "PRODUCTION")
                or c.get("root") != str(self.root)):
            raise ReaderError("EXACT_REPOSITORY_ENVIRONMENT_REQUIRED")
        if not re.fullmatch(r"TASK088-GE-PRICE-SITE-STAGE3-[A-Za-z0-9-]+",c.get("task_id", "")):
            raise ReaderError("EXACT_PRICE_TASK_REQUIRED")
        if not re.fullmatch(r"[0-9a-f]{64}",c.get("delegation_sha256", "")):
            raise ReaderError("DELEGATION_BINDING_REQUIRED")
        self.source = "github:" + REPOSITORY + ":main"
        if c.get("source") != self.source or type(c.get("max_age_ms")) is not int or not 1000 <= c["max_age_ms"] <= 30000:
            raise ReaderError("BOUNDED_CANONICAL_SOURCE_REQUIRED")
        if type(c.get("poll_interval_ms")) is not int or not 1000 <= c["poll_interval_ms"] <= c["max_age_ms"]//2:
            raise ReaderError("BOUNDED_RENEWAL_INTERVAL_REQUIRED")
        self.pins = c.get("canonical_file_pins")
        if type(self.pins) is not dict or not {MODE,MANUAL,VERIFIER} <= set(self.pins) or HALT in self.pins:
            raise ReaderError("FULL_CANONICAL_CHAIN_PINS_REQUIRED")
        for path, digest in self.pins.items():
            relative(path)
            if not re.fullmatch(r"[0-9a-f]{64}",digest):
                raise ReaderError("CANONICAL_FILE_SHA256_REQUIRED")
        refs = c.get("price_artifacts")
        if type(refs) is not dict or set(refs) != {"manifest","request","owner_approval","gate_b"}:
            raise ReaderError("CANONICAL_PRICE_ARTIFACT_PATHS_REQUIRED")
        if any(type(path) is not str or path not in self.pins for path in refs.values()):
            raise ReaderError("PRICE_ARTIFACT_PIN_REQUIRED")
        paths = [local(self.root,c[key]) for key in ("token_file","state_path","freshness_path","cache_dir")]
        if (len(set(paths + [self.path])) != len(paths) + 1
                or any(path.relative_to(self.root).parts[0] in ("video","site") for path in paths)
                or any(parent in child.parents for parent in paths for child in paths if parent != child)):
            raise ReaderError("DISTINCT_PRIVATE_READER_PATHS_REQUIRED")
        self.token_path,self.state_path,self.stamp_path,self.cache_dir = paths
        for path in (self.state_path.parent,self.stamp_path.parent,self.cache_dir):
            info = path.stat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode)&0o077:
                raise ReaderError("PRIVATE_INSTALLED_CACHE_DIRECTORY_REQUIRED")
        if test_api is not None and test_root is None:
            raise ReaderError("SYNTHETIC_TRANSPORT_FORBIDDEN_IN_PRODUCTION")
        self.api = test_api if test_api is not None else GitHub(self.token_path)
        self.clock = clock or (lambda:time.time_ns()//1_000_000)

    def _head(self):
        value=self.api.get("/git/ref/heads/main")
        obj=value.get("object",{})
        if value.get("ref") != "refs/heads/main" or obj.get("type") != "commit" or not re.fullmatch(r"[0-9a-f]{40}",obj.get("sha", "")):
            raise ReaderError("EXACT_CURRENT_MAIN_COMMIT_REQUIRED")
        return obj["sha"]

    def _tree(self,commit):
        record=self.api.get("/git/commits/"+commit)
        tree_sha=record.get("tree",{}).get("sha", "")
        if record.get("sha") != commit or not re.fullmatch(r"[0-9a-f]{40}",tree_sha):
            raise ReaderError("EXACT_COMMIT_TREE_REQUIRED")
        record=self.api.get("/git/trees/"+tree_sha+"?recursive=1")
        if record.get("sha") != tree_sha or record.get("truncated") is not False or type(record.get("tree")) is not list:
            raise ReaderError("COMPLETE_AUTHORITATIVE_TREE_REQUIRED")
        result={}
        for item in record["tree"]:
            path=item.get("path") if type(item) is dict else None
            relative(path)
            if path in result:
                raise ReaderError("DUPLICATE_GIT_TREE_PATH")
            result[path]=item
        if HALT in result:
            raise ReaderError("CANONICAL_HALT_PRESENT")
        # The verifier inventories active workflows. Omitting a newly added
        # remote workflow from its local snapshot would conceal a policy bypass.
        if {path for path in result if workflow_path(path)} != {path for path in self.pins if workflow_path(path)}:
            raise ReaderError("COMPLETE_CANONICAL_WORKFLOW_SET_REQUIRED")
        return result

    def _blob(self,item):
        blob_sha=item.get("sha", "")
        if item.get("type") != "blob" or item.get("mode") not in ("100644","100755") or not re.fullmatch(r"[0-9a-f]{40}",blob_sha):
            raise ReaderError("REGULAR_CANONICAL_GIT_BLOB_REQUIRED")
        cache=local(self.cache_dir,blob_sha+".blob")
        if cache.exists(): raw=read(cache,private=True)
        else:
            record=self.api.get("/git/blobs/"+blob_sha)
            if record.get("sha") != blob_sha or record.get("encoding") != "base64":
                raise ReaderError("EXACT_CANONICAL_BLOB_REQUIRED")
            try: raw=base64.b64decode("".join(record["content"].split()),validate=True)
            except (KeyError,ValueError,TypeError): raise ReaderError("INVALID_GIT_BLOB_ENCODING") from None
        if len(raw)>MAX_BODY or hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()!=blob_sha:
            raise ReaderError("CANONICAL_GIT_BLOB_HASH_MISMATCH")
        if not cache.exists(): atomic(cache,raw)
        return raw

    def observe(self):
        if read(self.path,private=True)!=self.raw:
            raise ReaderError("INSTALLER_READER_CONFIG_CHANGED")
        commit=self._head();tree=self._tree(commit)
        with tempfile.TemporaryDirectory(prefix="verify-",dir=self.cache_dir) as directory:
            snapshot=Path(directory)
            for path,expected in self.pins.items():
                if path not in tree: raise ReaderError("CANONICAL_APPROVAL_OR_CONTROL_REMOVED")
                raw=self._blob(tree[path])
                if sha(raw)!=expected: raise ReaderError("CANONICAL_APPROVAL_OR_CONTROL_DRIFT")
                destination=local(snapshot,path);destination.parent.mkdir(parents=True,exist_ok=True)
                atomic(destination,raw)
            mode=verify_canonical(snapshot,self.pins[VERIFIER])
            refs=self.config["price_artifacts"]
            manifest=parse(read(snapshot/refs["manifest"]))
            request=parse(read(snapshot/refs["request"]))
            if manifest.get("price_event_delegation_sha256")!=self.config["delegation_sha256"] or request.get("task_id")!=self.config["task_id"]:
                raise ReaderError("CANONICAL_PRICE_DELEGATION_CHANGED")
            # The actual Provider verifies full local chain semantics. These
            # exact fresh remote pins independently detect revocation/drift.
            observed=self.clock();started=time.monotonic()
            if self._head()!=commit: raise ReaderError("MAIN_CHANGED_DURING_OBSERVATION")
            finished=self.clock()
            if (type(observed) is not int or type(finished) is not int or not 0<=finished-observed<self.config["max_age_ms"]
                    or time.monotonic()-started>=self.config["max_age_ms"]/1000):
                raise ReaderError("CANONICAL_OBSERVATION_EXPIRED")
            record={"contract":CONTRACT,"source":self.source,"repository":REPOSITORY,"ref":"refs/heads/main",
                    "commit_sha":commit,"task_id":self.config["task_id"],"delegation_sha256":self.config["delegation_sha256"],
                    "reader_config_sha256":self.config_sha,"observed_ms":observed,
                    "mode":mode["mode"],"halt":False,"revoked":False,
                    "canonical_file_pins":self.pins,"halt_evidence":"ABSENT_FROM_COMPLETE_AUTHENTICATED_COMMIT_TREE"}
        raw=encode(record)
        facts={kind:{"path":str(self.state_path),"sha256":sha(raw),"value":value}
               for kind,value in (("mode","AUTOMATIC"),("halt",False),("revocation",False))}
        stamp={"source":self.source,"observed_ms":observed,"observations_sha256":sha(encode(facts)),
               "reader_config_sha256":self.config_sha,"task_id":self.config["task_id"],
               "delegation_sha256":self.config["delegation_sha256"],"commit_sha":commit}
        atomic(self.state_path,raw)
        atomic(self.stamp_path,encode(stamp)) # Commit stamp LAST; torn refresh fails hash verification.
        if read(self.state_path,private=True)!=raw or read(self.stamp_path,private=True)!=encode(stamp):
            raise ReaderError("CONTROL_CACHE_READBACK_FAILED")
        return {"status":"OBSERVED","commit_sha":commit,"observed_ms":observed,
                "valid_until_ms":observed+self.config["max_age_ms"],"production_authorized":False}

    def tick(self):
        descriptor=os.open(local(self.cache_dir,"reader.lock"),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            try: fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: return {"status":"BUSY","production_authorized":False}
            try: return self.observe()
            except Exception as exc:
                reason=str(exc) if isinstance(exc,ReaderError) else type(exc).__name__.upper()
                if not re.fullmatch(r"[A-Z0-9_]{1,100}",reason):reason="CONTROL_READER_FAILED"
                # Do not renew a successful timestamp after any failed read.
                atomic(self.stamp_path,encode({"source":self.source,"status":"BLOCKED","reason":reason}))
                return {"status":"BLOCKED","reason":reason,"production_authorized":False}
        finally: os.close(descriptor)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--config-sha256",required=True)
    parser.add_argument("--loop",action="store_true")
    args=parser.parse_args()
    try: reader=Reader(args.config,args.config_sha256)
    except Exception as exc:
        code=str(exc) if isinstance(exc,ReaderError) else type(exc).__name__.upper()
        print(json.dumps({"status":"BLOCKED","reason":code,"production_authorized":False}));return 2
    while True:
        result=reader.tick();print(json.dumps(result),flush=True)
        if not args.loop:return 0 if result["status"]=="OBSERVED" else 1
        time.sleep(reader.config["poll_interval_ms"]/1000)


if __name__=="__main__":
    raise SystemExit(main())
