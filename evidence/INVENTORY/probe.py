"""Відтворення дефектів 0.1 на новій синтетичній SQLite без mocks.

Exit 0 означає відтворення зазначених дефектів, а не приймання продукту.
Код застосунку та всі SQLite-файли в checkout лише хешуються/читаються.
"""
import hashlib
import inspect
import json
import os
import sqlite3
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

ROOT = Path('/workspace/sites/bos-original-refined')
WORK = Path(__file__).resolve().parent
AUDIT_DIR = Path(tempfile.mkdtemp(prefix='master_inventory_db_', dir=WORK))

def hashes(paths):
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}

source_before = hashes(ROOT.rglob('*.py'))
db_before = hashes(ROOT.glob('*.sqlite3'))
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'demo_settings'
import django
from django.conf import settings
settings.DATABASES['default']['NAME'] = str(AUDIT_DIR / 'audit.sqlite3')
settings.DATABASES['default']['OPTIONS'] = {'timeout': 20}
django.setup()

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections
from django.db.models import Sum
from django.test import Client
from django.urls import URLResolver, get_resolver
from employees.models import Employee
from erp.models import Item, Location, Lot, Movement, Production, Event
from finance.models import Salary, Transaction, Contract, Counterparty
from finance.serializers import SalarySerializer, TransactionSerializer
from operations.models import Configuration
from erp.service import reserved
from rest_framework import VERSION as DRF_VERSION
from rest_framework.mixins import CreateModelMixin, UpdateModelMixin, DestroyModelMixin
from rest_framework.serializers import ModelSerializer
from django.contrib.admin.options import ModelAdmin

call_command('migrate', verbosity=0)
Configuration.objects.create(key='erp_write', value={'revision': 0})
client = Client(enforce_csrf_checks=True, REMOTE_ADDR='127.0.0.1')
assert client.get('/api/operations/status/').status_code == 200
trace = []

def request(method, path, payload=None):
    token = client.cookies['csrftoken'].value
    response = getattr(client, method)(path, data=json.dumps(payload or {}), content_type='application/json', HTTP_X_CSRFTOKEN=token)
    body = response.json() if response.content else None
    trace.append({'method': method.upper(), 'path': path, 'status': response.status_code})
    return response.status_code, body

def employee(tag):
    return Employee.objects.create(full_name='Синтетичний ' + tag, role='Тест')

def salary(tag, currency='UAH'):
    return Salary.objects.create(employee=employee(tag), amount='100', currency=currency, period_year=2026, period_month=9)

def paid_salary(tag, currency='UAH'):
    sal = salary(tag, currency)
    code, body = request('post', f'/api/salaries/{sal.pk}/pay/', {'payment_date': '2026-09-11'})
    assert code == 200, body
    sal.refresh_from_db()
    return sal

def confirmed(payload):
    status, preview = request('post', '/api/erp/preview/', payload)
    assert status == 200, preview
    status, result = request('post', '/api/operations/confirm/', {'confirmed': True, 'proposal_id': preview['id']})
    assert status == 200, result
    return preview['id'], result

cases = {}

# A01: двічі резервується одна партія; весь користувацький запис через HTTP.
emp = employee('Виробництво')
material = Item.objects.create(code='AUD-RAW', name='Синтетичний матеріал', kind='material')
product = Item.objects.create(code='AUD-FG', name='Синтетичний виріб')
plant = Location.objects.create(code='AUD-PLANT', name='Дільниця', kind='production')
warehouse = Location.objects.create(code='AUD-WH', name='Склад')
lot = Lot.objects.create(code='AUD-LOT', item=material, location=plant, revision='A', quantity='10', unit_cost='1', currency='EUR', quality='approved')
Movement.objects.create(lot=lot, quantity='10', cost='10', kind='opening', reference='AUD-LOT')
job = Production.objects.create(code='AUD-MO', item=product, quantity='10', revision='A', bom=[{'item_id': material.pk, 'quantity': '1'}], routing=[{'name': 'Виготовлення'}], location=plant, owner=emp, due_date='2026-09-20')
for _ in range(2):
    confirmed({'action': 'erp_reserve', 'lot_id': lot.pk, 'production_id': job.pk, 'quantity': '5'})
