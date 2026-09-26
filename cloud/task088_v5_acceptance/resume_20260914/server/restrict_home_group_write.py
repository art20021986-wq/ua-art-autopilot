"""Remove only the observed group-write bit on Carix's home directory.

No file content is read or written; no credential or child directory is created.
Exact metadata is compared on a directory fd, avoiding symlink/path substitution.
"""
import sys
import json
import os
import stat


def main():
    descriptors = []
    result = {'kind': 'EXACT_HOME_GROUP_WRITE_REMOVAL', 'path': '/home/Carix',
              'file_contents_read': False, 'file_contents_written': False,
              'credential_created': False, 'chmod_attempted': False}
    try:
        if not sys.flags.isolated or not sys.dont_write_bytecode:
            raise ValueError('ISOLATED_NO_BYTECODE_REQUIRED')
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        descriptor = os.open('/', flags)
        descriptors.append(descriptor)
        for name in ('home', 'Carix'):
            descriptor = os.open(name, flags, dir_fd=descriptor)
            descriptors.append(descriptor)
        before = os.fstat(descriptor)
        if (not stat.S_ISDIR(before.st_mode) or before.st_uid != os.geteuid()
                or before.st_uid != 23671234 or before.st_gid != 60000
                or stat.S_IMODE(before.st_mode) != 0o775 or before.st_size != 98304):
            raise ValueError('OBSERVED_HOME_METADATA_REQUIRED')
        result['before'] = {'uid': before.st_uid, 'gid': before.st_gid,
                            'mode': '0775', 'bytes': before.st_size,
                            'device': before.st_dev, 'inode': before.st_ino}
        current = os.stat('Carix', dir_fd=descriptors[-2], follow_symlinks=False)
        if (current.st_dev, current.st_ino, current.st_uid, current.st_gid,
                current.st_mode, current.st_size) != (before.st_dev, before.st_ino,
                before.st_uid, before.st_gid, before.st_mode, before.st_size):
            raise ValueError('HOME_METADATA_CHANGED_BEFORE_CHMOD')
        result['chmod_attempted'] = True
        os.fchmod(descriptor, stat.S_IMODE(before.st_mode) & ~0o020)
        after = os.fstat(descriptor)
        current = os.stat('Carix', dir_fd=descriptors[-2], follow_symlinks=False)
        if (after.st_uid != before.st_uid or after.st_gid != before.st_gid
                or stat.S_IMODE(after.st_mode) != 0o755
                or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError('HOME_MODE_READBACK_REQUIRES_REVIEW')
        result.update(status='HOME_MODE_0755_CONFIRMED', after_mode='0755',
                      permission_bits_removed='GROUP_WRITE_ONLY')
    except Exception as error:
        result.update(status='HOME_PERMISSION_FIX_NOT_CONFIRMED', error_type=type(error).__name__)
        message = str(error)
        result['code'] = message if message.isupper() and message.replace('_', '').isalnum() and len(message) < 100 else 'REDACTED_ERROR_MESSAGE'
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0 if result['status'] == 'HOME_MODE_0755_CONFIRMED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
