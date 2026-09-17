"""A rehearsal worker cannot write an arbitrary correctly named database."""
import os
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4
from django.test import SimpleTestCase
import scripts.check_data_transfer as runner


class TransferWorkerGuardTests(SimpleTestCase):
    def test_postgres_name_ticket_alone_does_not_authorize_a_proof_worker(self):
        with tempfile.TemporaryDirectory(prefix='bos-a07-pg-worker-guard-') as directory:
            work = Path(directory).resolve()
            name = 'bos_verify_' + uuid4().hex[:16]
            token = uuid4().hex
            marker = work / 'worker.json'
            media = work / 'media'
            marker.write_text(json.dumps({'stage': 'proof', 'database': name,
                'backend': 'postgres', 'root': str(work), 'media': str(media),
                'expected': None, 'minimum_id': 1,
                'token_sha256': hashlib.sha256(token.encode()).hexdigest()}))
            env = dict(os.environ, BOS_VERIFY_DB='postgres', BOS_TEST_DB_NAME=name,
                BOS_TEST_MEDIA=str(media), BOS_PG_DISPOSABLE='1',
                BOS_REHEARSAL_MARKER=str(marker), BOS_REHEARSAL_TOKEN=token)
            result = subprocess.run([sys.executable, '-B', '-c',
                "from scripts.check_data_transfer import guard_worker; guard_worker('proof')"],
                cwd=runner.ROOT, env=env, text=True, capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0,
                'A name ticket without a successful CREATE proof was accepted')

    def test_proof_worker_refuses_unissued_external_database_without_touching_it(self):
        with tempfile.TemporaryDirectory(prefix='bos-a07-worker-guard-') as directory:
            path = Path(directory) / ('check_' + uuid4().hex + '.sqlite3')
            path.write_bytes(b'synthetic untouched guard canary')
            env = dict(os.environ, BOS_VERIFY_DB='sqlite', BOS_TEST_DB_NAME=str(path))
            for name in ('BOS_REHEARSAL_MARKER', 'BOS_REHEARSAL_TOKEN'):
                env.pop(name, None)
            result = subprocess.run([sys.executable, '-B', '-c',
                "from scripts.check_data_transfer import guard_worker; guard_worker('proof')"],
                cwd=runner.ROOT, env=env, text=True, capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0, 'Worker accepted a database not issued by this run')
            self.assertEqual(path.read_bytes(), b'synthetic untouched guard canary')