confirmed({'action': 'erp_start', 'production_id': job.pk})
confirmed({'action': 'erp_operator', 'production_id': job.pk, 'operation': 'Виготовлення', 'operator_id': emp.pk, 'result': 'done', 'minutes': 1, 'defects': '0'})
proposal_id, receipt = confirmed({'action': 'erp_finish', 'production_id': job.pk, 'quantity': '10', 'code': 'AUD-OUTPUT', 'location_id': warehouse.pk, 'labor_cost': '0'})
lot.refresh_from_db(); job.refresh_from_db()
movement_total = lot.movements.aggregate(n=Sum('quantity'))['n']
counts = (Movement.objects.count(), Event.objects.count(), Lot.objects.count())
status, repeat = request('post', '/api/operations/confirm/', {'confirmed': True, 'proposal_id': proposal_id})
cases['finish_repeated_lot'] = {'defect_reproduced': lot.quantity != movement_total, 'quantity': str(lot.quantity), 'movement_total': str(movement_total), 'reserved': str(reserved(lot)), 'produced': str(job.produced), 'repeat_same_receipt': status == 200 and repeat == receipt, 'repeat_no_new_rows': counts == (Movement.objects.count(), Event.objects.count(), Lot.objects.count()), 'expected_when_fixed': 'quantity == movement_total == 0'}
assert cases['finish_repeated_lot']['defect_reproduced']

# A02: два справжні ORM-читання pending завершуються до mark_paid.
# Бар'єр керує лише порядком викликів; функції та SQL не підмінюються.
sal = salary('Паралельність')
baseline_ids = set(Transaction.objects.values_list('pk', flat=True))
barrier = threading.Barrier(2, timeout=15)
def pay_concurrently(worker):
    try:
        stale = Salary.objects.select_related('employee', 'transaction').get(pk=sal.pk)
        barrier.wait()
        stale.mark_paid('2026-09-11')
        return {'worker': worker, 'status': 'succeeded', 'transaction_id': stale.transaction_id}
    except Exception as exc:
        return {'worker': worker, 'status': type(exc).__name__, 'message': str(exc)}
    finally:
        connections.close_all()
with ThreadPoolExecutor(max_workers=2) as pool:
    workers = list(pool.map(pay_concurrently, (0, 1)))
new_transactions = Transaction.objects.exclude(pk__in=baseline_ids)
sal.refresh_from_db()
cases['salary_concurrent_payment'] = {'defect_reproduced': new_transactions.count() == 2, 'workers': workers, 'transaction_count': new_transactions.count(), 'transaction_total': str(new_transactions.aggregate(n=Sum('amount'))['n']), 'salary_transaction_id': sal.transaction_id, 'expected_when_fixed': 'one expense 100 and one stable source link'}
assert cases['salary_concurrent_payment']['defect_reproduced'], cases['salary_concurrent_payment']

# Зарплатний serializer: створення paid без проводки.
emp = employee('Створення paid')
status, body = request('post', '/api/salaries/', {'employee': emp.pk, 'amount': '100.00', 'currency': 'UAH', 'period_year': 2026, 'period_month': 9, 'status': 'paid'})
cases['salary_serializer_create_paid'] = {'defect_reproduced': status == 201 and body['status'] == 'paid' and body['transaction'] is None, 'http_status': status, 'salary_status': body.get('status'), 'transaction': body.get('transaction'), 'expected_when_fixed': 'reject inconsistent state or create exactly one expense atomically'}
assert cases['salary_serializer_create_paid']['defect_reproduced'], body

# І зміна суми вже виплаченої зарплати.
sal = paid_salary('Зміна нарахування')
tx_id = sal.transaction_id
status, body = request('patch', f'/api/salaries/{sal.pk}/', {'amount': '200.00'})
sal.refresh_from_db(); tx = Transaction.objects.get(pk=tx_id)
cases['salary_serializer_update_paid'] = {'defect_reproduced': status == 200 and sal.amount != tx.amount, 'http_status': status, 'salary_amount': str(sal.amount), 'transaction_amount': str(tx.amount), 'expected_when_fixed': 'immutable payment history; explicit correction instead of silent rewrite'}
assert cases['salary_serializer_update_paid']['defect_reproduced']

