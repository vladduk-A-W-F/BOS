"""Read-only application audit; all writes target newly created temporary SQLite files.

No monkey-patching business rules: execute_wrapper adds a barrier immediately before
the existing erp_write UPDATE so both connections read the initial mutex revision.
"""
import os, sys, json, sqlite3, tempfile, hashlib, threading
from pathlib import Path
from decimal import Decimal as D
from concurrent.futures import ThreadPoolExecutor

ROOT = Path('/workspace/sites/bos-original-refined')
WORK = Path(tempfile.mkdtemp(prefix='bos-data-audit-', dir=Path(__file__).parent))
before_hash = hashlib.sha256((ROOT / 'db.sqlite3').read_bytes()).hexdigest()
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'demo_settings'
import django
from django.conf import settings
settings.DATABASES['default']['NAME'] = str(WORK / 'base.sqlite3')
settings.DATABASES['default']['OPTIONS'] = {'timeout': 2}
django.setup()
from django.core.management import call_command
from django.db import connections, connection, transaction
from django.db.models import Sum
from erp import service as s
from erp.models import Item, Location, Lot, SalesOrder, SalesLine, Production, Reservation, Purchase, Movement, OperatorEntry, Event
from operations.models import Configuration, Invoice, Document, ProcurementRequest
from finance.models import Counterparty, Salary, Transaction
from employees.models import Employee

call_command('migrate', verbosity=0)
Configuration.objects.create(key='erp_write', value={'revision': 0})
emp = Employee.objects.create(full_name='Тест', role='Тест')
customer = Counterparty.objects.create(name='Тестовий клієнт', type='customer')
supplier = Counterparty.objects.create(name='Тестовий постачальник', type='supplier')
fg = Item.objects.create(code='FG', name='Виріб')
raw = Item.objects.create(code='RAW', name='Матеріал', kind='material')
loc = Location.objects.create(code='WH', name='Склад')
dest = Location.objects.create(code='DEST', name='Дільниця', kind='production')
base = Path(settings.DATABASES['default']['NAME'])
connections.close_all()

def fresh(name):
    connections.close_all()
    target = WORK / (name + '.sqlite3')
    with sqlite3.connect(base) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    settings.DATABASES['default']['NAME'] = str(target)
    connection.settings_dict['NAME'] = str(target)

def initial_lot(item=fg, location=loc, code='LOT', qty='10'):
    lot = Lot.objects.create(code=code, item=item, location=location, revision='A', quantity=qty, quality='approved', unit_cost='1', currency='EUR')
    Movement.objects.create(lot=lot, quantity=qty, kind='opening', reference=code, cost=qty)
    return lot

def order_line(code='SO'):
    order = SalesOrder.objects.create(code=code, customer=customer, owner=emp, due_date='2026-09-20', status='confirmed')
    return SalesLine.objects.create(order=order, item=fg, revision='A', quantity='10', price='1')

def payloads(name):
    lot = initial_lot()
    line = order_line()
    def p(**kw): return {'action': 'erp_' + name, **kw}
    if name == 'reserve':
        other = order_line('SO-2')
        return [p(lot_id=lot.pk, line_id=x.pk, quantity='7') for x in (line, other)]
    if name == 'release':
        r = Reservation.objects.create(lot=lot, line=line, quantity='10')
        return [p(reservation_id=r.pk, quantity='7')] * 2
    if name == 'receive':
        po = Purchase.objects.create(code='PO', item=fg, supplier=supplier, quantity='10', price='1', due_date='2026-09-20', original_due='2026-09-20', revision='A')
        return [p(purchase_id=po.pk, code='RCV-' + k, location_id=loc.pk, quantity='7') for k in ('A', 'B')]
    if name == 'transfer':
        return [p(lot_id=lot.pk, quantity='7', location_id=dest.pk, code='TR-' + k, reason='Тест') for k in ('A', 'B')]
    if name == 'finish':
        material = initial_lot(raw, dest, 'RAW-LOT')
        job = Production.objects.create(code='MO', item=fg, quantity='10', revision='A', bom=[{'item_id': raw.pk, 'quantity': '1'}], routing=[{'name': 'Виготовлення'}], location=dest, owner=emp, due_date='2026-09-20', status='running')
        Reservation.objects.create(lot=material, production=job, quantity='10')
        OperatorEntry.objects.create(production=job, operation='Виготовлення', operator=emp, result='done')
        return [p(production_id=job.pk, quantity='7', code='OUT-' + k, location_id=loc.pk, labor_cost='0') for k in ('A', 'B')]
    if name == 'ship':
        Reservation.objects.create(lot=lot, line=line, quantity='10')
        return [p(line_id=line.pk, lot_id=lot.pk, quantity='7', reference='SHIP-' + k) for k in ('A', 'B')]
    if name in ('return', 'invoice'):
        lot.quantity = D(0); lot.save()
        line.shipped = D(10); line.save()
        Movement.objects.create(lot=lot, quantity='-10', kind='shipment', reference='SHIPPED', line=line, cost='10')
        if name == 'return':
            return [p(line_id=line.pk, lot_id=lot.pk, quantity='7', code='RET-' + k, location_id=loc.pk, reason='Тест') for k in ('A', 'B')]
        return [p(order_id=line.order_id, code='INV-' + k, due_date='2026-10-01') for k in ('A', 'B')]
    if name == 'adjust':
        return [p(lot_id=lot.pk, delta='-7', reason='Тест')] * 2
    if name in ('payment', 'payment_dup'):
        inv = Invoice.objects.create(code='INV', customer=customer, amount='20' if name == 'payment_dup' else '10', currency='EUR', due_date='2026-10-01')
        return [{'action': 'erp_payment', 'invoice_id': inv.pk, 'amount': '7', 'reference': 'SAME' if name == 'payment_dup' else 'PAY-' + k} for k in ('A', 'B')]
    raise AssertionError(name)

