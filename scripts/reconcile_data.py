"""Read-only reconciliation of a SQLite snapshot; never repairs business data.

Public API: analyze(sqlite3.Connection) -> dict;
make_snapshot(source: Path, dest: Path, timeout=30.0) -> dict.
The complete flag describes coverage, not acceptance; use reconciled and
stop_required separately. Reports contain structural IDs and financial facts,
never employee names, contacts, descriptions, document text or session values.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(source):
    result = {}
    for suffix in ('', '-wal', '-shm'):
        path = Path(str(source) + suffix)
        if path.is_file():
            result['main' if not suffix else suffix[1:]] = {
                'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
    return result


def connect_readonly(path):
    connection = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro',
                                 uri=True, timeout=5, isolation_level=None)
    connection.execute('PRAGMA query_only=ON')
    return connection


def make_snapshot(source, dest, timeout=30.0):
    source = Path(source).resolve(strict=True)
    dest = Path(dest).absolute()
    if source == dest.resolve():
        raise ValueError('Джерело і копія повинні мати різні шляхи.')
    if not source.is_file() or timeout <= 0:
        raise ValueError('Потрібний файл SQLite та додатний timeout.')
    dest.parent.mkdir(parents=True, exist_ok=True)
    before = source_files(source)
    started = time.monotonic()
    # Exclusive creation: an existing snapshot or symlink is never replaced.
    with dest.open('xb'):
        pass
    reader = writer = None
    try:
        reader = connect_readonly(source)
        writer = sqlite3.connect(str(dest), timeout=5, isolation_level=None)
        def progress(status, remaining, total):
            if time.monotonic() - started > timeout:
                raise TimeoutError('Створення узгодженої копії перевищило timeout.')
        reader.backup(writer, pages=256, progress=progress, sleep=0.05)
    finally:
        if writer is not None:
            writer.close()
        if reader is not None:
            reader.close()
    after = source_files(source)
    return {
        'method': 'SQLite backup API; source mode=ro; destination exclusively created',
        'source': str(source), 'snapshot': str(dest.resolve()),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'source_files_before': before, 'source_files_after': after,
        'source_sha256_before': before['main']['sha256'],
        'source_sha256_after': after['main']['sha256'],
        'snapshot_sha256': sha256_file(dest),
        'source_main_unchanged': before['main'] == after['main'],
        # SHM may change because another application is active; not a ledger discrepancy.
        'source_files_unchanged': before == after,
        'note': 'Backup API створює узгоджену копію, включно з WAL. Різні SHA копії та джерела самі по собі не є фінансовою помилкою.'}


def plain(value):
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def quote_identifier(name):
    return '"' + name.replace('"', '""') + '"'


class Analyzer:
    def __init__(self, connection):
        self.connection = connection
        self.findings = []
        self.checks = {}
        self.totals = {}
        self.incomplete = False
        self.schema = {}
        connection.execute('PRAGMA query_only=ON')
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for (name,) in tables:
            if name in {'finance_salary', 'finance_transaction', 'erp_lot', 'erp_movement',
                        'erp_reservation', 'operations_invoice', 'erp_purchase', 'erp_production'}:
                self.schema[name] = [row[1] for row in connection.execute(
                    'PRAGMA table_info(' + quote_identifier(name) + ')')]
        self.table_count = len(tables)

    def add(self, code, classification, facts, proposal):
        self.findings.append({'id': 'REC-' + str(len(self.findings) + 1).zfill(4),
            'code': code, 'classification': classification, 'facts': plain(facts),
            'proposal': proposal})

    def require(self, check, tables):
        missing = {}
        for table, fields in tables.items():
            if table not in self.schema:
                missing[table] = {'table_missing': True}
            elif set(fields) - set(self.schema[table]):
                missing[table] = {'columns_missing': sorted(set(fields) - set(self.schema[table]))}
        if missing:
            self.incomplete = True
            self.checks[check] = {'status': 'not_checked', 'missing': missing}
            self.add('SCHEMA_MISSING', 'not_checked', {'check': check, 'missing': missing},
                'Визначити відповідне джерело даних або версію схеми. Не створювати порожні таблиці для успішної звірки.')
            return False
        self.checks[check] = {'status': 'checked'}
        return True

    def rows(self, table, fields, decimals=()):
        expressions = [('CAST(' + quote_identifier(field) + ' AS TEXT) AS ' + quote_identifier(field))
                       if field in decimals else quote_identifier(field) for field in fields]
        cursor = self.connection.execute('SELECT ' + ', '.join(expressions) +
            ' FROM ' + quote_identifier(table) + ' ORDER BY "id"')
        return [dict(zip(fields, row)) for row in cursor.fetchall()]

    def number(self, row, field, table):
        try:
            value = Decimal(str(row[field]))
            if not value.is_finite():
                raise InvalidOperation
            return value
        except (InvalidOperation, ValueError, TypeError):
            self.incomplete = True
            self.add('INVALID_NUMBER', 'not_checked',
                {'table': table, 'record_id': row.get('id'), 'field': field},
                'Перевірити формат числового поля в першоджерелі; значення не перезаписувати.')
            return None

    def currency(self, row, table):
        value = row.get('currency')
        if not isinstance(value, str) or re.fullmatch(r'[A-Z]{3}', value) is None:
            self.incomplete = True
            self.add('INVALID_CURRENCY', 'not_checked', {'table': table, 'record_id': row.get('id')},
                'Підтвердити валюту в першоджерелі; автоматично не підставляти EUR, USD чи UAH.')
            return None
        return value

    def integrity(self):
        result = self.connection.execute('PRAGMA integrity_check').fetchall()
        ok = len(result) == 1 and tuple(result[0]) == ('ok',)
        self.checks['sqlite_integrity'] = {'status': 'checked', 'ok': ok,
                                           'diagnostic_count': 0 if ok else len(result)}
        if not ok:
            self.incomplete = True
            self.add('SQLITE_INTEGRITY', 'discrepancy', {'diagnostic_count': len(result)},
                'Зберегти джерело і копію; технічно дослідити цілісність без автоматичного ремонту.')
        foreign = self.connection.execute('PRAGMA foreign_key_check').fetchall()
        self.checks['foreign_keys'] = {'status': 'checked', 'violations': len(foreign)}
        for table, rowid, parent, index in foreign:
            # Structural IDs only; no joined records or text fields are read.
            self.add('FOREIGN_KEY_MISSING', 'discrepancy',
                {'table': table, 'record_id': rowid, 'parent_table': parent, 'foreign_key_index': index},
                'Підтвердити джерело зв’язку. Не створювати чи видаляти історичні записи автоматично.')

    def stock(self):
        required = {'erp_lot': ('id', 'item_id', 'quantity', 'unit_cost', 'currency'),
                    'erp_movement': ('id', 'lot_id', 'quantity')}
        if not self.require('stock_movements', required):
            # Also report missing reservation coverage independently.
            if self.require('reservations', {'erp_lot': ('id', 'quantity'),
                    'erp_reservation': ('id', 'lot_id', 'quantity', 'line_id', 'production_id')}):
                self.checks['reservations'] = {'status': 'not_checked',
                    'reason': 'Недоступна повна структура партій/рухів; резерви не аналізувалися.'}
                self.add('RESERVATION_ANALYSIS_INCOMPLETE', 'not_checked', {'check': 'reservations'},
                    'Надати повну схему партій і рухів для звірки резервів; не вважати лише наявність таблиці успішною перевіркою.')
            return
        lot_rows = self.rows('erp_lot', required['erp_lot'], ('quantity', 'unit_cost'))
        move_rows = self.rows('erp_movement', required['erp_movement'], ('quantity',))
        lots = {}; movements = defaultdict(Decimal); move_counts = Counter()
        values = defaultdict(Decimal); by_item = defaultdict(lambda: {'stock': Decimal(0), 'movements': Decimal(0)})
        for row in lot_rows:
            lots[row['id']] = {**row, 'quantity': self.number(row, 'quantity', 'erp_lot'),
                'unit_cost': self.number(row, 'unit_cost', 'erp_lot'),
                'currency': self.currency(row, 'erp_lot')}
        for row in move_rows:
            quantity = self.number(row, 'quantity', 'erp_movement')
            if quantity is None:
                continue
            if row['lot_id'] not in lots:
                self.add('MOVEMENT_WITHOUT_LOT', 'discrepancy',
                    {'movement_id': row['id'], 'lot_id': row['lot_id'], 'quantity': quantity},
                    'Встановити джерело партії; не видаляти рух і не вигадувати початковий залишок.')
                continue
            movements[row['lot_id']] += quantity; move_counts[row['lot_id']] += 1
        for key, row in lots.items():
            quantity = row['quantity']; total = movements[key]
            if quantity is None:
                continue
            by_item[row['item_id']]['stock'] += quantity
            by_item[row['item_id']]['movements'] += total
            if row['unit_cost'] is not None and row['currency']:
                values[row['currency']] += quantity * row['unit_cost']
            if quantity < 0:
                self.add('NEGATIVE_STOCK', 'discrepancy', {'lot_id': key, 'quantity': quantity},
                    'Перевірити первинні рухи та початковий залишок; не виправляти кількість напряму.')
            if quantity != total:
                facts = {'lot_id': key, 'item_id': row['item_id'], 'quantity': quantity,
                         'movement_total': total, 'difference': quantity - total,
                         'movement_count': move_counts[key]}
                classification = 'discrepancy'
                if row['unit_cost'] is not None and row['currency']:
                    money_gap = (quantity - total) * row['unit_cost']
                    facts.update(currency=row['currency'], recorded_unit_cost=row['unit_cost'],
                                 recorded_cost_basis_difference=money_gap)
                    if money_gap:
                        classification = 'confirmed_monetary'
                self.add('LOT_MOVEMENT_MISMATCH', classification, facts,
                    'Погодити звірку партії за первинними документами. Не створювати коригувальний рух автоматично; наведена вартість є обліковою, не ринковою.')
        self.totals['stock'] = {'lot_count': len(lot_rows), 'movement_count': len(move_rows),
            'recorded_cost_basis_by_currency': values,
            'quantity_by_item': dict(by_item)}
        self.checks['stock_movements'].update(lots=len(lot_rows), movements=len(move_rows))
        if self.require('reservations', {'erp_reservation': ('id', 'lot_id', 'quantity', 'line_id', 'production_id')}):
            rows = self.rows('erp_reservation', ('id', 'lot_id', 'quantity', 'line_id', 'production_id'), ('quantity',))
            totals = defaultdict(Decimal)
            for row in rows:
                quantity = self.number(row, 'quantity', 'erp_reservation')
                if quantity is not None:
                    totals[row['lot_id']] += quantity
                    if quantity < 0:
                        self.add('NEGATIVE_RESERVATION', 'discrepancy',
                            {'reservation_id': row['id'], 'quantity': quantity}, 'Звірити джерело резерву без автоматичної зміни.')
                if row['lot_id'] not in lots:
                    self.add('RESERVATION_WITHOUT_LOT', 'discrepancy',
                        {'reservation_id': row['id'], 'lot_id': row['lot_id']}, 'Звірити джерело партії.')
                if (row['line_id'] is None) == (row['production_id'] is None):
                    self.add('RESERVATION_TARGET', 'discrepancy', {'reservation_id': row['id']},
                        'Підтвердити рівно одне призначення резерву: замовлення або виробництво.')
            for lot_id, reserved in totals.items():
                if lot_id in lots and lots[lot_id]['quantity'] is not None and reserved > lots[lot_id]['quantity']:
                    self.add('RESERVE_EXCEEDS_STOCK', 'discrepancy',
                        {'lot_id': lot_id, 'reserved': reserved, 'stock': lots[lot_id]['quantity']},
                        'Звірити активні резерви і фактичний залишок; автоматично не знімати резерви.')
            self.checks['reservations']['rows'] = len(rows)

    def salaries(self):
        salary_fields = ('id', 'status', 'transaction_id', 'amount', 'currency', 'payment_date')
        tx_fields = ('id', 'direction', 'category', 'amount', 'currency', 'date')
        if not self.require('salary_expenses', {'finance_salary': salary_fields, 'finance_transaction': tx_fields}):
            return
        salaries = self.rows('finance_salary', salary_fields, ('amount',))
        transactions = self.rows('finance_transaction', tx_fields, ('amount',))
        txs = {}; linked = defaultdict(list); salary_totals = defaultdict(Decimal); tx_totals = defaultdict(Decimal)
        signatures = defaultdict(list)
        for row in transactions:
            tx = {**row, 'amount': self.number(row, 'amount', 'finance_transaction'),
                  'currency': self.currency(row, 'finance_transaction')}
            txs[row['id']] = tx
            if tx['amount'] is not None and tx['currency']:
                tx_totals[(tx['currency'], tx['direction'])] += tx['amount']
                if tx['direction'] == 'out' and tx['category'] == 'salary':
                    signatures[(tx['currency'], tx['amount'], tx['date'])].append(tx['id'])
        for row in salaries:
            amount = self.number(row, 'amount', 'finance_salary'); currency = self.currency(row, 'finance_salary')
            if amount is not None and currency:
                salary_totals[(currency, row['status'])] += amount
            if row['transaction_id'] is not None:
                linked[row['transaction_id']].append(row['id'])
            tx = txs.get(row['transaction_id'])
            facts = {'salary_id': row['id'], 'transaction_id': row['transaction_id'],
                     'salary_amount': amount, 'salary_currency': currency, 'status': row['status']}
            if row['status'] == 'paid':
                if tx is None:
                    self.add('PAID_WITHOUT_EXPENSE', 'confirmed_monetary', facts,
                        'Підтвердити первинне проведення та джерело виплати. Не створювати повторну витрату й не змінювати paid автоматично.')
                    continue
                different = []
                if tx['direction'] != 'out': different.append('direction')
                if tx['category'] != 'salary': different.append('category')
                if amount is not None and tx['amount'] is not None and amount != tx['amount']: different.append('amount')
                if currency is not None and tx['currency'] is not None and currency != tx['currency']: different.append('currency')
                if row['payment_date'] != tx['date']: different.append('date')
                if different:
                    facts.update(expense_amount=tx['amount'], expense_currency=tx['currency'],
                        salary_date=row['payment_date'], expense_date=tx['date'],
                        expense_direction=tx['direction'], expense_category=tx['category'], mismatches=different)
                    self.add('SALARY_EXPENSE_MISMATCH', 'confirmed_monetary', facts,
                        'Погодити звірку нарахування і витрати за первинними документами. Це розбіжність облікового зв’язку, не доказ двох банківських переказів.')
            elif row['transaction_id'] is not None:
                self.add('UNPAID_WITH_EXPENSE_LINK', 'confirmed_monetary', facts,
                    'Перевірити стан проведення і прив’язану операцію; не змінювати історичний статус автоматично.')
        for tx_id, salary_ids in linked.items():
            if len(salary_ids) > 1:
                self.add('EXPENSE_MULTIPLE_SALARY_SOURCES', 'confirmed_monetary',
                    {'transaction_id': tx_id, 'salary_ids': salary_ids},
                    'Підтвердити джерела спільної витрати. Не називати це двома банківськими переказами без первинних доказів.')
        unlinked_ids = set()
        for tx in txs.values():
            if tx['category'] == 'salary' and tx['direction'] == 'out' and tx['id'] not in linked:
                unlinked_ids.add(tx['id'])
                self.add('SALARY_EXPENSE_WITHOUT_SOURCE', 'unlinked',
                    {'transaction_id': tx['id'], 'amount': tx['amount'], 'currency': tx['currency'], 'date': tx['date']},
                    'Знайти документоване джерело. Відсутній зв’язок сам по собі не доводить дубль або переплату.')
        for (currency, amount, day), ids in signatures.items():
            if len(ids) > 1:
                self.add('SIMILAR_SALARY_EXPENSES', 'candidate',
                    {'transaction_ids': ids, 'currency': currency, 'amount_each': amount, 'date': day,
                     'unlinked_ids': [key for key in ids if key in unlinked_ids], 'confirmed_duplicate': False},
                    'Однакові сума, валюта й дата не доводять дубль. Потрібний спільний ідентифікатор джерела або рішення людини; нічого не видаляти.')
        self.totals['finance'] = {
            'salary_rows': len(salaries), 'transaction_rows': len(transactions),
            'salary_amounts': [{'currency': currency, 'status': status, 'amount': total}
                for (currency, status), total in sorted(salary_totals.items())],
            'transaction_amounts': [{'currency': currency, 'direction': direction, 'amount': total}
                for (currency, direction), total in sorted(tx_totals.items())]}
        self.checks['salary_expenses'].update(salaries=len(salaries), transactions=len(transactions))

    def bounds(self):
        for check, table, limit, actual, monetary in (
                ('invoice_bounds', 'operations_invoice', 'amount', 'paid', True),
                ('purchase_bounds', 'erp_purchase', 'quantity', 'received', False),
                ('production_bounds', 'erp_production', 'quantity', 'produced', False)):
            fields = ('id', limit, actual, 'currency') if monetary else ('id', limit, actual)
            if not self.require(check, {table: fields}):
                continue
            rows = self.rows(table, fields, (limit, actual))
            for row in rows:
                ceiling = self.number(row, limit, table); observed = self.number(row, actual, table)
                if ceiling is None or observed is None:
                    continue
                if ceiling < 0 or observed < 0 or observed > ceiling:
                    facts = {'table': table, 'record_id': row['id'], limit: ceiling, actual: observed}
                    if monetary:
                        facts['currency'] = self.currency(row, table)
                    self.add('BOUND_VIOLATION', 'confirmed_monetary' if monetary else 'discrepancy', facts,
                        'Звірити значення з первинними документами; не змінювати суми, кількості або статуси автоматично.')
            self.checks[check]['rows'] = len(rows)

    def run(self):
        self.integrity(); self.stock(); self.salaries(); self.bounds()
        complete = not self.incomplete and all(row['status'] == 'checked' for row in self.checks.values())
        stop = any(row['classification'] == 'confirmed_monetary' for row in self.findings)
        return plain({'schema_version': 1, 'date': datetime.now(timezone.utc).isoformat(),
            'complete': complete, 'complete_means': 'Усі заявлені перевірки виконано; це не ознака узгодженості даних.',
            'reconciled': complete and not self.findings, 'stop_required': stop,
            'stop_basis': 'Стоп 8.1 лише за підтвердженою розбіжністю облікових грошей. Кандидати та несв’язані витрати не є підтвердженими дублями.',
            'findings': self.findings, 'checks': self.checks, 'totals': self.totals,
            'schema': {'table_count': self.table_count, 'checked_table_columns': self.schema},
            'limits': ['Лише облікові факти SQLite; банківські перекази не перевірено.',
                'Відсутність розбіжностей не доводить повноти первинних документів.',
                'ПІБ, контакти, описи операцій, документи та сесії не читаються.',
                'Жодних автоматичних виправлень, міграцій чи видалень.']})


def analyze(connection):
    """Inspect the supplied connection using only SELECT and read-only PRAGMAs."""
    with localcontext() as context:
        context.prec = 60
        return Analyzer(connection).run()


def render_markdown(report):
    lines = ['# BoS · звірка накопичених даних', '',
        'Приватний технічний звіт. Не додавати до зовнішнього CI.', '',
        'Дата: ' + report['date'], '',
        '**Покриття:** ' + ('усі заявлені перевірки виконано.' if report['complete'] else 'неповне; причини наведено нижче.'),
        '**Результат:** ' + ('потрібне рішення за стоп-умовою 8.1.' if report['stop_required'] else
            ('розбіжностей у перевіреному обсязі не знайдено.' if report['reconciled'] else 'потрібна звірка наведених фактів; автоматичні зміни не виконано.')), '']
    if 'snapshot' in report:
        snapshot = report['snapshot']
        lines += ['SHA джерела до: `' + snapshot['source_sha256_before'] + '`', '',
                  'SHA джерела після: `' + snapshot['source_sha256_after'] + '`', '',
                  'SHA копії: `' + snapshot['snapshot_sha256'] + '`', '']
    lines += ['| Перевірка | Статус |', '|---|---|']
    for name, check in report['checks'].items():
        lines.append('| ' + name + ' | ' + ('Виконано' if check['status'] == 'checked' else 'Не перевірено') + ' |')
    for finding in report['findings']:
        facts = json.dumps(finding['facts'], ensure_ascii=False, sort_keys=True)
        lines += ['', '## ' + finding['id'] + ' · ' + finding['code'], '',
                  'Клас: `' + finding['classification'] + '`.', '',
                  'Факти:', '', '```json', facts, '```', '', finding['proposal']]
    lines += ['', '## Межі висновку', '']
    lines.extend('- ' + value for value in report['limits'])
    lines += ['', 'Код завершення цього діагностичного скрипта не є прийманням продукту або повного verify.', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--timeout', type=float, default=30.0)
    args = parser.parse_args(argv)
    directory = args.output_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    paths = {name: directory / filename for name, filename in (
        ('snapshot', 'source_snapshot.sqlite3'), ('json', 'reconciliation.json'), ('md', 'DATA_RECONCILIATION_UA.md'))}
    if any(path.exists() for path in paths.values()):
        parser.error('Використайте новий каталог: попередні копії і докази не перезаписуються.')
    capture = make_snapshot(args.source, paths['snapshot'], args.timeout)
    connection = connect_readonly(paths['snapshot'])
    try:
        report = analyze(connection)
    finally:
        connection.close()
    capture['snapshot_sha256_after_analysis'] = sha256_file(paths['snapshot'])
    capture['snapshot_unchanged'] = capture['snapshot_sha256_after_analysis'] == capture['snapshot_sha256']
    report['snapshot'] = capture
    if not capture['snapshot_unchanged']:
        raise RuntimeError('SHA копії змінився: звірка не може бути прийнята.')
    with paths['json'].open('x', encoding='utf-8') as output:
        output.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    with paths['md'].open('x', encoding='utf-8') as output:
        output.write(render_markdown(report))
    print(json.dumps({'complete': report['complete'], 'reconciled': report['reconciled'],
        'stop_required': report['stop_required'], 'findings': len(report['findings']),
        'json': str(paths['json']), 'markdown': str(paths['md'])}, ensure_ascii=False))
    if report['stop_required']: return 3
    if not report['complete']: return 2
    return 0 if report['reconciled'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
