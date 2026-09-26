"""Root review regressions: trusted shared MEDIA root and owned rollback cleanup."""
import dataclasses
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

from operations import private_storage as storage


def sha(data):
    return hashlib.sha256(data).hexdigest()


class StorageOwnershipReview(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix='a08_ownership_synthetic_')
        self.root = Path(self.work.name) / 'media'
        self.root.mkdir(mode=0o700)
        self.store = storage.PrivateDocumentStorage(root=self.root, quota_bytes=1024)

    def tearDown(self):
        self.work.cleanup()

    def save(self, data=b'new'):
        return self.store.save_verified(data, sha(data), legacy_blob_bytes=0)

    def require_api(self):
        self.assertTrue(callable(getattr(self.store, 'discard_new', None)),
                        'A08 DOC13 needs owned rollback cleanup')
        self.assertTrue(callable(getattr(self.store, 'finalize', None)),
                        'Commit must revoke the cleanup capability')

    def test_existing_shared_media0755_unchanged_private_subdirs0700(self):
        self.root.chmod(0o755)
        (self.root / 'chat').mkdir(mode=0o755)
        old = self.root / 'chat' / 'legacy.bin'
        old.write_bytes(b'legacy')
        old.chmod(0o644)
        result = self.save()
        self.assertEqual(self.store.read_verified(result.name, result.checksum), b'new')
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(old.stat().st_mode), 0o644)
        self.assertEqual(old.read_bytes(), b'legacy')
        self.assertEqual(stat.S_IMODE((self.root / 'documents').stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.root / result.name).parent.stat().st_mode), 0o700)
        self.assertEqual(self.store.usage(legacy_blob_bytes=0)['physical_bytes'], 9)

    def test_sql_rollback_discards_only_this_new_file_and_revokes_receipt(self):
        self.require_api()
        keep = self.save(b'committed file')
        self.store.finalize(keep)
        connection = sqlite3.connect(Path(self.work.name) / 'check.sqlite3')
        try:
            connection.execute('CREATE TABLE proof (code TEXT UNIQUE, file TEXT)')
            connection.execute('INSERT INTO proof VALUES (?, ?)', ('A', keep.name))
            connection.commit()
            receipt = None
            with self.assertRaises(sqlite3.IntegrityError):
                with connection:
                    receipt = self.save(b'rollback file')
                    connection.execute('INSERT INTO proof VALUES (?, ?)', ('B', receipt.name))
                    connection.execute('INSERT INTO proof VALUES (?, ?)', ('A', receipt.name))
            self.assertEqual(connection.execute('SELECT code, file FROM proof').fetchall(), [('A', keep.name)])
            self.store.discard_new(receipt)
            self.assertFalse((self.root / receipt.name).exists())
            self.assertEqual((self.root / keep.name).read_bytes(), b'committed file')
            with self.assertRaises(storage.PrivateFileError):
                self.store.discard_new(receipt)
            self.assertEqual(self.store.usage(legacy_blob_bytes=0)['physical_bytes'], len(b'committed file'))
        finally:
            connection.close()

    def test_commit_finalize_revokes_cleanup_and_raw_delete_stays_forbidden(self):
        self.require_api()
        receipt = self.save()
        self.store.finalize(receipt)
        for call in (lambda: self.store.discard_new(receipt), lambda: self.store.delete(receipt.name)):
            with self.assertRaises(storage.PrivateFileError):
                call()
        self.assertEqual((self.root / receipt.name).read_bytes(), b'new')

    def test_forged_equal_receipt_or_other_storage_instance_cannot_cleanup(self):
        self.require_api()
        receipt = self.save()
        forged = dataclasses.replace(receipt)
        self.assertEqual(forged, receipt)
        other = storage.PrivateDocumentStorage(root=self.root, quota_bytes=1024)
        for candidate, owner in ((forged, self.store), (receipt, other),
                                 (object(), self.store), (receipt.name, self.store)):
            with self.assertRaises(storage.PrivateFileError):
                owner.discard_new(candidate)
        self.assertEqual((self.root / receipt.name).read_bytes(), b'new')
        self.store.discard_new(receipt)
        self.assertFalse((self.root / receipt.name).exists())

    def test_replaced_inode_is_not_deleted_even_when_bytes_match(self):
        self.require_api()
        receipt = self.save()
        original = self.root / receipt.name
        # Keep the original inode alive so the filesystem cannot reuse its ID.
        renamed = original.with_name('original-kept.blob')
        original.rename(renamed)
        original.write_bytes(b'new')
        original.chmod(0o600)
        with self.assertRaises(storage.PrivateFileError):
            self.store.discard_new(receipt)
        self.assertEqual(original.read_bytes(), b'new')
        self.assertEqual(renamed.read_bytes(), b'new')

    def test_changed_content_on_owned_inode_is_not_deleted(self):
        self.require_api()
        receipt = self.save()
        path = self.root / receipt.name
        path.write_bytes(b'newly changed')
        with self.assertRaises(storage.PrivateFileError):
            self.store.discard_new(receipt)
        self.assertEqual(path.read_bytes(), b'newly changed')

    def test_symlink_replacement_cannot_delete_the_destination(self):
        self.require_api()
        receipt = self.save()
        path = self.root / receipt.name
        outside = Path(self.work.name) / 'external'
        outside.write_bytes(b'keep external')
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaises(storage.PrivateFileError):
            self.store.discard_new(receipt)
        self.assertTrue(path.is_symlink())
        self.assertEqual(outside.read_bytes(), b'keep external')

    def test_changed_receipt_payload_and_root_replacement_are_refused(self):
        self.require_api()
        receipt = self.save()
        original_name = receipt.name
        object.__setattr__(receipt, 'name', 'documents/aa/' + 'a' * 32 + '.blob')
        with self.assertRaises(storage.PrivateFileError):
            self.store.discard_new(receipt)
        object.__setattr__(receipt, 'name', original_name)
        moved = self.root.with_name('original-root')
        self.root.rename(moved)
        self.root.mkdir(mode=0o700)
        replacement = self.root / receipt.name
        replacement.parent.mkdir(mode=0o700, parents=True)
        replacement.write_bytes(b'new')
        replacement.chmod(0o600)
        with self.assertRaises(storage.PrivateFileError):
            self.store.discard_new(receipt)
        self.assertEqual(replacement.read_bytes(), b'new')
        self.assertEqual((moved / receipt.name).read_bytes(), b'new')


if __name__ == '__main__':
    unittest.main(verbosity=2)