def integrity():
    errors = []
    for lot in Lot.objects.all():
        moves = lot.movements.aggregate(n=Sum('quantity'))['n'] or D(0)
        reserves = s.reserved(lot)
        if not (lot.quantity == moves and D(0) <= reserves <= lot.quantity):
            errors.append({'lot': lot.code, 'qty': str(lot.quantity), 'movements': str(moves), 'reserved': str(reserves)})
    for line in SalesLine.objects.all():
        if not D(0) <= line.invoiced <= line.shipped <= line.quantity: errors.append('line bounds')
    for inv in Invoice.objects.all():
        if not D(0) <= inv.paid <= inv.amount: errors.append('invoice bounds')
    return errors

out = {'django': django.get_version(), 'sqlite': sqlite3.sqlite_version, 'database_directory': str(WORK), 'cases': []}
for name in ('reserve', 'release', 'receive', 'transfer', 'finish', 'ship', 'return', 'adjust', 'payment', 'payment_dup', 'invoice'):
    fresh(name)
    pair = payloads(name)
    gate = threading.Barrier(2, timeout=10)
    def run(pair_index):
        def barrier(execute, sql, params, many, context):
            if sql.startswith('UPDATE "operations_configuration"'):
                gate.wait()
            return execute(sql, params, many, context)
        try:
            with connection.execute_wrapper(barrier):
                result = s.dispatch(pair[pair_index], role='ceo')
            return {'worker': pair_index, 'status': 'succeeded', 'result': result}
        except Exception as e:
            return {'worker': pair_index, 'status': type(e).__name__, 'error': str(e), 'sqlite_code': getattr(e.__cause__, 'sqlite_errorname', None)}
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (0, 1)))
    failed = next(x for x in results if x['status'] != 'succeeded')
    try:
        retry = {'status': 'succeeded', 'result': s.dispatch(pair[failed['worker']], role='ceo')}
    except Exception as e:
        retry = {'status': type(e).__name__, 'error': str(e)}
    err = integrity()
    case = {'action': name, 'workers': results, 'retry': retry, 'integrity_errors': err, 'event_count': Event.objects.count()}
    assert sum(x['status'] == 'succeeded' for x in results) == 1, case
    assert failed['status'] == 'OperationalError', case
    assert retry['status'] == 'ValueError' and not err and Event.objects.count() == 1, case
    out['cases'].append(case)

# Related current-local financial path bypasses ERP serialization. Both callers
# fetch the same unpaid salary, just as finance.views.SalaryViewSet.pay() does.
fresh('salary_duplicate')
salary = Salary.objects.create(employee=emp, amount='100', period_year=2026, period_month=9)
gate = threading.Barrier(2, timeout=10)
def pay_salary(worker):
    obj = Salary.objects.select_related('employee', 'transaction').get(pk=salary.pk)
    gate.wait()
    try:
        obj.mark_paid('2026-09-10')
        return {'worker': worker, 'status': 'succeeded', 'transaction_id': obj.transaction_id}
    except Exception as e:
        return {'worker': worker, 'status': type(e).__name__, 'error': str(e)}
    finally:
        connections.close_all()
with ThreadPoolExecutor(max_workers=2) as pool:
    result = list(pool.map(pay_salary, (0, 1)))
salary.refresh_from_db()
out['salary_duplicate'] = {'workers': result, 'transaction_count': Transaction.objects.count(), 'transaction_total': str(Transaction.objects.aggregate(n=Sum('amount'))['n']), 'salary_transaction_id': salary.transaction_id}
assert all(x['status'] == 'succeeded' for x in result) and Transaction.objects.count() == 2

out['original_db_sha256_before'] = before_hash
out['original_db_sha256_after'] = hashlib.sha256((ROOT / 'db.sqlite3').read_bytes()).hexdigest()
assert out['original_db_sha256_before'] == out['original_db_sha256_after']
print(json.dumps(out, ensure_ascii=False, indent=2))
