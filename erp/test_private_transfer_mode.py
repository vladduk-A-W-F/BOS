"""Actual typed exporter nested-private-directory regression (synthetic DB)."""
import os
from pathlib import Path
import unittest

from erp import test_data_transfer as synthetic_fixture
from operations.private_storage import PrivateDocumentStorage
from scripts import data_transfer as transfer


class A08PrivateTransferModeTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'Actual POSIX mode proof; Windows ACL proof remains separate')
    def test_nested_private_media_export_preserves_private_directory_access(self):
        fixture=synthetic_fixture.SyntheticTransfer(methodName='test_exact_round_trip_system_ids_types_and_empty_sequences')
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        key='documents/ab/'+'ab'+'1'*30+'.blob'
        data=bytes(range(256))
        for folder in (fixture.media/'documents',fixture.media/'documents/ab'):
            folder.mkdir(mode=0o700)
        path=fixture.media/key
        path.write_bytes(data)
        path.chmod(0o600)
        fixture.mutate('UPDATE demo_record SET file=? WHERE id=90001',(key,))
        old_umask=os.umask(0o022)
        try:
            bundle, manifest=fixture.export()
        finally:
            os.umask(old_umask)
        self.assertEqual(transfer.file_hash(fixture.source),fixture.original)
        self.assertEqual(transfer.media_manifest(fixture.media),transfer.media_manifest(bundle/'media'))
        modes={str(p.relative_to(bundle)):p.stat().st_mode & 0o777
               for p in (bundle/'media',bundle/'media/documents',bundle/'media/documents/ab',bundle/'media'/key)}
        print('BOS_A08_TRANSFER_MODES '+str(modes))
        self.assertEqual(modes,{'media':0o700,'media/documents':0o700,'media/documents/ab':0o700,'media/'+key:0o600})
        with __import__('django.test',fromlist=['override_settings']).override_settings(MEDIA_ROOT=bundle/'media'):
            storage=PrivateDocumentStorage()
            self.assertEqual(storage.read_verified(key,transfer.file_hash(path),expected_size=256),data)
