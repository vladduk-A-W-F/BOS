"""Synthetic network fixtures in the ordinary ERP, never an alternate ledger.

This trusted management command is deliberately separate from user-facing writes.
It creates only a fresh demo business database; it never resets existing rows.
"""
from datetime import date
from decimal import Decimal as D
import hashlib

from django.apps import apps
from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection, transaction

from branches.models import Branch
from employees.models import Employee
from finance.models import Counterparty
from operations.models import Configuration, Document, Invoice, ProcurementRequest, SupplierQuote
from operations.private_storage import private_document_storage, legacy_blob_usage
from tasks.models import Task
from .models import (
    Item, Location, Lot, SalesOrder, SalesLine, Purchase, Production,
    Movement, Inspection, Reservation, InvoiceLink, OperatorEntry, Event,
    StockTransfer, PaymentRetention,
)
from .service import dispatch, write_lock


VERSION = '1.0'
MARKER = 'network_demo_seed'
AS_OF = '2026-09-21'
DATASETS = {
    'workday': 'Робочий день мережі',
    'disruption': 'Збої постачання',
    'collections': 'Грошовий потік',
}
# City-centre reference coordinates (GeoNames). These are synthetic locations,
# not real warehouse addresses or a representation of transport availability.
BRANCHES = (
    ('KYI', 'Київ', 'Київська філія', 50.45466, 30.52380),
    ('LVI', 'Львів', 'Львівська філія', 49.83826, 24.02324),
    ('ODE', 'Одеса', 'Одеська філія', 46.48572, 30.74383),
    ('DNI', 'Дніпро', 'Дніпровська філія', 48.46664, 35.04066),
    ('KHA', 'Харків', 'Харківська філія', 49.98177, 36.25475),
    ('VIN', 'Вінниця', 'Вінницька філія', 49.23220, 28.46871),
    ('KHM', 'Хмельницький', 'Хмельницька філія', 49.41835, 26.97936),
)
# Fresh training prices in UAH, not a conversion of an EUR dataset.
PRODUCTS = (
    ('BLANK', 'Заготовка валу С45', 'шт.', 'material', '2400.00', '3300.00'),
    ('BEARING', 'Підшипник 6205', 'шт.', 'component', '480.00', '690.00'),
    ('SEAL', 'Комплект ущільнень', 'компл.', 'component', '260.00', '410.00'),
    ('VALVE', 'Клапан промисловий DN25', 'шт.', 'product', '1750.00', '2450.00'),
    ('ASSEMBLY', 'Вузол валу в зборі', 'шт.', 'product', '3620.00', '5100.00'),
)


def _existing(dataset):
    marker = Configuration.objects.filter(key=MARKER).first()
    if marker is None:
        return None
    receipt = marker.value
    if (not isinstance(receipt, dict) or receipt.get('version') != VERSION
            or receipt.get('synthetic') is not True):
        raise CommandError('Невідома квитанція навчальної мережі. Автоматичних змін немає.')
    if receipt.get('dataset') != dataset:
        raise CommandError('Інший набір потребує окремої порожньої демобази. Перезаписування заборонене.')
    # Do not recreate missing records or reset later user operations.
    return {**receipt, 'created': False}


def _assert_empty_business():
    for model in apps.get_models():
        if model._meta.app_label not in {'erp', 'operations', 'finance', 'tasks', 'employees', 'branches', 'ai_assistant'}:
            continue
        if model is Configuration:
            if model.objects.exclude(key='erp_write').exists():
                raise CommandError('База вже налаштована або містить демодані. Потрібна окрема порожня демобаза.')
            continue
        if model._meta.label_lower == 'operations.loginattempt':
            continue  # Login throttling is not business data.
        if model._base_manager.exists():
            raise CommandError('База містить бізнес-записи (' + model._meta.label + '). Змішування даних заборонене.')


def seed_network_demo(dataset='workday'):
    """All database rows commit together; only owned new files may be cleaned."""
    if getattr(settings, 'BOS_DATA_MODE', None) != 'demo':
        raise CommandError('Навчальна мережа дозволена лише за BOS_DATA_MODE=demo.')
    if dataset not in DATASETS:
        raise CommandError('Невідомий набір. Доступні workday, disruption, collections.')
    if connection.in_atomic_block:
        raise CommandError('Створення навчальної мережі потребує власної зовнішньої транзакції.')
    existing = _existing(dataset)
    if existing is not None:
        return existing
    pending_files = []
    committed = False

    def finalize():
        nonlocal committed
        committed = True
        for receipt in pending_files:
            private_document_storage.finalize(receipt)

    try:
        with transaction.atomic(durable=True):
            write_lock()
            existing = _existing(dataset)
            if existing is not None:
                return existing
            _assert_empty_business()
            result = _populate(dataset, pending_files)
            transaction.on_commit(finalize)
        return {**result, 'created': True}
    except BaseException:
        if not committed:
            for receipt in reversed(pending_files):
                private_document_storage.discard_new(receipt)
        raise


