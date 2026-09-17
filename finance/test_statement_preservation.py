"""Execute schema/typed proofs only on a fresh dedicated child database."""
import os,subprocess,sys,tempfile
from pathlib import Path
from uuid import uuid4
from django.test import SimpleTestCase

class StatementPreservationIsolationTests(SimpleTestCase):
    def test_earlier_schema_reverse_guard_and_populated_typed_transfer(self):
        with tempfile.TemporaryDirectory(prefix='bos-c03-preservation-') as folder:
            work=Path(folder);db=work/('check_'+uuid4().hex+'.sqlite3');media=work/'media';media.mkdir(mode=0o700)
            env=dict(os.environ,DJANGO_SETTINGS_MODULE='verification_settings',BOS_VERIFY_DB='sqlite',BOS_TEST_DB_NAME=str(db),BOS_TEST_MEDIA=str(media),PYTHONDONTWRITEBYTECODE='1')
            run=subprocess.run([sys.executable,'-B','manage.py','test','fixtures.synthetic.statement_migration.StatementMigrationTests','--noinput','-v2'],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True,timeout=120)
            self.assertEqual(run.returncode,0,run.stdout+'\n'+run.stderr);self.assertIn('Ran 3 tests',run.stderr);self.assertIn('OK',run.stderr)
            for line in run.stdout.splitlines():
                if line.startswith('C03_'):print(line)
