"""Finite A08 regressions, using fresh synthetic copies in isolated child processes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


class A08DocumentMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scripts.check_data_transfer import run_child
        cls.temporary = tempfile.TemporaryDirectory(prefix='bos_a08_document_cases_')
        cls.work = Path(cls.temporary.name)
        cls.source = cls.work / ('check_' + uuid4().hex + '.sqlite3')
        cls.media = cls.work / 'source-media'
        cls.media.mkdir(mode=0o700)
        run_child('seed', cls.source, cls.media, cls.work, expected=cls.work / 'expected.json')

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def _case(self, name):
        run = subprocess.run([sys.executable, '-B', '-m', 'operations.test_document_migration',
            '--case', name, '--source-db', str(self.source), '--source-media', str(self.media),
            '--work', str(self.work / name)], cwd=ROOT, capture_output=True,
            text=True, encoding='utf-8', timeout=120, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(run.returncode, 0, run.stdout + '\n' + run.stderr)
        result = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertTrue(result['passed'])
        print('BOS_A08_DOCUMENT_CASE ' + json.dumps(result, ensure_ascii=False), flush=True)

    def test_mixed_files_replay_restore_and_typed_transfer(self):
        self._case('mixed')

    def test_all_source_conflicts_are_reported_before_writing(self):
        self._case('all_conflicts')

    def test_late_sql_failure_rolls_back_rows_and_only_new_files(self):
        self._case('rollback')

    def test_forged_wrong_copy_attached_and_cross_plan_refused(self):
        self._case('ownership')

    def test_known_chat_checksum_deletion_refuses_old_plan(self):
        self._case('chat_checksum')

    def test_all_legacy_bytes_remain_charged_to_migration_quota(self):
        self._case('quota')

    def test_nullable_schema_upgrade_preserves_highwater_and_existing_rows(self):
        self._case('highwater')

    def test_missing_mutex_creation_is_the_only_allowed_new_row(self):
        self._case('missing_mutex')

    def test_bound_missing_corrupt_and_null_size_never_use_legacy_fallback(self):
        self._case('bound_conflicts')


def historical_highwater_case(source_db, source_media, work):
    """Create actual pre-A08/pre-B01 history; never erase a newer PO approval."""
    import hashlib
    from scripts import check_document_migration as runner
    from scripts.data_transfer import media_manifest
    from scripts.reconcile_data import source_files

    source_before = {'database': source_files(source_db), 'media': media_manifest(source_media)}
    # This subprocess creates a NEW historical fixture, rather than downgrading
    # the populated latest fixture and deleting its legitimate B01 snapshots.
    work.mkdir(mode=0o700)
    historical_db = work / ('check_' + uuid4().hex + '.sqlite3')
    with historical_db.open('xb'):
        pass
    historical_media = work / 'historical-media'
    historical_media.mkdir(mode=0o700)
    runner.configure(historical_db, historical_media)
    from django.db import connection, connections
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    # C01 tasks0005 and C03 finance0008 would pull ERP0005 and A08 back
    # into this historical source; pin both genuine earlier-schema boundaries.
    previous = {'operations': '0005_invoice_boundaries',
        'ai_assistant': '0008_chatmessage_archived_at_chatmessage_user_and_more',
        'erp': '0002_row_boundaries', 'tasks': '0004_task_branch',
        'finance': '0007_money_boundaries'}
    targets = [(app, previous.get(app, migration))
               for app, migration in executor.loader.graph.leaf_nodes()]
    executor.migrate(targets)
    historical = executor.loader.project_state(targets).apps
    DocumentBefore = historical.get_model('operations', 'Document')
    MessageBefore = historical.get_model('ai_assistant', 'ChatMessage')
    FileBefore = historical.get_model('ai_assistant', 'ChatFile')
    for pk in (7, 1001, 90001):
        content = ('Синтетичний історичний документ ' + str(pk)).encode()
        DocumentBefore.objects.create(pk=pk, code='A08-LEGACY-' + str(pk), revision='B',
            title='Історичний оригінал', filename=str(pk) + '.txt', content=content,
            text=content.decode(), sections=[{'page': 1, 'text': 'Точні первинні дані ЇЄҐ'}],
            checksum=hashlib.sha256(content).hexdigest(), status='approved', access_level='management')
    message = MessageBefore.objects.create(role='user', content='Історичне повідомлення')
    chat_bytes = b'Synthetic historical chat bytes\x00\xff'
    chat_path = historical_media / 'legacy-chat.bin'
    with chat_path.open('xb') as stream:
        stream.write(chat_bytes)
    FileBefore.objects.create(chat_message_id=message.pk, original_name='legacy-chat.bin',
        file='legacy-chat.bin', mime_type='application/octet-stream', size=len(chat_bytes),
        parsed_text='Історичний зміст без вигаданого checksum')
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA table_info(erp_purchase)')
        assert not {'quote_id', 'approval_snapshot'} & {row[1] for row in cursor.fetchall()}
        cursor.execute('PRAGMA table_info(operations_document)')
        assert not {'original_file', 'size'} & {row[1] for row in cursor.fetchall()}
        cursor.execute('PRAGMA table_info(ai_assistant_chatfile)')
        assert 'checksum' not in {row[1] for row in cursor.fetchall()}
        cursor.execute("UPDATE sqlite_sequence SET seq=400001 WHERE name='operations_document'")
        cursor.execute("UPDATE sqlite_sequence SET seq=500001 WHERE name='ai_assistant_chatfile'")
    connections.close_all()

    historical_before = {'database': source_files(historical_db), 'media': media_manifest(historical_media)}
    owned, db, media, _ = runner.new_owned_copy(historical_db, historical_media, work / 'upgrade')
    runner.configure(db, media)
    owned.assert_owned(connection, media)
    before, files_before = runner._rows(connection), media_manifest(media)
    executor = MigrationExecutor(connection)
    a08_targets = [(app, '0006_private_documents' if app == 'operations' else
                    '0009_private_documents' if app == 'ai_assistant' else migration)
                   for app, migration in targets]
    executor.migrate(a08_targets)
    # Preserve the original complete row, migration-recorder and high-water
    # oracle; apply only the A08 migrations that this scenario is testing.
    runner._preserve(before, runner._rows(connection), schema=True)
    assert media_manifest(media) == files_before
    owned.assert_owned(connection, media)
    DocumentAfter = executor.loader.project_state(a08_targets).apps.get_model('operations', 'Document')
    new = DocumentAfter.objects.create(code='A08-HIGHWATER', revision='A', title='Синтетичний наступний ID',
        content=b'', text='', checksum=hashlib.sha256(b'').hexdigest())
    assert new.pk == 400002
    connections.close_all()
    assert {'database': source_files(source_db), 'media': media_manifest(source_media)} == source_before
    assert {'database': source_files(historical_db), 'media': media_manifest(historical_media)} == historical_before
    return {'case': 'highwater', 'passed': True, 'input_unchanged': True,
        'details': {'document_high_water': 400001, 'chat_high_water': 500001,
            'actual_next_document_id': new.pk, 'historical_schema_created': True,
            'b01_source_fields_never_created_or_erased': True, 'historical_media_unchanged': True}}


def run_case(name, source_db, source_media, work):
    if name == 'highwater':
        return historical_highwater_case(source_db, source_media, work)
    from scripts import check_document_migration as runner
    from scripts.data_transfer import media_manifest
    from scripts.reconcile_data import source_files
    original = {'database': source_files(source_db), 'media': media_manifest(source_media)}
    owned, db, media, _ = runner.new_owned_copy(source_db, source_media, work)
    runner.configure(db, media)
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connection, connections, transaction
    from django.test import override_settings
    from operations.models import Document
    from ai_assistant.models import ChatFile
    from operations.document_migration import plan_migration, apply_plan
    from operations.private_storage import private_document_storage as storage, legacy_blob_usage, verified_document_bytes
    from erp.service import write_lock
    import hashlib

    owned.assert_owned(connection, media)
    call_command('migrate', verbosity=0, interactive=False)

    def rejected(function):
        try:
            function()
        except (ValueError, TypeError, RuntimeError):
            return
        raise AssertionError('Очікувана відмова не відбулася.')

    def bind_private(row):
        data = verified_document_bytes(row)
        with transaction.atomic(durable=True):
            owned.assert_owned(connection, media)
            write_lock()
            receipt = storage.save_verified(data, row.checksum, legacy_blob_bytes=legacy_blob_usage)
            Document.objects.filter(pk=row.pk).update(original_file=receipt.name, size=receipt.size)
            transaction.on_commit(lambda: storage.finalize(receipt))
        row.refresh_from_db()
        return row

    def state():
        return runner._rows(connection), media_manifest(media)

    details = {}
    if name == 'mixed':
        bound = bind_private(Document.objects.get(pk=7))
        original_key = bound.original_file.name
        text = 'Точний історичний текст українською.'
        owned.assert_owned(connection, media)
        fallback = Document.objects.create(code='A08-TEXT', revision='A', title='Синтетичний текст',
            content=b'', text=text, checksum=hashlib.sha256(text.encode()).hexdigest(), access_level='management')
        before = runner._rows(connection)
        expected_bytes = {row.pk: verified_document_bytes(row) for row in Document.objects.all()}
        plan = plan_migration(owned_copy=owned)
        assert plan['complete'] and {row['action'] for row in plan['documents']} == {'copy', 'keep'}
        assert any(row['id'] == fallback.pk and row['checksum_basis'] == 'exact_utf8_text' for row in plan['documents'])
        first = apply_plan(plan, owned_copy=owned)
        after = state()
        second = apply_plan(plan, owned_copy=owned)
        assert first['new_files'] == 3 and second['new_files'] == 0
        assert media_manifest(media) == after[1]
        assert Document.objects.get(pk=7).original_file.name == original_key
        assert expected_bytes == {row.pk: verified_document_bytes(row) for row in Document.objects.all()}
        runner._preserve(before, runner._rows(connection), mutex_steps=2)
        final_rows = runner._rows(connection)
        from fixtures.synthetic.transfer import _snapshot
        final_orm = _snapshot()
        connections.close_all()
        restored, restored_db, restored_media, _ = runner.new_owned_copy(db, media, work / 'restore')
        runner.configure(restored_db, restored_media)
        restored.assert_owned(connection, restored_media)
        assert runner._rows(connection) == final_rows
        assert expected_bytes == {row.pk: verified_document_bytes(row) for row in Document.objects.all()}
        assert plan_migration(owned_copy=restored)['complete']
        connections.close_all()
        from scripts import data_transfer as transport
        from scripts.schema_preflight import inspect_schema
        from scripts.check_data_transfer import sqlite_target
        bundle = work / 'typed-package'
        manifest = transport.export_snapshot(restored_db, restored_media, bundle, inspect_schema=inspect_schema)
        target = sqlite_target(work, bundle / 'media')
        try:
            transport.import_to_disposable(bundle, target, verify_actual_schema=lambda value: inspect_schema(value.name))
            target_db = Path(target.name)
        finally:
            target.connection.close()
        imported = transport.validate_snapshot(target_db, bundle / 'media', inspect_schema=inspect_schema)
        for key in ('tables', 'sequences', 'media', 'media_references', 'logical_schema_hash'):
            assert imported[key] == manifest[key], key
        runner.configure(target_db, bundle / 'media')
        # Typed transfer canonicalizes JSON spacing; compare independent ORM values.
        assert _snapshot() == final_orm
        assert runner._rows(connection)[1] == final_rows[1]
        assert expected_bytes == {row.pk: verified_document_bytes(row) for row in Document.objects.all()}
        details = {'tables': len(manifest['tables']), 'new_files': first['new_files'], 'replay_new_files': 0,
            'restored_exact_bytes': len(expected_bytes), 'typed_transfer_exact_bytes': len(expected_bytes)}
    elif name == 'all_conflicts':
        owned.assert_owned(connection, media)
        Document.objects.filter(pk=7).update(content=b'corrupt original')
        Document.objects.filter(pk=1001).update(checksum='not-a-sha')
        (media / ChatFile.objects.get().file.name).unlink()
        before = state()
        plan = plan_migration(owned_copy=owned)
        assert not plan['complete']
        assert {(row['model'], row['id']) for row in plan['findings']} == {
            ('operations.Document', 7), ('operations.Document', 1001), ('ai_assistant.ChatFile', 1)}
        rejected(lambda: apply_plan(plan, owned_copy=owned))
        assert state() == before
        connections.close_all()
        rejected(lambda: runner.rehearse(db, media, work / 'refused'))
        refusal = json.loads((work / 'refused' / 'report.json').read_text())
        assert not refusal['complete'] and refusal['input_unchanged']
        assert refusal['findings'] == plan['findings']
        details = {'findings': plan['findings'], 'rows_and_files_unchanged': True, 'refusal_report_saved': True}
    elif name == 'rollback':
        plan = plan_migration(owned_copy=owned)
        owned.assert_owned(connection, media)
        with connection.cursor() as cursor:
            cursor.execute("CREATE TRIGGER a08_late_failure BEFORE UPDATE OF original_file ON operations_document WHEN NEW.id=1001 BEGIN SELECT RAISE(ABORT, 'synthetic A08 late SQL failure'); END")
        before = state()
        from django.db import IntegrityError
        try:
            apply_plan(plan, owned_copy=owned)
        except IntegrityError:
            pass
        else:
            raise AssertionError('Синтетичний SQL trigger не зупинив другу прив’язку.')
        assert state() == before
        details = {'rows_and_files_unchanged_after_late_sql_failure': True}
    elif name == 'ownership':
        before = state()
        rejected(lambda: runner.new_owned_copy(db, media, media / 'nested-output'))
        rejected(lambda: runner.new_owned_copy(db, media, media))
        rejected(lambda: runner.new_owned_copy(db, media, media / '..' / media.name / 'nested-output'))
        assert not (media / 'nested-output').exists() and state() == before
        rejected(lambda: runner.OwnedDocumentCopy())
        forged = object.__new__(runner.OwnedDocumentCopy)
        rejected(lambda: plan_migration(owned_copy=forged))
        plan = plan_migration(owned_copy=owned)
        other, other_db, other_media, _ = runner.new_owned_copy(db, media, work / 'other')
        rejected(lambda: plan_migration(owned_copy=other))
        with override_settings(MEDIA_ROOT=str(other_media)):
            rejected(lambda: plan_migration(owned_copy=owned))
        with connection.cursor() as cursor:
            cursor.execute('ATTACH DATABASE %s AS forbidden', [str(other_db)])
        rejected(lambda: apply_plan(plan, owned_copy=owned))
        with connection.cursor() as cursor:
            cursor.execute('DETACH DATABASE forbidden')
        assert state() == before
        runner.configure(other_db, other_media)
        other_before = runner._rows(connection), media_manifest(other_media)
        rejected(lambda: apply_plan(plan, owned_copy=other))
        assert (runner._rows(connection), media_manifest(other_media)) == other_before
        details = {'constructor_forged_wrong_database_wrong_media_attached_cross_plan': 'refused'}
    elif name == 'chat_checksum':
        chat = ChatFile.objects.get()
        checksum = hashlib.sha256((media / chat.file.name).read_bytes()).hexdigest()
        owned.assert_owned(connection, media)
        ChatFile.objects.filter(pk=chat.pk).update(checksum=checksum)
        plan = plan_migration(owned_copy=owned)
        ChatFile.objects.filter(pk=chat.pk).update(checksum=None)
        before = state()
        rejected(lambda: apply_plan(plan, owned_copy=owned))
        assert state() == before
        details = {'declared_checksum_deletion_refused_without_repair': True}
    elif name == 'quota':
        plan = plan_migration(owned_copy=owned)
        usage = plan['usage']
        before = state()
        with override_settings(BOS_DOCUMENT_QUOTA_BYTES=usage['physical_bytes'] + usage['legacy_blob_bytes']):
            short = plan_migration(owned_copy=owned)
            assert not short['complete'] and any(row['reason'] == 'TOTAL_MIGRATION_QUOTA_EXCEEDED' for row in short['findings'])
            rejected(lambda: apply_plan(plan, owned_copy=owned))
        assert state() == before
        details = {'legacy_bytes_counted': usage['legacy_blob_bytes'], 'all_or_nothing': True}
    elif name == 'missing_mutex':
        from operations.models import Configuration
        owned.assert_owned(connection, media)
        Configuration.objects.filter(key='erp_write').delete()
        before = runner._rows(connection)
        connections.close_all()
        result = runner.rehearse(db, media, work / 'without-mutex')
        assert result['complete'] and result['input_unchanged']
        details = {'full_rehearsal_without_existing_mutex': True, 'new_files': result['first']['new_files']}
    elif name == 'bound_conflicts':
        first = bind_private(Document.objects.get(pk=7))
        second = bind_private(Document.objects.get(pk=1001))
        third = bind_private(Document.objects.get(pk=90001))
        owned.assert_owned(connection, media)
        (media / first.original_file.name).unlink()
        target = media / second.original_file.name
        target.write_bytes(b'X' * second.size)
        Document.objects.filter(pk=third.pk).update(size=None)
        before = state()
        plan = plan_migration(owned_copy=owned)
        assert not plan['complete']
        assert {row['id'] for row in plan['findings'] if row['model'] == 'operations.Document'} == {7, 1001, 90001}
        rejected(lambda: apply_plan(plan, owned_copy=owned))
        assert state() == before
        details = {'bound_missing_corrupt_null_size_ids': [7, 1001, 90001], 'legacy_fallback': False}
    else:
        raise ValueError('Невідомий синтетичний сценарій.')
    connections.close_all()
    assert {'database': source_files(source_db), 'media': media_manifest(source_media)} == original
    return {'case': name, 'passed': True, 'input_unchanged': True, 'details': details}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True)
    parser.add_argument('--source-db', required=True, type=Path)
    parser.add_argument('--source-media', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run_case(args.case, args.source_db, args.source_media, args.work), ensure_ascii=False))
