"""Synthetic filesystem failures must never publish an accepted backup marker."""
import errno
import hashlib
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from scripts import backup_server as backup
from scripts import install_server as installer

class BackupSealTests(unittest.TestCase):
    def _exercise(self, case):
        original_fsync, original_open = os.fsync, os.open
        owned = tempfile.TemporaryDirectory(prefix='bos-a10-seal-')
        self.addCleanup(owned.cleanup)
        work = Path(owned.name); work.chmod(0o700)
        source = work / 'untouched_source.bin'
        installer.new_file(source, b'NEW SYNTHETIC SOURCE; NEVER A PRODUCTION DATABASE')
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        destination = work / 'backup'; destination.mkdir(mode=0o700)
        installer.new_file(destination / 'STARTED.json', backup.canonical({'fixture': 'seal metadata only'}))
        code = destination / 'code'; code.mkdir(mode=0o700)
        (code / 'boss_project').mkdir(mode=0o700)
        for relative, body in {'manage.py': b'# metadata fixture only\n', 'requirements.txt': b'# no runtime install\n',
                              'boss_project/version.py': b"VERSION = '0.2.9-fixture'\n"}.items():
            installer.new_file(code / relative, body)
        manifest = {'format': backup.FORMAT, 'payload': backup.inventory(installer, destination),
                    'code_source': installer.source_identity(code)}
        installer.new_file(destination / 'MANIFEST.json', backup.canonical(manifest))
        value = {'format': backup.FORMAT, 'manifest_sha256': backup.checksum(destination / 'MANIFEST.json')}
        faults = []
        def fsync(fd):
            kind = 'directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file'
            if (case == 'file_fsync_failure' and kind == 'file') or (case == 'directory_fsync_failure' and kind == 'directory'):
                faults.append(kind + '_fsync')
                raise OSError(errno.EIO, 'synthetic fault')
            return original_fsync(fd)
        def opened(path, flags, *args, **kwargs):
            if case == 'directory_open_failure' and Path(path) == destination:
                faults.append('directory_open')
                raise OSError(errno.EMFILE, 'synthetic fault')
            return original_open(path, flags, *args, **kwargs)
        observed = None
        try:
            with patch.object(backup.os, 'fsync', fsync), patch.object(backup.os, 'open', opened):
                backup._seal_complete(installer, destination, value)
        except OSError as error:
            observed = {'type': type(error).__name__, 'errno': error.errno}
        accepted = False
        try:
            backup.inspect_backup(installer=installer, source=destination)
            accepted = True
        except (ValueError, OSError):
            pass
        row = {'case': case, 'work': str(work), 'injected': faults, 'error': observed,
               'complete_marker_exists': (destination / 'COMPLETE').exists(),
               'pending_marker_exists': (destination / 'PENDING_COMPLETE').exists(),
               'inspect_backup_accepted': accepted,
               'source_unchanged': hashlib.sha256(source.read_bytes()).hexdigest() == before}
        if case == 'positive':
            assert observed is None and faults == [] and accepted and row['complete_marker_exists'] and not row['pending_marker_exists']
            assert (destination / 'COMPLETE').read_bytes() == backup.canonical(value)
        else:
            assert len(faults) == 1 and observed and not accepted and not row['complete_marker_exists'] and not row['pending_marker_exists']
        assert row['source_unchanged']
        row['passed'] = True
        self.assertTrue(row['passed'])

    def test_file_fsync_failure(self):
        self._exercise('file_fsync_failure')

    def test_directory_open_failure(self):
        self._exercise('directory_open_failure')

    def test_directory_fsync_failure(self):
        self._exercise('directory_fsync_failure')

    def test_positive(self):
        self._exercise('positive')
