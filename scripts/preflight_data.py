"""Read-only admission of an explicitly supplied sealed SQLite snapshot.

Reports contain schema/record IDs and accounting totals. Keep real-client
reports private. Nothing is trimmed, rounded, linked, deleted or migrated.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def inspect_data(snapshot, media_root):
    from scripts.schema_preflight import inspect_schema
    from scripts.data_transfer import validate_snapshot, file_hash
    from scripts.reconcile_data import analyze
    path = Path(snapshot).resolve(strict=True)
    if ROOT == path or ROOT in path.parents:
        raise ValueError('Передайте окрему копію поза каталогом установки.')
    start = file_hash(path)
    report = {'date': datetime.now(timezone.utc).isoformat(), 'source_sha256': start,
              'can_migrate': False, 'source_unchanged': False, 'findings': [],
              'warnings': [], 'not_checked': ['target_database', 'production_cutover']}
    schema = inspect_schema(path)
    report['schema'] = schema
    if not schema.get('can_migrate') or not schema.get('complete'):
        report['findings'] = schema['findings']
        report['source_unchanged'] = start == file_hash(path)
        return report
    try:
        report['manifest'] = validate_snapshot(path, media_root, inspect_schema=inspect_schema)
    except ValueError as error:
        report['findings'].append({'code': 'TYPE_OR_FILE_CONFLICT', 'detail': str(error)})
        report['source_unchanged'] = start == file_hash(path)
        return report
    except OSError as error:
        report['findings'].append({'code': 'FILE_ACCESS_CONFLICT',
            'detail': type(error).__name__ + ': ' + str(error)})
        report['source_unchanged'] = start == file_hash(path)
        return report
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as con:
        con.execute('PRAGMA query_only=ON')
        accounting = analyze(con)
        report['accounting'] = accounting
        for finding in accounting['findings']:
            destination = 'warnings' if finding['classification'] in ('candidate', 'unlinked') else 'findings'
            report[destination].append(finding)
        if not accounting['complete']:
            report['findings'].append({'code': 'SOURCE_RECONCILIATION_INCOMPLETE',
                'detail': 'Покриття старого джерела неповне; схема й дані потребують окремої репетиції відомих міграцій на staging-копії.'})
        if 'finance_financialintent' in schema['tables']:
            for (key,) in con.execute('SELECT key FROM finance_financialintent WHERE transaction_id IS NULL AND salary_id IS NULL'):
                report['findings'].append({'code': 'FINANCIAL_INTENT_WITHOUT_SOURCE',
                    'table': 'finance_financialintent', 'pk': key})
    report['source_unchanged'] = start == file_hash(path)
    report['can_migrate'] = report['source_unchanged'] and not report['findings']
    if not report['source_unchanged']:
        report['findings'].append({'code': 'SNAPSHOT_CHANGED_DURING_PREFLIGHT'})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--media', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    output = args.output.absolute()
    if output.exists() or ROOT == output or ROOT in output.resolve().parents:
        parser.error('Звіт має бути новим файлом поза каталогом установки.')
    os.environ.update(DJANGO_SETTINGS_MODULE='verification_settings',
        BOS_VERIFY_DB='sqlite', BOS_TEST_DB_NAME=':memory:', BOS_TEST_MEDIA=str(args.media.absolute()))
    import django
    django.setup()
    report = inspect_data(args.snapshot, args.media)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        os.chmod(output, 0o600)
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'can_migrate': report['can_migrate'],
        'findings': len(report['findings']), 'warnings': len(report['warnings']),
        'source_unchanged': report['source_unchanged'], 'report': str(output)}, ensure_ascii=False))
    return 0 if report['can_migrate'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
