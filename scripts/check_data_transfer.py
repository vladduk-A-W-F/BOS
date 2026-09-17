"""Rehearse A07 on new synthetic databases; never accepts an installation DB."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def setup():
    os.environ['DJANGO_SETTINGS_MODULE'] = 'verification_settings'
    import django
    django.setup()


def run_child(stage, db, media, work, *, backend='sqlite', expected=None, minimum_id=None):
    work = work.resolve(strict=True)
    if backend == 'sqlite' and Path(db).resolve().parent != work:
        raise RuntimeError('База worker має належати поточному каталогу репетиції.')
    token = uuid4().hex
    marker = work / ('worker_' + uuid4().hex + '.json')
    issued = {'stage':stage, 'database':str(db), 'backend':backend, 'root':str(work),
        'media':str(media), 'expected':str(expected) if expected is not None else None,
        'minimum_id':minimum_id, 'token_sha256':hashlib.sha256(token.encode()).hexdigest()}
    with marker.open('x', encoding='utf-8') as handle:
        os.chmod(marker, 0o600)
        json.dump(issued, handle)
    env = dict(os.environ, BOS_VERIFY_DB=backend, BOS_TEST_DB_NAME=str(db),
               BOS_TEST_MEDIA=str(media), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1',
               BOS_REHEARSAL_MARKER=str(marker), BOS_REHEARSAL_TOKEN=token)
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker', stage]
    if expected is not None:
        command += ['--expected', str(expected)]
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                text=True, encoding='utf-8', timeout=120)
    finally:
        marker.unlink()
    number = len(list(work.glob('child-*.log'))) + 1
    (work / f'child-{number:02d}-{stage}.log').write_text(
        result.stdout + '\n--- STDERR ---\n' + result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(f'{stage}: exit {result.returncode}; child-{number:02d}-{stage}.log')
    if stage == 'migrate':
        return {'migrated': True}
    return json.loads(result.stdout.strip().splitlines()[-1])


def guard_worker(stage):
    backend = os.environ.get('BOS_VERIFY_DB', 'sqlite')
    raw = os.environ.get('BOS_TEST_DB_NAME', '')
    marker = Path(os.environ.get('BOS_REHEARSAL_MARKER', ''))
    token = os.environ.get('BOS_REHEARSAL_TOKEN', '')
    if not token or not marker.is_absolute() or marker.is_symlink() or marker != marker.resolve():
        raise RuntimeError('Worker не отримав дозвіл поточної репетиції.')
    issued = json.loads(marker.read_text(encoding='utf-8'))
    if (issued['token_sha256'] != hashlib.sha256(token.encode()).hexdigest()
            or issued['stage'] != stage or issued['database'] != raw or issued['backend'] != backend
            or issued['root'] != str(marker.parent) or issued['media'] != os.environ.get('BOS_TEST_MEDIA')):
        raise RuntimeError('Параметри worker не відповідають дозволу репетиції.')
    if backend == 'sqlite':
        db = Path(raw)
        if (not db.is_absolute() or ROOT == db or ROOT in db.parents or db.is_symlink()
                or db != db.resolve() or db.parent != marker.parent
                or not re.fullmatch(r'check_[a-f0-9]{32}\.sqlite3|bos_verify_[a-f0-9]{16}\.sqlite3', db.name)):
            raise RuntimeError('Потрібна нова ізольована база перевірки.')
        if stage in ('seed', 'migrate') and db.exists() and db.stat().st_size:
            raise RuntimeError('Вже заповнену базу не можна використати для початкової міграції.')
    elif backend == 'postgres':
        # The native inspector/factory are prepared, but no provisioner with
        # successful CREATE + OID ownership is integrated into this runner yet.
        # A caller-supplied name/env flag must not authorize migration or proof
        # writes on an existing server database.
        raise RuntimeError('НЕ ЗАПУЩЕНО: PostgreSQL worker потребує підтвердження створення власної тестової БД.')
    else:
        raise RuntimeError('Непідтримуваний профіль бази перевірки.')
    if stage == 'proof' and (type(issued['minimum_id']) is not int or issued['minimum_id'] < 0):
        raise RuntimeError('Не зафіксовано контрольну верхню межу ID.')
    return issued


def worker(args):
    issued = guard_worker(args.worker)
    if issued['expected'] != (str(args.expected) if args.expected is not None else None):
        raise RuntimeError('Файл еталона не відповідає дозволу worker.')
    setup()
    from django.core.management import call_command
    from django.db import connections, connection, transaction
    from fixtures.synthetic.transfer import populate, verify_facts
    if args.worker in ('seed', 'migrate'):
        call_command('migrate', verbosity=0, interactive=False)
    if args.worker == 'seed':
        result = populate()
        Path(args.expected).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'populated': True, 'backend': connection.vendor}))
    elif args.worker == 'facts':
        expected = json.loads(Path(args.expected).read_text(encoding='utf-8'))
        result = verify_facts(expected)
        print(json.dumps({'facts_verified': True, 'backend': connection.vendor, 'facts': result}, ensure_ascii=False, default=str))
    elif args.worker == 'proof':
        from fixtures.synthetic.transfer import verify_replays
        os.environ['BOS_A07_PROOF_COPY'] = '1'
        replay = verify_replays(json.loads(Path(args.expected).read_text(encoding='utf-8')))
        from operations.models import Document
        before = Document.objects.order_by('-id').first().id
        high_water = max(before, issued['minimum_id'])
        inserted = []
        # This DB is a separate disposable proof copy. No verification row is
        # added to the imported target or immutable source snapshot.
        for revision in ('PROOF-1', 'PROOF-2'):
            row = Document.objects.create(code='A07-SEQUENCE-PROOF', revision=revision,
                title='Синтетична перевірка нового номера', content=b'proof',
                text='proof', sections=[], checksum=__import__('hashlib').sha256(b'proof').hexdigest())
            inserted.append(row.pk)
        assert high_water < inserted[0] < inserted[1], (high_water, inserted)
        assert Document.objects.filter(code='A07-SEQUENCE-PROOF').order_by('-id').first().id == inserted[1]
        print(json.dumps({'proof': True, 'backend': connection.vendor, 'old_max': before,
            'source_high_water':issued['minimum_id'], 'next_ids': inserted, 'replay':replay}, default=str))
    connections.close_all()


def reconcile(path):
    from scripts.reconcile_data import analyze, connect_readonly
    from scripts.data_transfer import file_hash
    before = file_hash(path)
    con = connect_readonly(path)
    try:
        result = analyze(con)
    finally:
        con.close()
    allowed = {'candidate', 'unlinked'}
    blockers = [row for row in result['findings'] if row['classification'] not in allowed]
    if not result['complete'] or result['stop_required'] or blockers:
        raise RuntimeError('Неповна звірка або підтверджений конфлікт; перенесення відхилено.')
    if file_hash(path) != before:
        raise RuntimeError('Копія змінилася під час звірки.')
    result['source_sha256'] = before
    return result


def sqlite_target(work, media):
    from scripts import data_transfer as transport
    from scripts.schema_preflight import inspect_schema
    def bootstrap(con):
        name = con.execute('PRAGMA database_list').fetchone()[2]
        run_child('migrate', name, media, work)
    return transport.new_disposable_sqlite(work, bootstrap=bootstrap, inspect_schema=inspect_schema)


def rehearse(work, backend):
    from scripts import data_transfer as transport
    from scripts.schema_preflight import inspect_schema
    from scripts.reconcile_data import make_snapshot
    from scripts.verify import source_digest
    start_sha = source_digest()
    source = work / ('check_' + uuid4().hex + '.sqlite3')
    media = work / 'source-media'
    media.mkdir()
    expected_file = work / 'expected.json'
    run_child('seed', source, media, work, expected=expected_file)
    original = transport.file_hash(source)
    snapshot = work / ('check_' + uuid4().hex + '.sqlite3')
    capture = make_snapshot(source, snapshot)
    before_facts = run_child('facts', snapshot, media, work, expected=expected_file)
    from scripts.preflight_data import inspect_data
    preflight = inspect_data(snapshot, media)
    source_schema = preflight['schema']
    (work / 'preflight.json').write_text(json.dumps(preflight, ensure_ascii=False, indent=2), encoding='utf-8')
    if not preflight['can_migrate'] or not source_schema['complete'] or source_schema['profile'] != 'latest':
        raise RuntimeError('Повна актуальна схема синтетичного джерела не підтверджена.')
    accounting = reconcile(snapshot)
    report_recon = work / 'reconciliation.json'
    report_recon.write_text(json.dumps(accounting, ensure_ascii=False, indent=2), encoding='utf-8')
    bundle = work / 'typed-bundle'
    manifest = transport.export_snapshot(snapshot, media, bundle, inspect_schema=inspect_schema)
    assert manifest['source_sha256'] == capture['snapshot_sha256']
    if backend != 'sqlite':
        return rehearse_postgres(work, snapshot, media, expected_file, bundle, manifest,
                                 start_sha, original, source, before_facts, accounting)
    target = sqlite_target(work, media)
    try:
        imported = transport.import_to_disposable(bundle, target,
            verify_actual_schema=lambda row: inspect_schema(row.name))
        target_path = Path(target.name)
    finally:
        target.connection.close()
    target_before = transport.file_hash(target_path)
    target_facts = run_child('facts', target_path, bundle / 'media', work, expected=expected_file)
    assert before_facts['facts'] == target_facts['facts']
    restored = transport.validate_snapshot(target_path, bundle / 'media', inspect_schema=inspect_schema)
    # The DB file itself can have a different physical layout; all logical
    # records, sums, foreign links, sequence high-water and bytes must match.
    for key in ('tables', 'sequences', 'media', 'media_references', 'logical_schema_hash'):
        assert restored[key] == manifest[key], key
    target_accounting = reconcile(target_path)
    assert accounting['totals'] == target_accounting['totals']
    proof = work / ('check_' + uuid4().hex + '.sqlite3')
    make_snapshot(target_path, proof)
    proof_media = work / 'proof-media'
    shutil.copytree(bundle / 'media', proof_media)
    proof_result = run_child('proof', proof, proof_media, work,
        minimum_id=manifest['sequences']['operations_document']['high_water'], expected=expected_file)
    # Rollback rehearsal returns to the original sealed source and matching
    # media, never merges later writes from another installation.
    rollback_facts = run_child('facts', snapshot, media, work, expected=expected_file)
    assert rollback_facts == before_facts
    assert transport.file_hash(source) == original
    assert transport.file_hash(snapshot) == manifest['source_sha256']
    assert transport.file_hash(target_path) == target_before
    assert source_digest() == start_sha
    return {'complete': True, 'scope': 'A07 synthetic full-model SQLite transfer rehearsal',
        'backend': 'sqlite', 'source_sha256': start_sha,
        'source_database_sha256': manifest['source_sha256'], 'source_unchanged': True,
        'table_count': len(manifest['tables']), 'tables': manifest['tables'],
        'sequences_preserved': True, 'files_preserved': True,
        'business_before': before_facts, 'business_after': target_facts,
        'accounting_totals': accounting['totals'], 'accounting_warnings': accounting['findings'],
        'sequence_proof': proof_result, 'rollback_source_verified': True,
        'target_unchanged_by_proof': True,
        'not_checked': ['real_customer_data', 'postgresql', 'production_cutover', 'A09_A10_installation_upgrade']}


def rehearse_postgres(work, snapshot, media, expected_file, bundle, manifest,
                       start_sha, original, source, before_facts, accounting):
    # Explicit failure until the isolated native-schema inspector and genuine
    # PostgreSQL provisioner are integrated and exercised in its real runtime.
    from scripts.verify import EnvironmentUnavailable
    required = ('BOS_PGHOST', 'BOS_PGUSER', 'BOS_PGPASSWORD')
    if os.environ.get('BOS_PG_DISPOSABLE') != '1' or not all(os.environ.get(k) for k in required):
        raise EnvironmentUnavailable('НЕ ЗАПУЩЕНО: немає ізольованого PostgreSQL для A07.')
    raise RuntimeError('PostgreSQL A07: native schema admission ще не інтегровано; успіх не підміняється SQLite.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--backend', choices=('sqlite', 'postgres'), default=os.environ.get('BOS_VERIFY_DB', 'sqlite'))
    parser.add_argument('--worker', choices=('seed', 'migrate', 'facts', 'proof'), help=argparse.SUPPRESS)
    parser.add_argument('--expected', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        worker(args)
        return 0
    if args.output_dir is None:
        parser.error('--output-dir потрібний')
    work = args.output_dir.resolve()
    if work.exists() or ROOT == work or ROOT in work.resolve().parents:
        parser.error('Потрібен новий каталог поза checkout.')
    work.mkdir(parents=True, mode=0o700)
    os.environ.update(BOS_VERIFY_DB='sqlite', BOS_TEST_DB_NAME=':memory:',
                      BOS_TEST_MEDIA=str(work / 'unused-parent-media'))
    setup()
    report = {'complete': False, 'backend': args.backend}
    try:
        report = rehearse(work, args.backend)
        status = 0
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        status = 1
    (work / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
