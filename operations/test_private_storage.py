"""Synthetic file-level checks only. No DB/model integration, no real MEDIA_ROOT."""
import hashlib
import io
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest

from operations import private_storage as storage


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PrivateStorageFiles(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix='a08_storage_synthetic_')
        self.root = Path(self.work.name) / 'media'
        self.root.mkdir(mode=0o700)
        self.store = storage.PrivateDocumentStorage(root=self.root, quota_bytes=32 * 1024 * 1024)

    def tearDown(self):
        self.work.cleanup()

    def save(self, data, **kwargs):
        return self.store.save_verified(data, sha(data), legacy_blob_bytes=kwargs.pop('legacy', 0), **kwargs)

    def files(self):
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*') if p.is_file())

    def document(self, data=b'', **kwargs):
        return SimpleNamespace(content=data, checksum=sha(data), text='', original_file=None,
                               size=None, **kwargs)

    def test_exact_binary_empty_utf8_and_private_permissions(self):
        for data in (b'', b'\x00\xff\x00binary', 'Креслення Ї'.encode()):
            with self.subTest(data=data):
                result = self.save(data)
                self.assertEqual(result.size, len(data))
                self.assertEqual(self.store.read_verified(result.name, result.checksum, expected_size=len(data)), data)
                self.assertEqual(stat.S_IMODE((self.root / result.name).stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE((self.root / result.name).parent.stat().st_mode), 0o700)
        self.assertEqual(len(self.files()), 3)

    def test_exact_10mb_boundary_and_oversize_removes_only_failed_file(self):
        data = b'\x00' * storage.MAX_BYTES
        result = self.save(data)
        before = self.files()
        with self.assertRaises(storage.PrivateFileError):
            self.save(data + b'x')
        self.assertEqual(self.files(), before)
        self.assertEqual(self.store.read_verified(result.name, sha(data)), data)

    def test_no_public_urls_raw_open_write_paths_or_delete(self):
        result = self.save(b'stays')
        for function in (lambda: self.store.url(result.name), lambda: self.store.path(result.name),
                         lambda: self.store.open(result.name), lambda: self.store.delete(result.name),
                         lambda: self.store.save('anything', io.BytesIO(b'change'))):
            with self.assertRaises(storage.PrivateFileError):
                function()
        self.assertEqual(self.store.read_verified(result.name, sha(b'stays')), b'stays')

    def test_invalid_keys_never_read_or_change_files(self):
        result = self.save(b'valid')
        before = self.files()
        for name in ('../secret', '/etc/passwd', 'documents/x/a.blob', result.name + '/..',
                     result.name.replace('/', '\\'), result.name.replace('/' + result.name.split('/')[1] + '/', '/zz/'),
                     result.name + '\x00'):
            with self.subTest(name=name), self.assertRaises(storage.PrivateFileError):
                self.store.read_verified(name, sha(b'valid'))
        self.assertEqual(self.files(), before)

    def test_quota_counts_unbound_physical_files_and_legacy_bytes(self):
        (self.root / 'orphan.bin').write_bytes(b'1234567')
        self.store = storage.PrivateDocumentStorage(root=self.root, quota_bytes=11)
        before = self.files()
        with self.assertRaises(storage.PrivateFileError):
            self.save(b'12', legacy=3)
        self.assertEqual(self.files(), before)
        self.save(b'1', legacy=3)
        self.assertEqual(self.store.usage(legacy_blob_bytes=3), {
            'physical_bytes': 8, 'legacy_blob_bytes': 3, 'total_bytes': 11, 'quota_bytes': 11})
        with self.assertRaises(storage.PrivateFileError):
            self.save(b'1', legacy=3)
        # An actual zero-byte document consumes zero bytes, not an inferred text.
        self.save(b'', legacy=3)
        self.assertEqual(self.store.usage(legacy_blob_bytes=3)['total_bytes'], 11)

    def test_quota_requires_known_nonnegative_integer_including_callable(self):
        before = self.files()
        for value in (None, -1, False, '0', 0.0):
            with self.subTest(value=value), self.assertRaises(storage.PrivateFileError):
                self.store.save_verified(b'a', sha(b'a'), legacy_blob_bytes=value)
        calls = []
        self.store.save_verified(b'a', sha(b'a'), legacy_blob_bytes=lambda: calls.append('count') or 0)
        self.assertEqual(calls, ['count'])
        self.assertEqual(before, [])
        with self.assertRaises(storage.PrivateFileError):
            storage.PrivateDocumentStorage(root=self.root, quota_bytes=False).save_verified(
                b'a', sha(b'a'), legacy_blob_bytes=0)

    def test_bad_checksum_or_interrupted_stream_cleans_exclusive_partial(self):
        saved = self.save(b'keep')
        before = self.files()
        with self.assertRaises(storage.PrivateFileError):
            self.store.save_verified(b'incorrect', sha(b'expected'), legacy_blob_bytes=0)
        class Interrupted:
            seen = False
            def read(self, length):
                if self.seen:
                    raise OSError('synthetic interrupted stream')
                self.seen = True
                return b'partial'
        with self.assertRaises(storage.PrivateFileError):
            self.store.save_verified(Interrupted(), sha(b'partial'), legacy_blob_bytes=0)
        self.assertEqual(self.files(), before)
        self.assertEqual(self.store.read_verified(saved.name, saved.checksum), b'keep')

    def test_corruption_size_conflict_and_buffer_independence(self):
        result = self.save(b'original')
        with self.assertRaises(storage.PrivateFileError):
            self.store.read_verified(result.name, result.checksum, expected_size=999)
        checked = self.store.open_verified(result.name, result.checksum)
        (self.root / result.name).write_bytes(b'changed!')
        self.assertEqual(checked.read(), b'original')
        checked.close()
        with self.assertRaises(storage.PrivateFileError):
            self.store.read_verified(result.name, result.checksum)
        self.assertEqual((self.root / result.name).read_bytes(), b'changed!')

    def test_legacy_exact_bytes_empty_and_exact_utf8_without_repair(self):
        self.assertEqual(storage.verified_document_bytes(self.document(b'\x00\xff')), b'\x00\xff')
        empty = self.document()
        empty.text = 'Цей текст не є оригіналом нульового файла'
        self.assertEqual(storage.verified_document_bytes(empty), b'')
        text = self.document()
        text.text = 'Ї\r\nТекст'
        text.checksum = sha(text.text.encode('utf-8'))
        self.assertEqual(storage.verified_document_bytes(text), text.text.encode())
        text.text = text.text.replace('\r\n', '\n')
        with self.assertRaises(storage.PrivateFileError):
            storage.verified_document_bytes(text)
        wrong = self.document(b'broken')
        wrong.text = 'valid text'
        wrong.checksum = sha(wrong.text.encode())
        with self.assertRaises(storage.PrivateFileError):
            storage.verified_document_bytes(wrong)
        self.assertEqual(wrong.content, b'broken')

    def test_bound_missing_or_corrupt_never_falls_back_to_valid_blob(self):
        result = self.save(b'valid')
        doc = self.document(b'valid')
        doc.original_file = result.name
        doc.size = result.size
        self.assertEqual(storage.verified_document_bytes(doc, storage=self.store), b'valid')
        (self.root / result.name).write_bytes(b'wrong')
        with self.assertRaises(storage.PrivateFileError):
            storage.verified_document_bytes(doc, storage=self.store)
        (self.root / result.name).unlink()
        with self.assertRaises(storage.PrivateFileError):
            storage.verified_document_bytes(doc, storage=self.store)
        self.assertEqual(doc.content, b'valid')

    def test_symlink_in_root_ancestor_document_path_and_quota_refused(self):
        outside = Path(self.work.name) / 'outside'
        outside.mkdir(mode=0o700)
        canary = outside / 'canary'
        canary.write_bytes(b'untouched')
        root_link = Path(self.work.name) / 'root-link'
        root_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(storage.PrivateFileError):
            storage.PrivateDocumentStorage(root=root_link, quota_bytes=99).save_verified(b'a', sha(b'a'), legacy_blob_bytes=0)
        (self.root / 'documents').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(storage.PrivateFileError):
            self.save(b'a')
        with self.assertRaises(storage.PrivateFileError):
            self.store.read_verified('documents/aa/' + 'a'*32 + '.blob', sha(b'untouched'))
        self.assertEqual(canary.read_bytes(), b'untouched')

    def test_final_symlink_hardlink_and_special_file_refused(self):
        result = self.save(b'original')
        path = self.root / result.name
        outside = Path(self.work.name) / 'outside'
        outside.write_bytes(b'original')
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaises(storage.PrivateFileError):
            self.store.read_verified(result.name, result.checksum)
        path.unlink()
        outside.chmod(0o600)
        os.link(outside, path)
        with self.assertRaises(storage.PrivateFileError):
            self.store.read_verified(result.name, result.checksum)
        path.unlink()
        fifo = self.root / 'fifo'
        os.mkfifo(fifo)
        with self.assertRaises(storage.PrivateFileError):
            self.save(b'another')
        self.assertEqual(outside.read_bytes(), b'original')

    def test_exclusive_create_and_portable_path_branch_on_real_files(self):
        tree = storage._Tree(self.root)
        # Exercise the portable implementation directly on genuine files. This
        # is Linux path-branch coverage, NOT a Windows OS/ACL/junction acceptance.
        tree.close()
        tree.anchored = False
        with tree.directory(('documents', 'aa'), create=True) as directory:
            fd = tree.open_file(directory, 'a'*32 + '.blob', create=True)
            with os.fdopen(fd, 'wb') as output:
                output.write(b'keep')
            with self.assertRaises(FileExistsError):
                tree.open_file(directory, 'a'*32 + '.blob', create=True)
            fd = tree.open_file(directory, 'a'*32 + '.blob')
            with os.fdopen(fd, 'rb') as incoming:
                self.assertEqual(incoming.read(), b'keep')
        self.assertEqual(tree.physical_bytes(), 4)
        link = self.root / 'evil'
        link.symlink_to(Path(self.work.name))
        with self.assertRaises(storage.PrivateFileError):
            tree.physical_bytes()

    def test_missing_lookup_false_and_existing_nonprivate_document_directory_refused(self):
        self.assertFalse(self.store.exists('documents/aa/' + 'a'*32 + '.blob'))
        private_directory = self.root / 'documents'
        private_directory.mkdir(mode=0o755)
        private_directory.chmod(0o755)
        with self.assertRaises(storage.PrivateFileError):
            self.save(b'a')
        self.assertEqual(stat.S_IMODE(private_directory.stat().st_mode), 0o755)
        self.assertEqual(self.files(), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