# Той самий serializer дозволяє повторно відкрити вже сплачену зарплату.
sal = paid_salary('Повтор після PATCH')
first_tx = sal.transaction_id
status, _ = request('patch', f'/api/salaries/{sal.pk}/', {'status': 'pending'})
status2, _ = request('post', f'/api/salaries/{sal.pk}/pay/', {'payment_date': '2026-09-11'})
sal.refresh_from_db()
cases['salary_serializer_reopen_then_pay'] = {'defect_reproduced': status == 200 and status2 == 200 and sal.transaction_id != first_tx and Transaction.objects.filter(pk=first_tx).exists(), 'patch_status': status, 'pay_status': status2, 'first_transaction': first_tx, 'second_transaction': sal.transaction_id, 'expected_when_fixed': 'cannot silently reset a paid accrual and create another expense'}
assert cases['salary_serializer_reopen_then_pay']['defect_reproduced']

# Проводковий serializer переписує суму прив'язаної зарплатної проводки.
sal = paid_salary('Зміна проводки')
status, body = request('patch', f'/api/transactions/{sal.transaction_id}/', {'amount': '300.00', 'direction': 'in'})
tx = Transaction.objects.get(pk=sal.transaction_id)
cases['transaction_serializer_update_salary_expense'] = {'defect_reproduced': status == 200 and (tx.amount != sal.amount or tx.direction != 'out'), 'http_status': status, 'salary_amount': str(sal.amount), 'transaction_amount': str(tx.amount), 'transaction_direction': tx.direction, 'expected_when_fixed': 'expense remains immutable and linked to the source'}
assert cases['transaction_serializer_update_salary_expense']['defect_reproduced']

sal = paid_salary('Видалення нарахування')
salary_id, tx_id = sal.pk, sal.transaction_id
status, _ = request('delete', f'/api/salaries/{salary_id}/')
cases['salary_api_destroy'] = {'defect_reproduced': status == 204 and not Salary.objects.filter(pk=salary_id).exists() and Transaction.objects.filter(pk=tx_id).exists(), 'http_status': status, 'salary_exists': Salary.objects.filter(pk=salary_id).exists(), 'transaction_exists': Transaction.objects.filter(pk=tx_id).exists(), 'expense_has_source': Salary.objects.filter(transaction_id=tx_id).exists(), 'expected_when_fixed': 'retain historical accrual and expense source'}
assert cases['salary_api_destroy']['defect_reproduced']

sal = paid_salary('Видалення проводки')
tx_id = sal.transaction_id
status, _ = request('delete', f'/api/transactions/{tx_id}/')
sal.refresh_from_db()
cases['transaction_api_destroy'] = {'defect_reproduced': status == 204 and sal.status == 'paid' and sal.transaction_id is None, 'http_status': status, 'salary_status': sal.status, 'transaction': sal.transaction_id, 'expected_when_fixed': 'paid salary retains exactly one expense'}
assert cases['transaction_api_destroy']['defect_reproduced']

sal = paid_salary('Видалення працівника')
salary_id, tx_id, employee_id = sal.pk, sal.transaction_id, sal.employee_id
status, _ = request('delete', f'/api/employees/{employee_id}/')
cases['employee_api_destroy_salary_cascade'] = {'defect_reproduced': status == 204 and not Salary.objects.filter(pk=salary_id).exists() and Transaction.objects.filter(pk=tx_id).exists(), 'http_status': status, 'salary_exists': Salary.objects.filter(pk=salary_id).exists(), 'transaction_exists': Transaction.objects.filter(pk=tx_id).exists(), 'expected_when_fixed': 'archive employee; preserve payroll history and source'}
assert cases['employee_api_destroy_salary_cascade']['defect_reproduced']

sal = paid_salary('Валюта EUR', currency='EUR')
tx = Transaction.objects.get(pk=sal.transaction_id)
cases['salary_payment_currency'] = {'defect_reproduced': sal.currency != tx.currency, 'salary_currency': sal.currency, 'transaction_currency': tx.currency, 'salary_amount': str(sal.amount), 'transaction_amount': str(tx.amount), 'expected_when_fixed': 'expense currency equals salary currency'}
assert cases['salary_payment_currency']['defect_reproduced']

# Справжній admin з авторизованим synthetic superuser і чинним CSRF.
user = get_user_model().objects.create_superuser(username='audit-admin', email='', password='synthetic-audit-only')
admin_client = Client(enforce_csrf_checks=True, REMOTE_ADDR='127.0.0.1')
assert admin_client.login(username='audit-admin', password='synthetic-audit-only')
assert admin_client.get('/admin/').status_code == 200

