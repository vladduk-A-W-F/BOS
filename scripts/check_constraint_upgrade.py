"""Actual synthetic migration refusal/high-water probe; never working files."""
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        raise RuntimeError('One explicit synthetic migration case is required')
    case = arguments[0]
    if case not in ('finance', 'operations', 'erp', 'sequence', 'sequence_empty', 'sequence_current', 'sequence_null'):
        raise RuntimeError('Unknown synthetic migration case')
    db = Path(os.environ['BOS_TEST_DB_NAME']).resolve()
    if (not Path(os.environ['BOS_TEST_DB_NAME']).is_absolute() or db.exists()
            or not re.fullmatch(r'check_[a-f0-9]{32}\.sqlite3', db.name)
            or ROOT == db.parent or ROOT in db.parents):
        raise RuntimeError('A fresh disposable SQLite database outside the project is required')
    if os.environ.get('BOS_VERIFY_DB', 'sqlite') != 'sqlite':
        raise RuntimeError('This rebuild probe is explicitly SQLite-only')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'verification_settings'

    import django
    django.setup()
    from django.db import connection, IntegrityError
    from django.db.migrations.executor import MigrationExecutor

    if connection.vendor != 'sqlite':
        raise RuntimeError('This specific upgrade probe requires actual SQLite')
    old = {'finance': '0006_financialintent',
           'operations': '0004_alter_document_options_document_access_level',
           'erp': '0001_initial'}
    new = {'finance': '0007_money_boundaries', 'operations': '0005_invoice_boundaries', 'erp': '0002_row_boundaries'}
    executor = MigrationExecutor(connection)
    # Pin A06 baselines; future unrelated application migrations must not alter
    # the historical upgrade fixture. Django includes their actual dependencies.
    targets = list(old.items())
    executor.migrate(targets)
    state = executor.loader.project_state(targets).apps
    partner = state.get_model('finance', 'Counterparty').objects.create(name='Синтетичний probe A07')

    if case == 'finance':
        model = state.get_model('finance', 'Transaction')
        row = model.objects.create(direction='out', amount='-0.01', currency='EUR',
            date='2026-09-11', description='Synthetic invalid source', category='other')
    elif case == 'erp':
        item = state.get_model('erp', 'Item').objects.create(code='A07-PROBE-ITEM', name='Synthetic')
        model = state.get_model('erp', 'Purchase')
        row = model.objects.create(code='A07-PROBE-PO', item=item, supplier=partner,
            quantity='0', received='0', price='1', extras='0', currency='EUR',
            due_date='2026-09-30', original_due='2026-09-30', revision='A')
    else:
        model = state.get_model('operations', 'Invoice')
        if case.startswith('sequence'):
            row = model.objects.create(id=7, code='A07-KEEP', customer=partner,
                amount='100', paid='20', currency='EUR', due_date='2026-09-30')
            high = model.objects.create(id=90001, code='A07-OLD-HIGH', customer=partner,
                amount='1', paid='0', currency='EUR', due_date='2026-09-30')
            high.delete()
            if case == 'sequence_empty':
                row.delete()
            elif case == 'sequence_null':
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE sqlite_sequence SET seq = NULL WHERE name = %s', [model._meta.db_table])
            elif case == 'sequence_current':
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE sqlite_sequence SET seq = 5 WHERE name = %s', [model._meta.db_table])
        else:
            row = model.objects.create(code='A07-PROBE-INV', customer=partner,
                amount='100', paid='100.01', currency='EUR', due_date='2026-09-30')

    table = model._meta.db_table
    def snapshot():
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM ' + connection.ops.quote_name(table) + ' ORDER BY id')
            rows = cursor.fetchall()
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=%s", [table])
            ddl = cursor.fetchone()[0]
            cursor.execute('SELECT seq FROM sqlite_sequence WHERE name=%s', [table])
            seq = cursor.fetchone()[0]
        return {'rows': rows, 'ddl': ddl, 'sequence': seq}

    before = snapshot()
    app = 'operations' if case.startswith('sequence') else case
    denied = None
    try:
        MigrationExecutor(connection).migrate([(app, new[app])])
    except (IntegrityError, RuntimeError) as exc:
        denied = str(exc)
    after = snapshot()
    applied = (app, new[app]) in MigrationExecutor(connection).loader.applied_migrations
    with connection.cursor() as cursor:
        cursor.execute('SELECT sqlite_version()')
        sqlite_version = cursor.fetchone()[0]
    result = {'case': case, 'backend': connection.vendor, 'database_version': sqlite_version, 'denied': denied, 'applied': applied,
              'rows_unchanged': before['rows'] == after['rows'],
              'ddl_unchanged': before['ddl'] == after['ddl'],
              'sequence_before': before['sequence'], 'sequence_after': after['sequence']}
    if case.startswith('sequence') and case != 'sequence_null':
        result['passed'] = denied is None and applied and result['rows_unchanged'] and after['sequence'] >= before['sequence']
        if result['passed']:
            MigrationExecutor(connection).migrate([(app, old[app])])
            reverse = snapshot()
            result['reverse_rows_unchanged'] = before['rows'] == reverse['rows']
            result['reverse_sequence'] = reverse['sequence']
            first = model.objects.create(code='A07-NEXT-1', customer=partner,
                amount='1', paid='0', currency='EUR', due_date='2026-09-30')
            second = model.objects.create(code='A07-NEXT-2', customer=partner,
                amount='1', paid='0', currency='EUR', due_date='2026-09-30')
            result['next_ids'] = [first.pk, second.pk]
            result['passed'] = (result['passed'] and result['reverse_rows_unchanged']
                and reverse['sequence'] >= max(before['sequence'], after['sequence'])
                and first.pk > reverse['sequence'] and second.pk > first.pk)
    else:
        result['passed'] = bool(denied) and not applied and before == after
    print(json.dumps(result, ensure_ascii=False))
    connection.close()
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
