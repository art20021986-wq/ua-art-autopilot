# UA-SITE-COUNTERS-123:START
from ua_site_counters import prepare_updates as _ua123_prepare_updates

_UA123_BASE_SNAPSHOT = Snapshot
_UA123_BASE_INSTALL = _install_catalog


class Snapshot(_UA123_BASE_SNAPSHOT):
    """Include homepage counters in the existing publication rollback."""
    def __init__(self, codes):
        super().__init__(codes)
        manifest_path = self.root / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for folder in ROOTS:
            path = folder / 'index.html'
            if not path.is_file() or str(path) in manifest:
                continue
            data = _read(path)
            relative = pathlib.Path('files') / (str(path.relative_to(ROOT)) + '.gz')
            _atomic(self.root / relative, _ua099_gzip.compress(data, compresslevel=9, mtime=0), 0o600)
            manifest[str(path)] = {
                'exists': True, 'path': str(path), 'sha256': _sha(data),
                'mode': path.stat().st_mode & 0o777, 'storage': 'gzip-v1',
                'stored_relative': str(relative),
            }
            self.before_paths.add(path)
            self.present.add(path)
        _atomic(manifest_path, (json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode(), 0o600)


def _install_catalog(source, target):
    # Both callers already hold the publisher lock and own Snapshot rollback.
    result = _UA123_BASE_INSTALL(source, target)
    updates, counts = _ua123_prepare_updates(ROOTS)
    for path, before, after in updates:
        if _read(path) != before:
            raise PublishError('COUNTER_SOURCE_CHANGED:' + str(path))
        if after != before:
            _atomic(path, after, path.stat().st_mode & 0o777)
        if _read(path) != after:
            raise PublishError('COUNTER_READBACK:' + str(path))
    result['site_counters'] = counts
    rows, _ = _row_map()
    for path_string, evidence in result.get('installed', {}).items():
        path = pathlib.Path(path_string)
        evidence['sha256'] = _sha(_read(path))
        evidence['audit'] = _validate_catalog(_read(path).decode('utf-8'), rows)
    return result
# UA-SITE-COUNTERS-123:END