def admin_post(path, data):
    response = admin_client.post(path, data=data, HTTP_X_CSRFTOKEN=admin_client.cookies['csrftoken'].value)
    trace.append({'method': 'POST', 'path': path, 'status': response.status_code, 'entry': 'authenticated_admin'})
    if response.status_code == 200 and response.context and 'adminform' in response.context:
        errors = str(response.context['adminform'].form.errors)
    else:
        errors = None
    return response.status_code, errors

def salary_form(sal, **overrides):
    data = {'employee': sal.employee_id, 'amount': str(sal.amount), 'currency': sal.currency, 'period_year': sal.period_year, 'period_month': sal.period_month, 'payment_date': '2026-09-11', 'status': sal.status, 'notes': sal.notes, 'transaction': sal.transaction_id or '', '_save': 'Зберегти'}
    data.update(overrides)
    return data

sal = salary('Admin paid')
status, errors = admin_post(f'/admin/finance/salary/{sal.pk}/change/', salary_form(sal, status='paid'))
sal.refresh_from_db()
cases['salary_admin_save_model'] = {'defect_reproduced': status == 302 and sal.status == 'paid' and sal.transaction_id is None, 'http_status': status, 'errors': errors, 'salary_status': sal.status, 'transaction': sal.transaction_id, 'expected_when_fixed': 'admin uses same protected payment service'}
assert cases['salary_admin_save_model']['defect_reproduced'], cases['salary_admin_save_model']

sal = paid_salary('Admin проводка')
tx = Transaction.objects.get(pk=sal.transaction_id)
form = {'direction': 'in', 'amount': '400.00', 'currency': tx.currency, 'date': '2026-09-11', 'description': tx.description, 'category': 'salary', 'counterparty': '', 'contract': '', 'branch': '', '_save': 'Зберегти'}
status, errors = admin_post(f'/admin/finance/transaction/{tx.pk}/change/', form)
tx.refresh_from_db()
cases['transaction_admin_save_model'] = {'defect_reproduced': status == 302 and (tx.direction != 'out' or tx.amount != sal.amount), 'http_status': status, 'errors': errors, 'salary_amount': str(sal.amount), 'transaction_amount': str(tx.amount), 'transaction_direction': tx.direction, 'expected_when_fixed': 'admin cannot rewrite posted salary expense'}
assert cases['transaction_admin_save_model']['defect_reproduced'], cases['transaction_admin_save_model']

for model, prefix in [(Salary, 'salary'), (Transaction, 'transaction'), (Employee, 'employee')]:
    for deletion_mode in ('single', 'bulk'):
        sal = paid_salary(f'Admin delete {prefix} {deletion_mode}')
        salary_id, tx_id = sal.pk, sal.transaction_id
        target_id = sal.pk if model is Salary else tx_id if model is Transaction else sal.employee_id
        base_path = f'/admin/{model._meta.app_label}/{model._meta.model_name}/'
        path = f'{base_path}{target_id}/delete/' if deletion_mode == 'single' else base_path
        data = {'post': 'yes'} if deletion_mode == 'single' else {'action': 'delete_selected', '_selected_action': str(target_id), 'post': 'yes'}
        status, errors = admin_post(path, data)
        surviving_salary = Salary.objects.filter(pk=salary_id).first()
        source_missing = surviving_salary is None and Transaction.objects.filter(pk=tx_id).exists()
        expense_missing = surviving_salary is not None and surviving_salary.status == 'paid' and surviving_salary.transaction_id is None
        cases[f'{prefix}_admin_delete_{deletion_mode}'] = {'defect_reproduced': status == 302 and (source_missing or expense_missing), 'http_status': status, 'salary_exists': surviving_salary is not None, 'transaction_exists': Transaction.objects.filter(pk=tx_id).exists(), 'salary_status': surviving_salary.status if surviving_salary else None, 'salary_transaction': surviving_salary.transaction_id if surviving_salary else None, 'expected_when_fixed': 'preserve payroll history and one linked expense'}
        assert cases[f'{prefix}_admin_delete_{deletion_mode}']['defect_reproduced'], cases[f'{prefix}_admin_delete_{deletion_mode}']