def _populate(dataset, pending_files):
    def act(action, **data):
        return dispatch({'action': 'erp_' + action, **data}, 'ceo')

    def document(code, title, text):
        raw = text.encode('utf-8')
        checksum = hashlib.sha256(raw).hexdigest()
        receipt = private_document_storage.save_verified(raw, checksum, legacy_blob_bytes=legacy_blob_usage)
        pending_files.append(receipt)
        return Document.objects.create(
            code=code, revision='A', title=title, filename=code + '.txt',
            access_level='operational', content=b'', original_file=receipt.name,
            size=receipt.size, text=text, sections=[{'source': 'Навчальний документ', 'text': text}],
            status='approved', checksum=checksum,
        )

    # Seed the trace at a historical business date, then expose the final snapshot.
    # Normal source validation remains enabled, including non-past PO agreement.
    clock = Configuration.objects.create(key='dataset', value={
        'synthetic': True, 'as_of': '2026-09-14', 'source': 'BoS Network Demo', 'dataset': dataset,
    })
    Configuration.objects.create(key='organization', value={
        'name': 'Вектор Індустрія · навчальні дані',
        'description': 'Вигадана мережа промислових поставок і складання',
        'industry': 'Промислові поставки', 'timezone': 'Europe/Kyiv', 'locale': 'uk-UA',
        'currency': 'UAH', 'synthetic': True,
    })
    spec = document('NET-SPEC', 'Навчальна специфікація вузла валу',
        'СИНТЕТИЧНІ ДАНІ. Вузол: 1 заготовка С45, 2 підшипники 6205, 1 комплект ущільнень. '
        'Версія A. Маршрут: складання, контроль, пакування. Матеріальна собівартість 3620,00 грн. '
        'Без ПДВ, мита, валютообміну та окремої вартості праці. Не для реального виробництва.')
    cert = document('NET-CERT', 'Навчальний сертифікат комплектності',
        'СИНТЕТИЧНІ ДАНІ. Навчальний документ комплектності партій NET, версія A. '
        'Не є сертифікатом виробника. Застосовується лише до навчальних залишків мережі BoS.')
    cash_source = document('NET-CASH', 'Навчальний зріз коштів мережі',
        'СИНТЕТИЧНІ ДАНІ. Зріз на 21.09.2026: 180000,00 грн. Це окремий навчальний залишок, '
        'а не банківська виписка. BoS не підключений до банку; локальні записи оплат не змінюють цей зріз автоматично.')
    Configuration.objects.create(key='cash', value={
        'amount': '180000.00', 'currency': 'UAH', 'source': cash_source.code,
        'as_of': AS_OF, 'synthetic': True, 'kind': 'manual_snapshot',
    })
    docs = {'certificate': cert.pk}
    branches, locations, managers, inspectors, customers, suppliers, items, lots = ({ } for _ in range(8))
    for index, (code, city, name, lat, lng) in enumerate(BRANCHES):
        branch = Branch.objects.create(code='NET-' + code, name=name + ' · навчальна', short_name=city,
            type='headquarters' if code == 'KYI' else 'regional', lat=lat, lng=lng, employee_count=2,
            status='yellow' if dataset == 'disruption' else 'green')
        branches[code] = branch
        managers[code] = Employee.objects.create(full_name='Навчальний менеджер · ' + city,
            role='Менеджер мережі', department='Продажі', branch=branch)
        inspectors[code] = Employee.objects.create(full_name='Навчальний інженер · ' + city,
            role='Інженер якості та виробництва', department='Якість', branch=branch)
        for suffix, kind, label in [('WH', 'warehouse', 'центральний склад'),
                                     ('SV', 'production', 'сервісно-виробнича точка')]:
            # Both share the city centre: there are no invented precise addresses.
            locations[code + '-' + suffix] = act('location', code='NET-' + code + '-' + suffix,
                name=city + ' · ' + label, kind=kind, branch_id=branch.pk, lat=lat, lng=lng,
                address='Навчальна точка; координати центру міста, не адреса об’єкта')['location_id']
        suppliers[code] = Counterparty.objects.create(name='Навчальний постачальник · ' + city,
            type='supplier', notes='Вигаданий контрагент, лише для навчання. Валюта UAH.')
        customers[code] = Counterparty.objects.create(name='Навчальний клієнт · ' + city,
            type='customer', notes='Вигаданий контрагент, лише для навчання. Валюта UAH.')
    for code, name, unit, kind, cost, price in PRODUCTS:
        payload = dict(code='NET-' + code, name=name, unit=unit, kind=kind,
            method='make' if code == 'ASSEMBLY' else 'buy', revision='A', currency='UAH',
            required_documents=['certificate'], minimum='10', lead_days=7, planned_cost=cost,
            document_id=spec.pk)
        if code == 'ASSEMBLY':
            payload.update(bom=[{'item_id': items[key], 'quantity': str(qty)}
                for key, qty in [('BLANK', 1), ('BEARING', 2), ('SEAL', 1)]],
                routing=[{'name': name, 'instruction': 'Навчальна операція за NET-SPEC A', 'days': 1}
                    for name in ['Складання', 'Контроль', 'Пакування']])
        items[code] = act('item', **payload)['item_id']

    def open_lot(code, key, location, qty, cost, inspector, blocked=False):
        lot_id = act('opening', code=code, item_id=items[key], location_id=location,
            quantity=str(qty), unit_cost=cost, currency='UAH', revision='A',
            documents={} if blocked else docs, reason='Синтетичний початковий залишок мережі')['lot_id']
        act('quality', lot_id=lot_id, result='blocked' if blocked else 'approved', inspector_id=inspector.pk,
            note='Синтетичний карантин: потрібен сертифікат NET-CERT A' if blocked else 'Навчальна перевірка за NET-CERT A')
        return lot_id

    for index, (code, city, *_rest) in enumerate(BRANCHES):
        for product_index, (key, _name, _unit, _kind, cost, _price) in enumerate(PRODUCTS):
            for suffix in ('WH', 'SV'):
                qty = (52 if suffix == 'WH' else 24) + index * 3 + product_index * 4
                hold = (10 if dataset == 'disruption' else 4) if key == 'VALVE' and suffix == 'WH' else 0
                if key == 'ASSEMBLY' and suffix == 'WH':
                    qty += 18  # Seed gross stock before the three traced historical shipments.
                blocked = dataset == 'disruption' and code == 'DNI' and suffix == 'SV' and key == 'SEAL'
                lots[(code, suffix, key)] = open_lot('NET-LOT-' + code + '-' + suffix + '-' + key,
                    key, locations[code + '-' + suffix], qty - hold, cost, inspectors[code], blocked)
                if hold:
                    held = open_lot('NET-HOLD-' + code, key, locations[code + '-WH'], hold, cost, inspectors[code], True)
                    Task.objects.create(title='Отримати сертифікат і перевірити партію NET-HOLD-' + code,
                        priority='high', status='active', assignee=inspectors[code].full_name,
                        assignee_employee=inspectors[code], branch=branches[code], deadline=AS_OF, category='Якість',
                        result=None)

    def sale(code, branch, key, qty, price, due='2026-09-25', customer=None, destination='', suffix='WH'):
        result = act('order', code=code, customer_id=(customer or customers[branch]).pk,
            owner_id=managers[branch].pk, due_date=due, currency='UAH',
            fulfillment_location_id=locations[branch + '-' + suffix], destination_country=destination,
            notes='Синтетичний навчальний продаж; без ПДВ. Не виконує банківських або митних дій.',
            lines=[{'item_id': items[key], 'quantity': str(qty), 'price': str(price)}])
        act('confirm_order', order_id=result['order_id'])
        return SalesLine.objects.get(order_id=result['order_id'])

    def procurement_source(code, branch, key, qty, price, supplier, with_quote=True):
        """Synthetic approved RFQ/quote sources exist before the ordinary PO writer."""
        item = Item.objects.get(pk=items[key])
        requirement = document(code + '-REQ-DOC', 'Навчальна вимога ' + code,
            f'СИНТЕТИЧНІ ДАНІ. Вимога {code}: {qty} {item.unit} {item.code}, версія A. '
            'Потрібно до 30.09.2026. Валюта UAH. Сертифікат матеріалу і комплектність обов’язкові. Без ПДВ.')
        request = ProcurementRequest.objects.create(code=code, part=item.code, revision='A',
            quantity=qty, unit=item.unit, currency='UAH', required_by='2026-09-30',
            owner=managers[branch], document=requirement,
            details={'project': 'Синтетична мережа BoS', 'material': 'Навчальна номенклатура',
                     'quality': 'Сертифікат матеріалу та комплектність', 'tax_basis': 'Без ПДВ'})
        if not with_quote:
            return request, None
        quote_doc = document(code + '-QUOTE-DOC', 'Навчальна пропозиція ' + code,
            f'СИНТЕТИЧНІ ДАНІ. Пропозиція для {code}: {qty} {item.unit}, ціна {price} грн за одиницю. '
            'Валюта UAH; версія A; MOQ 1; строк 0 тижнів; чинна до 30.10.2026; '
            'сертифікат і покриття включені. Підготовка, доставка, інструмент і спеціальні процеси: 0,00 грн. Без ПДВ.')
        quote = SupplierQuote.objects.create(code=code + '-Q', request=request, supplier=supplier, document=quote_doc,
            terms={'unit_price': price, 'setup': '0.00', 'shipping': '0.00', 'tooling': '0.00',
                   'special_processes': '0.00', 'currency': 'UAH', 'revision': 'A', 'lead_weeks': 0,
                   'valid_until': '2026-10-30', 'moq': 1, 'coating_included': True, 'material_certificate': True,
                   'tax_basis': 'excluding_VAT'})
        return request, quote

    # Unallocated requests remain explicitly without a logistics point until a
    # real purchase is agreed. The owner's branch is not a guessed destination.
    procurement_source('NET-RFQ-SEARCH', 'KYI', 'VALVE', 12, '1750.00', suppliers['KYI'], with_quote=False)
    procurement_source('NET-RFQ-COMPARE', 'LVI', 'BLANK', 15, '2400.00', suppliers['LVI'])

    for index, (code, city, *_rest) in enumerate(BRANCHES):
        request, quote = procurement_source('NET-RFQ-' + code, code, 'BEARING', 20 + index * 2, '480.00', suppliers[code])
        purchase = act('purchase', code='NET-PO-' + code, item_id=items['BEARING'], supplier_id=suppliers[code].pk,
            quantity=str(20 + index * 2), price='480.00', currency='UAH', revision='A',
            due_date='2026-09-19' if dataset == 'disruption' else '2026-09-23',
            destination_id=locations[code + '-WH'], origin_country='UA',
            request_id=request.pk, quote_id=quote.pk,
            supplier_confirmation='Синтетичне підтвердження навчального постачальника: кількість і дата погоджені')
        if code in ('KYI', 'LVI'):
            received = act('receive', purchase_id=purchase['purchase_id'], code='NET-RCV-' + code,
                location_id=locations[code + '-WH'], quantity='8' if code == 'KYI' else str(20 + index * 2), documents=docs)
            act('quality', lot_id=received['lot_id'], result='approved', inspector_id=inspectors[code].pk,
                note='Синтетична перевірка фактичної навчальної прийомки за NET-CERT A')
        current = sale('NET-SO-' + code, code, 'VALVE', 5 + index, '2450.00', '2026-09-22')
        if index % 2 == 0:
            act('reserve', lot_id=lots[(code, 'WH', 'VALVE')], quantity=str(5 + index), line_id=current.pk)
        for kind in range(3):
            due = ('2026-09-' + str(10 + index).zfill(2)) if dataset == 'collections' else ('2026-09-18' if kind == 2 else '2026-09-25')
            historical = sale('NET-HIST-' + code + '-' + str(kind + 1), code, 'ASSEMBLY', 5 + kind,
                D('5100.00') + D(index * 150 + kind * 200), due)
            act('reserve', lot_id=lots[(code, 'WH', 'ASSEMBLY')], quantity=str(5 + kind), line_id=historical.pk)
            act('ship', line_id=historical.pk, lot_id=lots[(code, 'WH', 'ASSEMBLY')], quantity=str(5 + kind),
                reference='NET-SHIP-' + code + '-' + str(kind + 1))
            result = act('invoice', order_id=historical.order_id, code='NET-INV-' + code + '-' + str(kind + 1), due_date=due)
            amount = D(result['amount'])
            if kind == 0:
                act('hold_payment', invoice_id=result['invoice_id'], amount=str((amount * D('.10')).quantize(D('.01'))),
                    code='NET-RET-' + code, reason='Навчальне договірне утримання 10% до погодження комплекту документів')
            else:
                act('payment', invoice_id=result['invoice_id'], amount=str((amount * (D('.25') if kind == 1 else D('.50'))).quantize(D('.01'))),
                    reference='NET-PAY-' + code + '-' + str(kind + 1))

    for index, (branch, country, country_code) in enumerate([('ODE', 'Польща', 'PL'), ('LVI', 'Чехія', 'CZ'), ('KYI', 'Німеччина', 'DE'), ('DNI', 'Словаччина', 'SK')]):
        supplier = Counterparty.objects.create(name='Навчальний постачальник · ' + country,
            type='supplier', notes='Вигаданий іноземний контрагент. Навчальна ціна UAH, без конвертації та мита.')
        request, quote = procurement_source('NET-RFQ-IMP-' + branch, branch, 'SEAL', 30 + index * 10, '260.00', supplier)
        act('purchase', code='NET-IMP-' + branch, item_id=items['SEAL'], supplier_id=supplier.pk,
            quantity=str(30 + index * 10), price='260.00', currency='UAH', revision='A',
            due_date='2026-09-19' if dataset == 'disruption' else '2026-09-24',
            destination_id=locations[branch + '-WH'], origin_country=country_code,
            request_id=request.pk, quote_id=quote.pk,
            supplier_confirmation='Синтетичне підтвердження іноземного постачальника: кількість і дата погоджені')
    for index, (branch, country, country_code) in enumerate([('KHA', 'Польща', 'PL'), ('VIN', 'Чехія', 'CZ'), ('KHM', 'Словаччина', 'SK')]):
        customer = Counterparty.objects.create(name='Навчальний замовник · ' + country,
            type='customer', notes='Вигаданий іноземний контрагент. Вартість UAH, без податкового розрахунку.')
        sale('NET-EXP-' + branch, branch, 'ASSEMBLY', 3 + index, '5100.00', customer=customer, destination=country_code)

    for branch in ('DNI', 'KHA'):
        line = sale('NET-MO-SO-' + branch, branch, 'ASSEMBLY', 6, '5100.00', suffix='SV')
        result = act('job', code='NET-MO-' + branch, item_id=items['ASSEMBLY'], quantity='6',
            location_id=locations[branch + '-SV'], owner_id=inspectors[branch].pk,
            due_date='2026-09-22', line_id=line.pk)
        for key, quantity in [('BLANK', '6'), ('BEARING', '12'), ('SEAL', '6')]:
            if dataset == 'disruption' and branch == 'DNI' and key == 'SEAL':
                continue
            act('reserve', lot_id=lots[(branch, 'SV', key)], production_id=result['production_id'], quantity=quantity)
        if branch == 'DNI' and dataset != 'disruption':
            act('start', production_id=result['production_id'])
            for operation in ['Складання', 'Контроль', 'Пакування']:
                act('operator', production_id=result['production_id'], operation=operation,
                    operator_id=inspectors[branch].pk, result='done', minutes=30, defects='0',
                    note='Синтетичний журнал виконання; випуск потребує окремого підтвердження')

    in_transit = {'KYI', 'LVI', 'ODE'} if dataset == 'disruption' else {'KYI', 'LVI'}
    for index, (branch, _city, *_rest) in enumerate(BRANCHES):
        destination = BRANCHES[(index + 1) % len(BRANCHES)][0]
        result = act('transfer_dispatch', lot_id=lots[(branch, 'WH', 'BEARING')], quantity=str(8 + index),
            location_id=locations[destination + '-SV'], code='NET-TRF-' + branch,
            reason='Синтетичне міжфіліальне поповнення', due_date='2026-09-20' if dataset == 'disruption' else '2026-09-24')
        if branch not in in_transit:
            received = act('transfer_receive', transfer_id=result['transfer_id'], code='NET-TRF-LOT-' + branch,
                reason='Навчальне підтвердження фактичного приймання')
            act('quality', lot_id=received['lot_id'], result='approved', inspector_id=inspectors[destination].pk,
                note='Синтетичний контроль прийнятого переміщення за NET-CERT A')
    clock.value = {**clock.value, 'as_of': AS_OF}
    clock.save(update_fields=['value'])
    counts = {model._meta.model_name: model.objects.count() for model in (
        Branch, Location, Employee, Counterparty, Document, Item, Lot, SalesOrder, SalesLine,
        Purchase, Production, Reservation, Invoice, InvoiceLink, Movement, Inspection,
        OperatorEntry, StockTransfer, PaymentRetention, Task, Event, ProcurementRequest, SupplierQuote,
    )}
    result = {'version': VERSION, 'synthetic': True, 'dataset': dataset, 'title': DATASETS[dataset],
        'as_of': AS_OF, 'currency': 'UAH', 'counts': counts,
        'source': 'BoS network practice adapted into persisted ERP commands',
        'coordinates': 'GeoNames city centres; https://www.geonames.org/about.html; CC BY 4.0',
        'notice': 'Навчальні дані. Не банківські платежі, митні декларації або реальна логістика.'}
    Configuration.objects.create(key=MARKER, value=result)
    Configuration.objects.create(key='erp_dataset', value={'network_demo': True, 'synthetic': True, 'version': VERSION, 'dataset': dataset})
    return result
