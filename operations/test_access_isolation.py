"""Actual durable HTTP and exclusively owned gate baseline regression."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def run_probe(project_root):
    ROOT = Path(project_root).resolve()
    sys.path.insert(0, str(ROOT))
    from scripts.access_isolation import OwnedSweepSQLite
    with tempfile.TemporaryDirectory(prefix='bos-gate4-durable-proof-') as folder:
        work=Path(folder)
        db=work / ('check_'+uuid4().hex+'.sqlite3')
        owner=OwnedSweepSQLite.create_new(db, ROOT)
        media=work/'media'
        media.mkdir(mode=0o700)
        (media/'baseline.txt').write_bytes(b'synthetic baseline media')
        os.environ.update(DJANGO_SETTINGS_MODULE='verification_settings', BOS_VERIFY_DB='sqlite',
            BOS_TEST_DB_NAME=str(db), BOS_TEST_MEDIA=str(media), PYTHONDONTWRITEBYTECODE='1')
        import django
        django.setup()
        from django.conf import settings
        from django.core.management import call_command
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.db import connection, transaction
        from django.test import Client, override_settings
        from operations.models import Document, Configuration
        from operations.private_storage import verified_document_bytes
        from scripts.check_support import login_test_client
        from scripts.check_document_migration import _rows
        from scripts.data_transfer import media_manifest
        owner.assert_owned(connection)
        call_command('migrate', verbosity=0, interactive=False)
        Configuration.objects.create(key='erp_write',value={'revision':0})
        with override_settings(BOS_DATA_MODE='working', DEBUG=False, ANTHROPIC_API_KEY='',
                PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher']):
            clients={}
            for role in ('ceo','manager'):
                client=Client(enforce_csrf_checks=True,raise_request_exception=False)
                login_test_client(client,role,capabilities=('view_document','download_document'))
                clients[role]=client
            data=b'Synthetic gate4 actual uploaded original'
            def upload(client):
                return client.post('/api/operations/documents/upload/',{'file':SimpleUploadedFile('proof.txt',data),
                    'code':'A04-NEW-DOC','revision':'A','title':'Синтетичний gate4 документ'},
                    HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
            result={'red':[],'green':[],'guards':{}}
            before=_rows(connection)
            before_media=media_manifest(media)
            original_database_bytes=db.read_bytes()
            try:
                OwnedSweepSQLite.create_new(db, ROOT)
            except FileExistsError:
                result['guards']['existing_database_refused']=True
            else:
                raise AssertionError('Existing database unexpectedly accepted')
            assert db.read_bytes()==original_database_bytes
            forged=object.__new__(OwnedSweepSQLite)
            try:
                forged.assert_owned(connection)
            except ValueError:
                result['guards']['forged_owner_refused']=True
            else:
                raise AssertionError('Forged owner unexpectedly accepted')
            connection.close()
            saved=db.with_suffix('.saved-owned.sqlite3')
            db.rename(saved)
            replacement=b'synthetic replacement must remain untouched'
            db.write_bytes(replacement)
            try:
                try:
                    owner.assert_owned(connection)
                except ValueError:
                    result['guards']['replaced_inode_refused']=True
                else:
                    raise AssertionError('Replaced inode unexpectedly accepted')
                assert db.read_bytes()==replacement and saved.read_bytes()==original_database_bytes
            finally:
                db.unlink()
                saved.rename(db)
            owner.assert_owned(connection)
            assert _rows(connection)==before
            for role,client in clients.items():
                with transaction.atomic():
                    response=upload(client)
                    assert response.status_code==500
                    assert response.exc_info and response.exc_info[0] is RuntimeError
                    assert 'durable atomic block cannot be nested' in str(response.exc_info[1])
                    result['red'].append({'role':role,'status':response.status_code,
                        'exception':str(response.exc_info[1]),'original_rows_unchanged':_rows(connection)==before})
                    transaction.set_rollback(True)
            for role,client in clients.items():
                with owner.committed_case(connection,media) as isolation:
                    response=upload(client)
                    assert response.status_code==201,response.content
                    doc=Document.objects.get(pk=response.json()['id'])
                    assert bytes(doc.content)==b'' and doc.size==len(data)
                    assert doc.checksum==hashlib.sha256(data).hexdigest()
                    assert verified_document_bytes(doc)==data
                    assert _rows(connection)!=before
                    assert not connection.in_atomic_block and connection.get_autocommit()
                    result['green'].append({'role':role,'status':201,'changed':True,'actual_private_bytes_match':True,'isolation':isolation})
                assert isolation['restored']
                assert _rows(connection)==before and media_manifest(media)==before_media
                assert Document.objects.count()==0
            class SyntheticCaseFailure(RuntimeError):
                pass
            exception_isolation=None
            try:
                with owner.committed_case(connection,media) as exception_isolation:
                    response=upload(clients['ceo'])
                    assert response.status_code==201,response.content
                    assert Document.objects.count()==1
                    raise SyntheticCaseFailure('synthetic failure after actual commit')
            except SyntheticCaseFailure:
                pass
            else:
                raise AssertionError('Harness swallowed the case exception')
            assert exception_isolation['restored']
            assert _rows(connection)==before and media_manifest(media)==before_media
            result['exception_after_commit_restored']=True
            print(json.dumps(result,ensure_ascii=False,indent=2))
        connection.close()


class A08AccessIsolationTests(SimpleTestCase):
    def test_durable_http_commits_and_owned_baseline_restores_exactly(self):
        completed = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--probe', str(ROOT)],
            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=60,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(completed.returncode, 0, completed.stdout + '\n' + completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual([row['status'] for row in result['red']], [500, 500])
        self.assertEqual([row['status'] for row in result['green']], [201, 201])
        self.assertTrue(all(row['isolation']['restored'] for row in result['green']))
        self.assertEqual(result['guards'], {'existing_database_refused': True,
            'forged_owner_refused': True, 'replaced_inode_refused': True})
        self.assertTrue(result['exception_after_commit_restored'])
        print('BOS_A08_ACCESS_ISOLATION ' + json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__' and len(sys.argv) == 3 and sys.argv[1] == '--probe':
    run_probe(sys.argv[2])