def serializer_fields(cls):
    return {name: {'read_only': field.read_only, 'required': field.required, 'allow_null': field.allow_null} for name, field in cls().fields.items()}

def source_ref(fn):
    lines, start = inspect.getsourcelines(fn)
    return {'file': inspect.getsourcefile(fn), 'line': start, 'source': ''.join(lines)}

def routes(patterns, prefix=''):
    result = []
    for item in patterns:
        path = prefix + str(item.pattern)
        if isinstance(item, URLResolver):
            result.extend(routes(item.url_patterns, path))
        else:
            callback = item.callback
            actions = getattr(callback, 'actions', {})
            mutations = {k: v for k, v in actions.items() if k.lower() in ('post', 'put', 'patch', 'delete')}
            if mutations:
                result.append({'route': path, 'actions': mutations, 'view': callback.cls.__module__ + '.' + callback.cls.__name__})
    return result

source_after = hashes(ROOT.rglob('*.py'))
db_after = hashes(ROOT.glob('*.sqlite3'))
assert source_before == source_after, 'Application Python sources changed during probe'
assert db_before == db_after, 'Checkout database hashes changed during probe'
output = {
    'purpose': 'Діагностичне відтворення дефектів; exit 0 не означає приймання',
    'date': '2026-09-11',
    'environment': {'python': sys.version, 'django': django.get_version(), 'drf': DRF_VERSION, 'sqlite': sqlite3.sqlite_version, 'database': str(AUDIT_DIR / 'audit.sqlite3'), 'http_client': 'Django Client, enforce_csrf_checks=True, local address', 'mocks': False, 'production_code_changes': False},
    'cases': cases,
    'all_defects_reproduced': all(c['defect_reproduced'] for c in cases.values()),
    'request_trace': trace,
    'serializer_fields': {'SalarySerializer': serializer_fields(SalarySerializer), 'TransactionSerializer': serializer_fields(TransactionSerializer)},
    'drf_write_routes': routes(get_resolver().url_patterns),
    'admin_registry': [{'model': m._meta.label, 'admin_class': type(a).__module__ + '.' + type(a).__name__, 'readonly_fields': list(a.readonly_fields), 'save_model': a.save_model.__qualname__, 'delete_model': a.delete_model.__qualname__, 'delete_queryset': a.delete_queryset.__qualname__} for m, a in admin.site._registry.items()],
    'framework_sources': {name: source_ref(fn) for name, fn in {'ModelSerializer.create': ModelSerializer.create, 'ModelSerializer.update': ModelSerializer.update, 'CreateModelMixin.perform_create': CreateModelMixin.perform_create, 'UpdateModelMixin.perform_update': UpdateModelMixin.perform_update, 'DestroyModelMixin.perform_destroy': DestroyModelMixin.perform_destroy, 'ModelAdmin.changeform_view': ModelAdmin.changeform_view, 'ModelAdmin.save_model': ModelAdmin.save_model, 'ModelAdmin.delete_view': ModelAdmin.delete_view, 'ModelAdmin.delete_model': ModelAdmin.delete_model, 'ModelAdmin.delete_queryset': ModelAdmin.delete_queryset}.items()},
    'source_sha256_before': source_before,
    'source_sha256_after': source_after,
    'checkout_database_sha256_before': db_before,
    'checkout_database_sha256_after': db_after,
    'checkout_databases_unchanged': db_before == db_after,
    'application_python_sources_unchanged': source_before == source_after,
    'not_run': ['PostgreSQL', 'HTTP concurrency', 'Windows', 'browser', 'production data reconciliation', 'external LLM', 'verify']
}
target = WORK / 'master_inventory_probe_output.json'
target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'output': str(target), 'cases': len(cases), 'all_defects_reproduced': output['all_defects_reproduced'], 'checkout_databases_unchanged': output['checkout_databases_unchanged'], 'application_python_sources_unchanged': output['application_python_sources_unchanged'], 'case_results': {key: {'defect_reproduced': row['defect_reproduced'], **{k: v for k, v in row.items() if k in ('http_status', 'quantity', 'movement_total', 'transaction_count', 'transaction_total', 'salary_currency', 'transaction_currency')}} for key, row in cases.items()}}, ensure_ascii=False, indent=2))
