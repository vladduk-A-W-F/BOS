"""A07 latest synthetic transfer fixture; caller configures and migrates NEW DB.

populate() refuses nonempty domain/auth/session tables before writing. It uses
the real ERP dispatcher, financial commands, archive commands and HTTP auth /
CSRF / proposal workflow. Only synthetic timestamp metadata is fixed after
those commands; no quantities, amounts, source IDs or statuses are rewritten.

verify_facts(expected) is read-only and compares independent domain expectations
plus exact canonical ORM rows/PK/FK/bytes against populate()'s JSON-safe manifest.
Neither function migrates, transfers, resets sequences or accesses another DB.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import UUID

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.db import connection, models, transaction
from django.test import Client

from ai_assistant.models import ChatFile, ChatMessage
from employees.models import Employee
from finance.commands import save_salary, save_transaction
from finance.models import Counterparty, FinancialIntent, Salary, Transaction
from operations.models import ActionProposal, AuditEvent, Configuration, Document, Invoice
from operations.service import newest
from erp import service
from erp.models import (
    Event, Inspection, InvoiceLink, Item, Location, Lot, Movement,
    OperatorEntry, Production, Purchase, Reservation, SalesLine, SalesOrder,
)
from scripts.check_support import login_test_client


FORMAT = 'bos-a07-latest-fixture/1'
CURRENCIES = ('EUR', 'USD', 'UAH')
DAY = date(2026, 9, 11)
STAMP = datetime(2026, 9, 11, 12, 0, 0, 123456, tzinfo=timezone.utc)
ARCHIVED = datetime(2026, 9, 11, 12, 5, 0, 654321, tzinfo=timezone.utc)
EXPIRY = datetime(2099, 1, 1, 0, 0, 0, 987654, tzinfo=timezone.utc)


def _check(condition, detail):
    if not condition:
        raise AssertionError('A07 fixture: ' + detail)


def _eq(actual, expected, detail):
    _check(actual == expected, f'{detail}: expected {expected!r}, got {actual!r}')


def _safe_runtime():
    """Reject installation names before a connection or table query is made."""
    requested = os.environ.get('BOS_TEST_DB_NAME', '')
    backend = os.environ.get('BOS_VERIFY_DB', '')
    configured = str(connection.settings_dict['NAME'])
    _check(backend in ('sqlite', 'postgres') and requested, 'explicit verification DB environment required')
    if backend == 'sqlite':
        _check(connection.vendor == 'sqlite', 'expected actual SQLite backend')
        _check(configured in (requested, requested + '_django_test'), 'configured SQLite is not caller test DB')
        _check(configured != ':memory:' and 'mode=memory' not in configured, 'use a named disposable SQLite')
        path = Path(configured).resolve()
        _check(path.name.lower() not in ('db.sqlite3', 'bos_demo.sqlite3'), 'installation database name refused')
        # After root integrates under scripts/, BASE_DIR still identifies the
        # installation root. Explicit test databases must be outside that root.
        base = Path(settings.BASE_DIR).resolve()
        _check(not path.is_relative_to(base), 'test DB cannot reside inside the installation checkout')
    else:
        _check(connection.vendor == 'postgresql', 'expected actual PostgreSQL backend')
        _check(os.environ.get('BOS_PG_DISPOSABLE') == '1', 'PostgreSQL disposable marker required')
        _check(bool(re.fullmatch(r'bos_verify_[a-f0-9]{16}', requested)), 'PostgreSQL verification name required')
        _check(configured in (requested, 'test_' + requested), 'configured PostgreSQL is not caller test DB')
    media = Path(settings.MEDIA_ROOT).resolve()
    _check(os.environ.get('BOS_TEST_MEDIA') and media == Path(os.environ['BOS_TEST_MEDIA']).resolve(),
           'explicit synthetic MEDIA_ROOT required')


def _tracked_models():
    # The transport manifest separately checks exact ContentType/Permission and
    # django_migrations rows. This independent domain oracle excludes bootstrap
    # metadata while retaining exact auth User/Group IDs and their through rows.
    excluded = {'contenttypes.contenttype', 'auth.permission'}
    values = []
    seen = set()
    for model in apps.get_models(include_auto_created=True):
        if model._meta.proxy or not model._meta.managed or model._meta.label_lower in excluded:
            continue
        if model._meta.db_table not in seen:
            seen.add(model._meta.db_table)
            values.append(model)
    return sorted(values, key=lambda model: model._meta.label_lower)


def _encode(value):
    if isinstance(value, D):
        return {'$decimal': format(value, 'f')}
    if isinstance(value, datetime):
        _check(value.tzinfo is not None, 'naive datetime in fixture')
        return {'$datetime': value.astimezone(timezone.utc).isoformat(timespec='microseconds')}
    if isinstance(value, date):
        return {'$date': value.isoformat()}
    if isinstance(value, UUID):
        return {'$uuid': str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {'$bytes': base64.b64encode(raw).decode('ascii'),
                'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _snapshot():
    result = {}
    for model in _tracked_models():
        fields = [field.attname for field in model._meta.concrete_fields]
        rows = [_encode(row) for row in model._base_manager.order_by(model._meta.pk.name).values(*fields)]
        result[model._meta.label_lower] = {'count': len(rows), 'rows': rows, 'sha256': _digest(rows)}
    return result


def _with_mutex_increment(snapshot, increment):
    expected = deepcopy(snapshot)
    configs = expected['operations.configuration']
    matches = [row for row in configs['rows'] if row['key'] == 'erp_write']
    _eq(len(matches), 1, 'exact one ERP mutex record')
    matches[0]['value']['revision'] += increment
    configs['sha256'] = _digest(configs['rows'])
    return expected


def _post(client, route, payload):
    response = client.post(route, json.dumps(payload, ensure_ascii=True), content_type='application/json',
        HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
    _eq(response.status_code, 200, route + ' response ' + repr(response.content[:500]))
    return response.json()


def _run(action, **fields):
    return service.dispatch({'action': 'erp_' + action, **fields}, role='ceo')


def _approve(client, document):
    _post(client, f'/api/operations/documents/{document.pk}/review/', {'checksum': document.checksum})
    document.refresh_from_db()
    _eq(document.status, 'approved', 'document approval')


def _documents(client):
    a = 'Синтетична специфікація A · ЇЄҐ 🙂'.encode() + b'\x00A'
    b = bytes(range(256)) + 'Синтетична специфікація B · ЇЄҐ 🙂'.encode()
    specs = ((7, 'A07-SPEC', 'A', a), (1001, 'A07-SPEC', 'B', b),
             (90001, 'A07-TEXT-ONLY', 'A', b''))
    result = {}
    for pk, code, revision, content in specs:
        document = Document.objects.create(pk=pk, code=code, revision=revision,
            title='Синтетичний документ ' + code, filename=code + '-' + revision + '.bin',
            content=content, text='Текстова версія ' + revision + ' · ЇЄҐ 🙂',
            sections=[{'number': 1, 'title': 'Вимоги', 'approved': True, 'value': '0.10', 'optional': None}],
            checksum=hashlib.sha256(content).hexdigest(), status='needs_review', access_level='ceo')
        _approve(client, document)
        result[str(pk)] = {'id': pk, 'code': code, 'revision': revision, 'bytes': _encode(content)}
    _eq(newest('A07-SPEC').pk, 1001, 'latest specification is version B')
    return result


def _currency_fixture(currency, user, client, *, completed_http=False):
    code = lambda suffix: 'A07-' + currency + '-' + suffix
    refs = {}
    owner = Employee.objects.create(full_name='Синтетичний оператор ' + currency,
        role='Оператор', department='Синтетичний A07', birthday=date(1990, 2, 3),
        user=user if completed_http else None)
    customer = Counterparty.objects.create(name='Синтетичний клієнт ' + currency, type='customer')
    supplier = Counterparty.objects.create(name='Синтетичний постачальник ' + currency, type='supplier')
    refs.update(employee=owner.pk, customer=customer.pk, supplier=supplier.pk)
    prod = _run('location', code=code('PROD'), name='Дільниця ' + currency, kind='production')['location_id']
    store = _run('location', code=code('STORE'), name='Склад ' + currency, kind='warehouse')['location_id']
    refs.update(location_production=prod, location_stock=store)
    material = _run('item', code=code('M'), name='Матеріал ' + currency, unit='шт.', kind='material',
        method='buy', revision='B', currency=currency, document_id=1001, required_documents=['cert'],
        external_codes={'постачальник': {'code': 'М-01', 'active': True, 'count': 1, 'optional': None}})['item_id']
    finished = _run('item', code=code('F'), name='Виріб ' + currency, unit='шт.', kind='product',
        method='make', revision='B', currency=currency, document_id=1001, required_documents=['cert'],
        planned_cost='3.00', bom=[{'item_id': material, 'quantity': '1.000'}],
        routing=[{'name': 'Виготовлення', 'instruction': 'Синтетична операція · ЇЄҐ 🙂', 'days': 1}])['item_id']
    refs.update(raw_item=material, finished_item=finished)
    raw = _run('opening', code=code('RAW'), item_id=material, location_id=prod, quantity='10.000',
        unit_cost='2.00', currency=currency, revision='B', documents={'cert': 1001})['lot_id']
    _run('quality', lot_id=raw, result='approved', inspector_id=owner.pk, note='Погоджено версію B')
    job = _run('job', code=code('JOB'), item_id=finished, location_id=prod, quantity='10.000',
        owner_id=owner.pk, due_date='2026-09-30')['production_id']
    reserves = [_run('reserve', lot_id=raw, production_id=job, quantity='5.000')['reservation_id']
                for _ in range(2)]
    _run('start', production_id=job)
    _run('operator', production_id=job, operation='Виготовлення', operator_id=owner.pk,
        result='done', minutes=12, defects='0.000', note='Синтетичний факт виконання')
    production = _run('finish', production_id=job, quantity='4.000', code=code('OUTPUT'),
        location_id=store, labor_cost='4.00', documents={'cert': 1001})
    output = production['lot_id']
    _run('quality', lot_id=output, result='approved', inspector_id=owner.pk, note='Випуск відповідає версії B')
    refs.update(raw_lot=raw, output_lot=output, job=job, reserve_material_ids=reserves,
                finish_event=production['erp_event_id'])
    order_payload = {'action': 'erp_order', 'code': code('SO'), 'customer_id': customer.pk,
        'owner_id': owner.pk, 'due_date': '2026-10-10', 'currency': currency,
        'lines': [{'item_id': finished, 'quantity': '3.000', 'price': '5.00'}],
        'notes': 'Синтетичний продаж для перенесення'}
    if completed_http:
        preview = _post(client, '/api/erp/preview/', order_payload)
        _check(not SalesOrder.objects.filter(code=code('SO')).exists(), 'HTTP preview must not create order')
        result = _post(client, '/api/operations/confirm/', {'proposal_id': preview['id'], 'confirmed': True})
        stable = _snapshot()
        replay = _post(client, '/api/operations/confirm/', {'proposal_id': preview['id'], 'confirmed': True})
        _eq(replay, result, 'completed HTTP receipt replay')
        # A06 deliberately advances its bookkeeping mutex once on receipt
        # replay. All source/receipt rows must remain byte-for-byte unchanged.
        replay_expected = _with_mutex_increment(stable, 1)
        _eq(_snapshot(), replay_expected, 'completed HTTP replay changed sources/receipt beyond mutex bookkeeping')
        refs['completed_proposal'] = preview['id']
    else:
        result = service.dispatch(order_payload, role='ceo')
    order = result['order_id']
    _run('confirm_order', order_id=order)
    line = SalesLine.objects.get(order_id=order)
    sales_reserve = _run('reserve', lot_id=output, line_id=line.pk, quantity='3.000')['reservation_id']
    _run('ship', line_id=line.pk, lot_id=output, quantity='3.000', reference=code('SHIP'))
    invoice = _run('invoice', order_id=order, code=code('INV'), due_date='2026-10-20')
    payment = _run('payment', invoice_id=invoice['invoice_id'], amount='5.00', reference=code('PAY'))
    returned = _run('return', line_id=line.pk, lot_id=output, quantity='1.000', code=code('RETURN'),
        location_id=store, reason='Синтетичне повернення без прихованого коригування рахунку')
    po = _run('purchase', code=code('PO'), item_id=material, supplier_id=supplier.pk,
        quantity='10.000', price='2.00', extras='10.00', currency=currency, due_date='2026-10-01', revision='B',
        direct_reason='Синтетична пряма закупівля матеріалу для перевірки перенесення та часткового приймання.')
    received = _run('receive', purchase_id=po['purchase_id'], code=code('RECEIPT'), location_id=store,
        quantity='7.000', documents={'cert': 1001})
    refs.update(order=order, line=line.pk, reserve_sales=sales_reserve,
        invoice=invoice['invoice_id'], invoice_event=invoice['erp_event_id'], payment_event=payment['erp_event_id'],
        returned_lot=returned['lot_id'], return_event=returned['erp_event_id'], purchase=po['purchase_id'],
        receipt_lot=received['lot_id'], receipt_event=received['erp_event_id'])
    salary_payload = dict(employee=owner, amount=D('100.00'), currency=currency,
        period_year=2026, period_month=9, notes='Синтетичне нарахування ЇЄҐ')
    salary = save_salary(changes=salary_payload, actor=user, operation_id=code('SALARY-CREATE'))
    salary, expense = salary.mark_paid(DAY)
    income_payload = dict(direction='in', amount=D('200.00'), currency=currency, date=DAY,
        description='Синтетичний ручний дохід ' + currency, category='customer', counterparty=customer)
    income = save_transaction(changes=income_payload, actor=user, operation_id=code('INCOME-CREATE'))
    before_archive = [(row.pk, row.amount, row.direction) for row in Transaction.objects.filter(currency=currency)]
    salary.delete(actor=user)
    expense.delete(actor=user)
    _eq([(row.pk, row.amount, row.direction) for row in Transaction.objects.filter(currency=currency)],
        before_archive, 'archive changed financial source amounts/IDs')
    repeated_salary, repeated_expense = salary.mark_paid(DAY)
    _eq((repeated_salary.pk, repeated_expense.pk), (salary.pk, expense.pk), 'archived paid replay duplicated expense')
    _eq(save_salary(changes=salary_payload, actor=user, operation_id=code('SALARY-CREATE')).pk,
        salary.pk, 'salary creation intent replay')
    _eq(save_transaction(changes=income_payload, actor=user, operation_id=code('INCOME-CREATE')).pk,
        income.pk, 'income creation intent replay')
    refs.update(salary=salary.pk, expense=expense.pk, income=income.pk)
    refs['financial_retries'] = {
        'salary': {'operation_id': code('SALARY-CREATE'), 'payload': {
            'employee_id': owner.pk, 'amount': '100.00', 'currency': currency,
            'period_year': 2026, 'period_month': 9, 'notes': salary_payload['notes']}},
        'income': {'operation_id': code('INCOME-CREATE'), 'payload': {
            'direction': 'in', 'amount': '200.00', 'currency': currency, 'date': DAY.isoformat(),
            'description': income_payload['description'], 'category': 'customer', 'counterparty_id': customer.pk}},
    }
    return refs


def _fix_synthetic_timestamps():
    """Fixture-only metadata, after genuine commands; no monetary row repair."""
    for model in _tracked_models():
        changes = {}
        for field in model._meta.concrete_fields:
            if isinstance(field, models.DateTimeField):
                if field.name == 'archived_at':
                    model._base_manager.filter(archived_at__isnull=False).update(archived_at=ARCHIVED)
                elif field.name in ('expires_at', 'expire_date'):
                    changes[field.name] = EXPIRY
                else:
                    # Preserve nullable NULL markers; set only existing dates.
                    model._base_manager.filter(**{field.name + '__isnull': False}).update(**{field.name: STAMP})
        if changes:
            model._base_manager.all().update(**changes)
    for audit in AuditEvent.objects.filter(action__endswith='.archive'):
        payload = deepcopy(audit.payload)
        payload['after']['archived_at'] = ARCHIVED.isoformat()
        AuditEvent.objects.filter(pk=audit.pk).update(payload=payload)


def populate():
    _safe_runtime()
    occupied = [model._meta.label_lower for model in _tracked_models() if model._base_manager.exists()]
    _check(not occupied, 'refuse nonempty business/auth/session tables: ' + ', '.join(occupied))
    media = Path(settings.MEDIA_ROOT).resolve()
    _check(not media.exists() or not any(media.iterdir()), 'refuse nonempty synthetic media directory')
    expected = {'format': FORMAT, 'currencies': {}, 'origin': {
        'backend': connection.vendor, 'database': str(connection.settings_dict['NAME']),
        'media_root': str(media),
    }}
    with transaction.atomic():
        Configuration.objects.create(key='dataset', value={'as_of': DAY.isoformat(), 'synthetic': True,
                                                          'purpose': 'A07 typed transfer fixture'})
        client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        user = login_test_client(client)
        expected['user_id'] = user.pk
        expected['group_id'] = user.groups.get(name='ceo').pk
        expected['session_key'] = client.session.session_key
        expected['documents'] = _documents(client)
        for currency in CURRENCIES:
            expected['currencies'][currency] = _currency_fixture(currency, user, client, completed_http=currency == 'EUR')
        expected['completed_proposal'] = expected['currencies']['EUR']['completed_proposal']
        chat = ChatMessage.objects.create(user=user, visibility_role='ceo', role='user',
            content='Синтетичний архівний діалог із технічним файлом · ЇЄҐ 🙂')
        raw = b'\x00\xff\xfe' + bytes(range(256)) + 'Синтетичний файл · ЇЄҐ 🙂'.encode()
        attached = ChatFile(chat_message=chat, original_name='Технічний_файл_ЇЄҐ.bin',
                            mime_type='application/octet-stream', size=len(raw), parsed_text='')
        attached.file.save('a07_fixture_bytes.bin', ContentFile(raw), save=True)
        response = client.delete('/api/chat/history/',
            HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        _eq(response.status_code, 200, 'archive chat via genuine HTTP')
        _eq(response.json()['archived_messages'], 1, 'archive exactly own synthetic message')
        expected['chat'] = {'message_id': chat.pk, 'file_id': attached.pk, 'relative_path': attached.file.name,
            'original_name': attached.original_name, 'content': _encode(raw)}
        _fix_synthetic_timestamps()
        po = expected['currencies']['EUR']['purchase']
        pending_payload = {'action': 'erp_postpone', 'purchase_id': po, 'due_date': '2026-12-01',
                           'reason': 'Невиконане синтетичне погодження для перенесення'}
        before = Purchase.objects.get(pk=po).due_date
        pending = _post(client, '/api/erp/preview/', pending_payload)
        _eq(Purchase.objects.get(pk=po).due_date, before, 'pending preview changed purchase')
        ActionProposal.objects.filter(pk=pending['id']).update(created_at=STAMP + timedelta(minutes=10), expires_at=EXPIRY)
        expected['pending_proposal'] = pending['id']
        expected['snapshot'] = _snapshot()
        result = verify_facts(expected)
        expected['facts'] = result['facts']
    return expected


def _movement(lot, kind, quantity, cost, *, line=None, production=None, purchase=None):
    row = lot.movements.get(kind=kind)
    _eq((row.quantity, row.cost, row.line_id, row.production_id, row.purchase_id),
        (D(quantity), D(cost), line, production, purchase), f'lot {lot.pk} {kind} movement source')


def verify_facts(expected):
    _safe_runtime()
    _eq(expected.get('format'), FORMAT, 'fixture manifest version')
    _eq(set(expected['currencies']), set(CURRENCIES), 'currencies separated')
    actual = _snapshot()
    _eq(set(actual), set(expected['snapshot']), 'tracked model set')
    for label, before in expected['snapshot'].items():
        _eq(actual[label]['count'], before['count'], label + ' exact row count')
        _eq(actual[label]['sha256'], before['sha256'], label + ' exact rows/PK/FK/typed-value SHA')
        _eq(actual[label]['rows'], before['rows'], label + ' exact rows/PK/FK/typed values')
    _eq(Document.objects.count(), 3, 'document row count')
    _eq(set(Document.objects.values_list('pk', flat=True)), {7, 1001, 90001}, 'sparse Document IDs')
    _eq(newest('A07-SPEC').pk, 1001, 'latest specification B')
    for ref in expected['documents'].values():
        document = Document.objects.get(pk=ref['id'])
        _eq((document.code, document.revision, document.status), (ref['code'], ref['revision'], 'approved'), 'document identity')
        _eq(_encode(document.content), ref['bytes'], 'exact Document bytes/base64/SHA')
        _eq(document.checksum, ref['bytes']['sha256'], 'declared fixture Document checksum')
    user = get_user_model().objects.get(pk=expected['user_id'])
    _eq(list(user.groups.values_list('pk', 'name')), [(expected['group_id'], 'ceo')], 'real actor/group IDs')
    completed = ActionProposal.objects.get(pk=expected['completed_proposal'])
    pending = ActionProposal.objects.get(pk=expected['pending_proposal'])
    _eq(ActionProposal.objects.count(), 2, 'one completed and one pending proposal')
    _eq((completed.user_id, completed.session_key, completed.role),
        (user.pk, expected['session_key'], 'ceo'), 'completed proposal owner/session')
    _eq(completed.receipt['state'], 'succeeded', 'completed receipt state')
    _eq(completed.receipt['order_id'], expected['currencies']['EUR']['order'], 'receipt points to existing EUR order')
    completed_event = Event.objects.get(pk=completed.receipt['erp_event_id'])
    _eq(completed_event.result['order_id'], completed.receipt['order_id'], 'Event receipt source preserved')
    _eq((pending.user_id, pending.session_key, pending.role, pending.receipt),
        (user.pk, expected['session_key'], 'ceo', None), 'pending proposal stays unexecuted')
    _eq(pending.fingerprint, service.fingerprint(), 'pending fingerprint matches transferred sources')
    _eq(pending.payload['due_date'], '2026-12-01', 'pending command preserved')
    facts = {}
    for currency, refs in expected['currencies'].items():
        material = Item.objects.get(pk=refs['raw_item'])
        finished = Item.objects.get(pk=refs['finished_item'])
        _eq(material.currency, currency, 'material currency')
        _eq(finished.currency, currency, 'finished currency')
        _eq(finished.bom, [{'item_id': material.pk, 'quantity': '1.000'}], 'BOM frozen component ID/quantity')
        _eq(service.accepted_documents(material, {'cert': 1001}), [], 'latest approved document admits material')
        _eq(service.accepted_documents(material, {'cert': 7}), ['cert'], 'older approved version is not current admission')
        raw = Lot.objects.get(pk=refs['raw_lot'])
        output = Lot.objects.get(pk=refs['output_lot'])
        returned = Lot.objects.get(pk=refs['returned_lot'])
        receipt = Lot.objects.get(pk=refs['receipt_lot'])
        lots = (raw, output, returned, receipt)
        _eq(Lot.objects.filter(currency=currency).count(), 4, 'exact four lots per currency')
        specifications = (
            (raw, material.pk, refs['location_production'], '6.000', '2.00', 'approved'),
            (output, finished.pk, refs['location_stock'], '1.000', '3.00', 'approved'),
            (returned, finished.pk, refs['location_stock'], '1.000', '3.00', 'blocked'),
            (receipt, material.pk, refs['location_stock'], '7.000', '3.00', 'pending'),
        )
        for lot, item_id, location_id, qty, cost, quality in specifications:
            _eq((lot.item_id, lot.location_id, lot.quantity, lot.unit_cost, lot.quality, lot.currency, lot.revision),
                (item_id, location_id, D(qty), D(cost), quality, currency, 'B'), f'lot {lot.pk} exact stock/location')
            _eq(lot.documents, {'cert': 1001}, 'lot latest document FK in JSON')
            _eq(sum((m.quantity for m in lot.movements.all()), D(0)), lot.quantity, 'lot movement ledger')
            held = sum((r.quantity for r in lot.reservations.all()), D(0))
            _check(D(0) <= held <= lot.quantity, 'reserved amount bounded by physical stock')
        _movement(raw, 'opening', '10', '20')
        _movement(raw, 'consume', '-4', '8', production=refs['job'])
        _movement(output, 'production', '4', '12', production=refs['job'])
        _movement(output, 'shipment', '-3', '9', line=refs['line'])
        _movement(returned, 'return', '1', '3', line=refs['line'])
        _movement(receipt, 'receipt', '7', '21', purchase=refs['purchase'])
        _eq(Movement.objects.filter(lot__currency=currency).count(), 6, 'six immutable movement sources')
        _eq(returned.movements.get().reference, output.code, 'return references original output lot')
        _eq([Reservation.objects.get(pk=pk).quantity for pk in refs['reserve_material_ids']],
            [D('1.000'), D('5.000')], 'two original reservations survive partial consumption')
        _eq(Reservation.objects.get(pk=refs['reserve_sales']).quantity, D('0.000'), 'released sale reservation preserved')
        _eq(Reservation.objects.filter(lot__currency=currency).count(), 3, 'reservation IDs preserved')
        job = Production.objects.get(pk=refs['job'])
        _eq((job.quantity, job.produced, job.actual_cost, job.planned_cost, job.status, job.location_id, job.owner_id),
            (D('10.000'), D('4.000'), D('12.00'), D('30.00'), 'running', refs['location_production'], refs['employee']),
            'partial production exact cost/state')
        _eq(job.bom, finished.bom, 'production frozen BOM')
        _eq(job.entries.get().result, 'done', 'actual operator completion retained')
        order = SalesOrder.objects.get(pk=refs['order'])
        line = SalesLine.objects.get(pk=refs['line'])
        _eq((order.customer_id, order.owner_id, order.currency, order.status),
            (refs['customer'], refs['employee'], currency, 'confirmed'), 'sales source FKs')
        _eq((line.order_id, line.item_id, line.quantity, line.shipped, line.invoiced, line.price),
            (order.pk, finished.pk, D('3.000'), D('3.000'), D('3.000'), D('5.00')), 'shipment/invoice history unchanged by return')
        invoice = Invoice.objects.get(pk=refs['invoice'])
        _eq((invoice.amount, invoice.paid, invoice.currency, invoice.customer_id),
            (D('15.00'), D('5.00'), currency, refs['customer']), 'invoice amount/payment/source')
        link = InvoiceLink.objects.get(invoice=invoice)
        _eq(link.order_id, order.pk, 'InvoiceLink order FK')
        _eq(link.lines, [{'line_id': line.pk, 'quantity': '3.000', 'price': '5.00'}], 'InvoiceLink typed quantities')
        payment = Event.objects.get(pk=refs['payment_event'])
        _eq((payment.action, payment.payload['invoice_id'], payment.payload['amount']),
            ('erp_payment', invoice.pk, '5.00'), 'payment Event source/reference')
        _eq(Event.objects.filter(action='erp_payment', payload__reference=payment.payload['reference']).count(), 1,
            'one payment reference')
        po = Purchase.objects.get(pk=refs['purchase'])
        _eq((po.quantity, po.received, po.price, po.extras, po.currency, po.status, po.item_id, po.supplier_id, po.due_date),
            (D('10.000'), D('7.000'), D('2.00'), D('10.00'), currency, 'partial', material.pk,
             refs['supplier'], date(2026, 10, 1)), 'purchase/receipt sources and unexecuted postpone')
        salary = Salary.objects.get(pk=refs['salary'])
        expense = Transaction.objects.get(pk=refs['expense'])
        income = Transaction.objects.get(pk=refs['income'])
        _eq((salary.employee_id, salary.amount, salary.currency, salary.status, salary.payment_date, salary.transaction_id),
            (refs['employee'], D('100.00'), currency, 'paid', DAY, expense.pk), 'archived salary exact expense source')
        _eq((expense.amount, expense.currency, expense.direction, expense.category, expense.date),
            (D('100.00'), currency, 'out', 'salary', DAY), 'single paid salary expense')
        _eq((income.amount, income.currency, income.direction, income.counterparty_id),
            (D('200.00'), currency, 'in', refs['customer']), 'independent manual income')
        _eq((salary.archived_at, expense.archived_at, income.archived_at), (ARCHIVED, ARCHIVED, None),
            'archive markers preserved without filtering ledger')
        _eq(Transaction.objects.filter(currency=currency).count(), 2, 'ERP payment must not duplicate financial transactions')
        _eq(Salary.objects.filter(currency=currency).count(), 1, 'salary source count')
        _eq(FinancialIntent.objects.filter(salary=salary, transaction__isnull=True).count(), 1, 'salary creation intent source')
        _eq(FinancialIntent.objects.filter(transaction=income, salary__isnull=True).count(), 1, 'income creation intent source')
        raw_qty = sum((lot.quantity for lot in Lot.objects.filter(item=material)), D(0))
        finished_qty = sum((lot.quantity for lot in Lot.objects.filter(item=finished)), D(0))
        stock_value = sum((lot.quantity * lot.unit_cost for lot in lots), D(0))
        total_in = sum((row.amount for row in Transaction.objects.filter(currency=currency, direction='in')), D(0))
        total_out = sum((row.amount for row in Transaction.objects.filter(currency=currency, direction='out')), D(0))
        _eq((raw_qty, finished_qty, stock_value, total_in, total_out, total_in - total_out),
            (D('13.000'), D('2.000'), D('39.00'), D('200.00'), D('100.00'), D('100.00')), 'independent totals per currency')
        facts[currency] = {'raw_quantity': format(raw_qty, '.3f'), 'finished_quantity': format(finished_qty, '.3f'),
            'stock_value': format(stock_value, '.2f'), 'production_actual': format(job.actual_cost, '.2f'),
            'invoice_amount': format(invoice.amount, '.2f'), 'invoice_paid': format(invoice.paid, '.2f'),
            'invoice_open': format(invoice.amount - invoice.paid, '.2f'),
            'finance_in': format(total_in, '.2f'), 'finance_out': format(total_out, '.2f'),
            'finance_net': format(total_in - total_out, '.2f')}
    _eq(FinancialIntent.objects.count(), 6, 'exact durable creation intents')
    _eq(Event.objects.count(), 66, 'only the 22 real ERP commands in each currency produced events')
    chat_ref = expected['chat']
    chat = ChatMessage.objects.get(pk=chat_ref['message_id'])
    attached = ChatFile.objects.get(pk=chat_ref['file_id'])
    _eq((chat.user_id, chat.visibility_role, chat.archived_at), (user.pk, 'ceo', ARCHIVED), 'archived chat owner/role/time')
    _eq((attached.chat_message_id, attached.original_name, attached.file.name, attached.size),
        (chat.pk, chat_ref['original_name'], chat_ref['relative_path'], chat_ref['content']['size']), 'ChatFile FK/name/size')
    relative = Path(attached.file.name)
    _check(not relative.is_absolute() and '..' not in relative.parts, 'relative test file path required')
    path = (Path(settings.MEDIA_ROOT) / relative).resolve()
    _check(path.is_relative_to(Path(settings.MEDIA_ROOT).resolve()), 'test file escaped MEDIA_ROOT')
    _eq(_encode(path.read_bytes()), chat_ref['content'], 'exact archived file bytes/base64/SHA')
    _eq((ChatMessage.objects.count(), ChatFile.objects.count()), (1, 1), 'archive preserved chat and file IDs')
    if 'facts' in expected:
        _eq(facts, expected['facts'], 'source/target material facts')
    return {'status': 'passed', 'format': FORMAT, 'facts': facts,
            'model_counts': {label: data['count'] for label, data in actual.items()},
            'rows_sha256': _digest(actual), 'documents': expected['documents'], 'chat_file': chat_ref['content']}


def verify_replays(expected):
    """Actual commands, ONLY on a derived disposable proof copy.

    Caller must copy DB and media, configure that copy, and explicitly set
    BOS_A07_PROOF_COPY=1. Never use this on the source or accepted imported DB.
    The marker attests a derived proof copy; the origin guards also reject the
    source even if the marker was set accidentally. The caller owns isolation
    of the accepted imported target, whose identity is not stored in source.
    """
    _check(os.environ.get('BOS_A07_PROOF_COPY') == '1', 'replay needs explicit derived proof-copy marker')
    _safe_runtime()
    origin = expected.get('origin', {})
    _check(origin.get('database') and origin.get('media_root'), 'source provenance required for replay guard')
    configured = str(connection.settings_dict['NAME'])
    if connection.vendor == origin.get('backend'):
        if connection.vendor == 'sqlite':
            _check(Path(configured).resolve() != Path(origin['database']).resolve(), 'replay on original source refused')
        else:
            _check(configured != origin['database'], 'replay on original source refused')
    _check(Path(settings.MEDIA_ROOT).resolve() != Path(origin['media_root']).resolve(),
           'replay requires derived media copy')
    verification = verify_facts(expected)
    before = _snapshot()
    client = Client(enforce_csrf_checks=True, raise_request_exception=False)
    client.cookies[settings.SESSION_COOKIE_NAME] = expected['session_key']
    csrf = client.get('/api/auth/csrf/')
    _eq(csrf.status_code, 200, 'HTTP CSRF endpoint on imported proof copy')
    _eq(csrf.json().get('authenticated'), True, 'preserved session must authenticate the real imported user')
    _check(settings.CSRF_COOKIE_NAME in client.cookies, 'real HTTP CSRF cookie required')
    stored_receipt = deepcopy(ActionProposal.objects.get(pk=expected['completed_proposal']).receipt)
    response = _post(client, '/api/operations/confirm/', {
        'proposal_id': expected['completed_proposal'], 'confirmed': True})
    _eq(response, stored_receipt, 'imported completed HTTP receipt replay')
    user = get_user_model().objects.get(pk=expected['user_id'])
    replays = {}
    for currency, refs in expected['currencies'].items():
        salary = Salary.objects.get(pk=refs['salary'])
        paid_salary, expense = salary.mark_paid(DAY)
        _eq((paid_salary.pk, expense.pk), (refs['salary'], refs['expense']),
            'imported archived Salary.mark_paid must reuse original expense')
        keys = refs['financial_retries']
        salary_retry = save_salary(changes=deepcopy(keys['salary']['payload']), actor=user,
                                  operation_id=keys['salary']['operation_id'])
        income_retry = save_transaction(changes=deepcopy(keys['income']['payload']), actor=user,
                                       operation_id=keys['income']['operation_id'])
        _eq((salary_retry.pk, income_retry.pk), (refs['salary'], refs['income']),
            'imported financial keys must return original source IDs')
        _eq(Transaction.objects.filter(currency=currency, category='salary').count(), 1,
            'no second salary expense after import replays')
        replays[currency] = {'salary_id': salary_retry.pk, 'expense_id': expense.pk,
                            'income_id': income_retry.pk, 'same_sources': True}
    expected_after = _with_mutex_increment(before, 1)
    after = _snapshot()
    for label in before:
        _eq(after[label], expected_after[label], 'replay changed exact source/receipt/ID rows beyond mutex: ' + label)
    post_manifest = deepcopy(expected)
    post_manifest['snapshot'] = expected_after
    post = verify_facts(post_manifest)
    _eq(post['facts'], verification['facts'], 'replay changed material or monetary facts')
    return {'status': 'passed', 'completed_proposal_id': expected['completed_proposal'],
            'http_receipt_equal': True, 'mutex_increment': 1,
            'financial_replays': replays, 'facts': post['facts'], 'rows_sha256': post['rows_sha256']}
