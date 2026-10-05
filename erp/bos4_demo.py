"""BoS 4 demo company through ordinary ERP commands, never an alternate ledger.

Trusted management command for a fresh demo database only (BOS_DATA_MODE=demo).
It never resets or mixes with existing rows. Data sources: erp/bos4_demo_data.py.
"""
from datetime import date, timedelta
from decimal import Decimal as D
import hashlib

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection, transaction

from branches.models import Branch
from employees.models import Employee
from finance.models import Counterparty
from operations.models import Configuration, Document
from operations.private_storage import private_document_storage, legacy_blob_usage
from tasks.models import Task
from . import bos4_demo_aw_v11 as aw
from . import bos4_demo_data as data
from .models import Item, Location, SalesLine
from .network_demo import _assert_empty_business
from .service import dispatch, write_lock


VERSION = '1.0'
# 1.1 = 1.0 plus the AdventureWorks catalog and a large reseller order (erp/bos4_demo_aw_v11.py).
# Only for a new database; an installed 1.0 demo is never upgraded or reseeded in place.
VERSIONS = ('1.0', '1.1')
AW_ORDER_CODE = 'ZM-0150'
AW_CUSTOMER = {'name': 'ТОВ «Склад-Мережа Схід»', 'city': 'Харків'}   # scenario, not AdventureWorks

# What the public first screen says about each case: plain words for a person, no internal record codes.
# Kept in code (not only in the seeded database) so wording fixes reach installed demos without reseeding.
PUBLIC_CASES = [
    {'key': 'components', 'title': 'Комплектуючі для партії меблів',
     'summary': 'Закупівля → приймання → виробництво → відвантаження 120 стелажів. Решта 134 вироби замовлення ще в роботі.',
     'result': {'label': 'Виготовлено й відвантажено', 'value': '120 стелажів СМ-1800'},
     'steps': [
         {'title': 'Замовлення й закупівля', 'text': 'Замовлення на 254 вироби на 1 922 800 грн; під нього закуплено 300 кутників'},
         {'title': 'Приймання й видача в цех', 'text': 'Прийнято 200 + 100 кутників; 480 кутників і решту матеріалів зарезервовано'},
         {'title': 'Виробництво й якість', 'text': '5 операцій завершено; випущено й допущено 120 стелажів СМ-1800'},
         {'title': 'Відвантаження', 'text': '120 стелажів відвантажено з Житомира; решта 134 вироби ще не відвантажена'}]},
    {'key': 'quality', 'title': 'Відвантаження лише допущеної партії',
     'summary': 'Клієнт отримує тільки перевірені шафи; заблокована партія чекає.',
     'result': {'label': 'Відвантажено', 'value': '40 з 50 шаф'},
     'steps': [
         {'title': 'Резерв', 'text': 'Партія від 15.09 у Києві'},
         {'title': 'Контроль якості', 'text': 'Партія від 18.09 заблокована'},
         {'title': 'Відвантаження', 'text': '90 виробів за накладною'},
         {'title': 'Доручення', 'text': 'Перефарбувати 25 шаф'}]},
    {'key': 'payment', 'title': 'Рахунок, оплата й нагадування',
     'summary': 'Часткова оплата не губиться: на решту є відповідальний і строк.',
     'result': {'label': 'Залишок до оплати', 'value': '168 000 грн'},
     'steps': [
         {'title': 'Відвантаження', 'text': '30 верстаків і 20 столів'},
         {'title': 'Рахунок', 'text': '420 000 грн, строк 01.10'},
         {'title': 'Оплата', 'text': '252 000 грн, 60%'},
         {'title': 'Нагадування', 'text': 'Доручення керівнику філії'}]},
]
# Internal records behind each step, used by the signed-in demo; never sent to the public screen.
CASE_REFS = {
    'components': [
        {'order': 'ZM-0141', 'purchase': 'ZK-0311', 'document': 'KM-ZM-0141'},
        {'purchase': 'ZK-0311', 'document': 'KM-CERT-ZK0311-REST'},
        {'production': 'VZ-0141-1', 'lot': 'KM-L-SM-1800-VZ0141', 'document': 'KM-PASS-VZ-0141-1'},
        {'shipment': 'VN-0141-1', 'lot': 'KM-T-SM-1800-VZ0141', 'document': 'KM-VN-0141-1'}],
    'quality': [
        {'order': 'ZM-0144', 'document': 'KM-ZM-0144'},
        {'lot': 'KM-L-SHM-2-0918', 'document': 'KM-QC-SHM-2-0918'},
        {'shipment': 'VN-0144-1', 'document': 'KM-VN-0144-1'},
        {'task': 'Перефарбувати партію ШМ-2', 'document': 'KM-QC-SHM-2-0918'}],
    'payment': [
        {'order': 'ZM-0137', 'document': 'KM-VN-0137-1'},
        {'invoice': 'RF-0137', 'document': 'KM-RF-0137'},
        {'payment': 'PD-5521', 'document': 'KM-PD-5521'},
        {'task': 'Нагадати «Агроснаб Дніпро»', 'document': 'KM-REM-RF-0137'}],
}


def public_cases(stored):
    """The cases for the public screen: current wording from code for this demo's cases, public fields only."""
    by_key = {case['key']: case for case in PUBLIC_CASES}
    out = []
    for case in stored if isinstance(stored, list) else []:
        source = by_key.get(case.get('key')) if isinstance(case, dict) else None
        if source is None:
            continue
        out.append({'key': source['key'], 'title': source['title'], 'summary': source['summary'],
                    'result': source['result'], 'steps': [{'title': s['title'], 'text': s['text']} for s in source['steps']]})
    return out
MARKER = 'bos4_demo_seed'
SEED_DATE = '2026-09-21'
AS_OF = '2026-10-05'
PREFIX = 'KM-'


def _existing(version):
    marker = Configuration.objects.filter(key=MARKER).first()
    if marker is None:
        return None
    receipt = marker.value
    if not isinstance(receipt, dict) or receipt.get('version') not in VERSIONS or receipt.get('synthetic') is not True:
        raise CommandError('Невідома квитанція демо-компанії. Автоматичних змін немає.')
    if receipt['version'] != version:
        raise CommandError(f'У базі вже демо-компанія версії {receipt["version"]}; версію {version} '
                           'створюють лише в новій базі. Автоматичних змін немає.')
    return {**receipt, 'created': False}


def _assert_no_connectors():
    from connectors.models import Connector, ConnectorSnapshot
    if Connector.objects.exists() or ConnectorSnapshot.objects.exists():
        raise CommandError('База містить підключені джерела. Змішування з демо-даними заборонене.')


def seed_bos4_demo(version=VERSION):
    """All rows commit together; only owned new files may be cleaned."""
    if version not in VERSIONS:
        raise CommandError('Невідома версія демо-компанії: ' + str(version))
    if getattr(settings, 'BOS_DATA_MODE', None) != 'demo':
        raise CommandError('Демо-компанія дозволена лише за BOS_DATA_MODE=demo.')
    if connection.in_atomic_block:
        raise CommandError('Створення демо-компанії потребує власної зовнішньої транзакції.')
    existing = _existing(version)
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
            existing = _existing(version)
            if existing is not None:
                return existing
            _assert_empty_business()
            _assert_no_connectors()
            result = _populate(pending_files, version)
            transaction.on_commit(finalize)
        return {**result, 'created': True}
    except BaseException:
        if not committed:
            for receipt in reversed(pending_files):
                private_document_storage.discard_new(receipt)
        raise


def _populate(pending_files, version=VERSION):
    def act(action, **payload):
        return dispatch({'action': 'erp_' + action, **payload}, 'ceo')

    def document(code, title, text):
        text = 'ДЕМО-ДАНІ. ' + text
        raw = text.encode('utf-8')
        checksum = hashlib.sha256(raw).hexdigest()
        receipt = private_document_storage.save_verified(raw, checksum, legacy_blob_bytes=legacy_blob_usage)
        pending_files.append(receipt)
        return Document.objects.create(
            code=code, revision='A', title=title, filename=code + '.txt',
            access_level='operational', content=b'', original_file=receipt.name,
            size=receipt.size, text=text, sections=[{'source': title, 'text': text}],
            status='approved', checksum=checksum,
        )

    clock = Configuration.objects.create(key='dataset', value={
        'synthetic': True, 'as_of': SEED_DATE, 'source': 'BoS 4 demo', 'dataset': 'bos4'})
    Configuration.objects.create(key='organization', value={
        **data.COMPANY, 'timezone': 'Europe/Kyiv', 'locale': 'uk-UA', 'currency': 'UAH', 'synthetic': True})

    branches, people, places, suppliers, customers, items = {}, {}, {}, {}, {}, {}
    for code, kind, branch_type, city, lat, lng in data.BRANCHES:
        branches[code] = Branch.objects.create(
            code=PREFIX + code, name=kind + ' · ' + city, short_name=city, type=branch_type,
            parent=branches.get('KYI'), lat=lat, lng=lng, status='green',
            employee_count=sum(1 for p in data.PEOPLE if p[3] == code))
    for full_name, role, department, branch in data.PEOPLE:
        people[full_name] = Employee.objects.create(
            full_name=full_name, role=role, department=department, branch=branches[branch])
    for key, branch, kind, name in data.LOCATIONS:
        b = branches[branch]
        places[key] = act('location', code=PREFIX + key, name=b.short_name + ' · ' + name, kind=kind,
            branch_id=b.pk, lat=b.lat, lng=b.lng,
            address='Демо-точка; координати центру міста, не адреса об’єкта')['location_id']
    for key, name, source, city, lat, lng in data.SUPPLIERS:
        suppliers[key] = Counterparty.objects.create(name=name, type='supplier', address=city,
            notes='Демо-постачальник. Роль узято з AdventureWorks (' + source + ').')
        # The supplier's own point: the origin of its deliveries on the company map.
        act('location', code=PREFIX + 'SUP-' + key, name=name + ' · ' + city, kind='supplier',
            supplier_id=suppliers[key].pk, lat=lat, lng=lng,
            address='Демо-точка постачальника; координати центру міста, не адреса об’єкта')
    for key, name, city in data.CUSTOMERS:
        customers[key] = Counterparty.objects.create(name=name, type='customer', address=city,
            notes='Демо-клієнт, вигаданий контрагент.')

    sales, quality, store = people['Андрій Мельник'], people['Наталія Ткаченко'], people['Сергій Кравець']
    certificate = document('KM-CERT-0901', 'Сертифікат якості металопрокату',
        'Металопрокат Центр. Залишок металу на складі Житомир станом на 01.09.2026: '
        'кутник, труба профільна, плита, лист. Марка сталі Ст3, відповідність ДСТУ підтверджено.')
    for article, name, unit, supplier, price, minimum, lead, cert in data.MATERIALS:
        items[article] = act('item', code=article, name=name, unit=unit, kind='material', method='buy',
            revision='A', currency='UAH', planned_cost=price, minimum=minimum, lead_days=lead,
            required_documents=['certificate'] if cert else [],
            external_codes={'Артикул AdventureWorks': article})['item_id']
    passports = {}
    for code, name, cost, price, bom in data.PRODUCTS:
        passports[code] = document('KM-PASS-' + code, 'Паспорт виробу ' + name,
            name + '. Специфікація: ' + ', '.join(a + ' × ' + q for a, q in bom.items()) +
            '. Маршрут: ' + ', '.join(step[0] for step in data.ROUTE) + '. Гарантія 24 місяці.')
        items[code] = act('item', code=code, name=name, unit='шт.', kind='product', method='make',
            revision='A', currency='UAH', planned_cost=cost, minimum='5', lead_days=10,
            required_documents=['passport'], document_id=passports[code].pk,
            bom=[{'item_id': items[a], 'quantity': q} for a, q in bom.items()],
            routing=[{'name': n, 'instruction': i, 'days': d} for n, i, d in data.ROUTE])['item_id']
    material_price = {m[0]: m[4] for m in data.MATERIALS}
    product_cost = {p[0]: p[2] for p in data.PRODUCTS}
    product_price = {p[0]: p[3] for p in data.PRODUCTS}

    def stock(code, article, place, qty, blocked=False, note=''):
        cert = any(m[0] == article and m[7] for m in data.MATERIALS)
        docs = {} if blocked else ({'certificate': certificate.pk} if cert else
            ({'passport': passports[article].pk} if article in passports else {}))
        lot = act('opening', code=code, item_id=items[article], location_id=places[place], quantity=str(qty),
            unit_cost=material_price.get(article) or product_cost[article], currency='UAH', revision='A',
            documents=docs, reason='Залишок на початок демо-періоду')['lot_id']
        act('quality', lot_id=lot, result='blocked' if blocked else 'approved', inspector_id=quality.pk,
            note=note or 'Вхідний контроль пройдено')
        return lot

    # Opening balances: metal store and finished goods in Zhytomyr, showroom in Kyiv.
    metal = {a: stock('KM-L-' + a, a, 'ZHY-METAL', q) for a, q in (
        ('MA-7075', 260), ('MB-2024', 180), ('MB-6061', 160), ('MP-2503', 40), ('MT-1000', 30),
        ('MS-6061', 150), ('MS-0253', 90), ('CB-2903', 12000), ('PB-6109', 4000), ('HN-4402', 10000),
        ('HN-5400', 4000), ('LW-4000', 10000), ('FW-1000', 4000), ('LR-2398', 120),
        ('PA-187B', 200), ('PA-529S', 160))}
    finished = {code: stock('KM-L-' + code + '-0901', code, 'ZHY-FG', q) for code, q in (
        ('SV-1500', 30), ('VS-1500', 50), ('SV-1200', 40), ('TI-1', 15))}
    shm2_ok = stock('KM-L-SHM-2-0915', 'SHM-2', 'ZHY-FG', 40)
    shm2_hold = stock('KM-L-SHM-2-0918', 'SHM-2', 'ZHY-FG', 25, blocked=True,
        note='Непрофарбовані зварні шви; паспорт не оформлено. Відвантаження заборонено.')
    kyiv = {code: stock('KM-L-' + code + '-KYI', code, 'KYI-WH', q) for code, q in (('SHM-1', 30), ('TI-1', 25))}

    def order(code, customer, owner, due, place, lines, confirm=True):
        out = act('order', code=code, customer_id=customers[customer].pk, owner_id=people[owner].pk,
            due_date=due, currency='UAH', branch_id=Location.objects.get(pk=places[place]).branch_id,
            fulfillment_location_id=places[place], notes='Демо-замовлення; ціни без ПДВ.',
            lines=[{'item_id': items[c], 'quantity': str(q), 'price': product_price[c]} for c, q in lines])
        if confirm:
            act('confirm_order', order_id=out['order_id'])
        return {line.item.code: line for line in SalesLine.objects.filter(order_id=out['order_id']).select_related('item')}, out['order_id']

    def deliver(code, lot, place, qty, receive=True, due=None):
        sent = act('transfer_dispatch', lot_id=lot, quantity=str(qty), location_id=places[place], code=code,
            reason='Поповнення складу філії з виробництва', **({'due_date': due} if due else {}))
        if not receive:
            return None
        got = act('transfer_receive', transfer_id=sent['transfer_id'], code=code + '-L', reason='Прийнято комірником філії')
        act('quality', lot_id=got['lot_id'], result='approved', inspector_id=quality.pk, note='Комплектність і паспорт перевірено')
        return got['lot_id']

    # Case 1: components for a furniture batch.
    zm141, zm141_id = order('ZM-0141', 'LOGISTIC', 'Андрій Мельник', '2026-10-20', 'ZHY-FG',
        [('SM-1800', 120), ('SM-2000', 80), ('SV-1500', 24), ('SHM-2', 12), ('TI-1', 18)])
    order_doc = document('KM-ZM-0141', 'Замовлення покупця ZM-0141 · Логістик Парк',
        'Облаштування розподільчого центру: стелажі СМ-1800 — 120, СМ-2000 — 80, столи СВ-1500 — 24, '
        'шафи ШМ-2 — 12, тумби ТІ-1 — 18. Сума 1 922 800,00 грн без ПДВ. Строк 20.10.2026.')
    act('link_document', document_id=order_doc.pk, order_id=zm141_id)
    job1 = act('job', code='VZ-0141-1', item_id=items['SM-1800'], quantity='120', location_id=places['ZHY-SHOP'],
        owner_id=people['Ігор Бондар'].pk, due_date='2026-10-12', line_id=zm141['SM-1800'].pk)['production_id']
    job2 = act('job', code='VZ-0141-2', item_id=items['SM-2000'], quantity='80', location_id=places['ZHY-SHOP'],
        owner_id=people['Ігор Бондар'].pk, due_date='2026-10-16', line_id=zm141['SM-2000'].pk)['production_id']
    po_angle = act('purchase', code='ZK-0311', item_id=items['MA-7075'], supplier_id=suppliers['METAL'].pk,
        quantity='300', price=material_price['MA-7075'], currency='UAH', due_date='2026-09-30', revision='A',
        production_id=job1, destination_id=places['ZHY-METAL'], origin_country='UA',
        direct_reason='Дефіцит кутника під стелажі СМ-1800 для замовлення ZM-0141')['purchase_id']
    act('purchase', code='ZK-0312', item_id=items['MS-0253'], supplier_id=suppliers['METAL'].pk,
        quantity='100', price=material_price['MS-0253'], currency='UAH', due_date='2026-10-08', revision='A',
        production_id=job2, destination_id=places['ZHY-METAL'], origin_country='UA',
        direct_reason='Лист 1,0 мм під стелажі СМ-2000 для замовлення ZM-0141')
    act('purchase', code='ZK-0309', item_id=items['PA-529S'], supplier_id=suppliers['PAINT'].pk,
        quantity='120', price=material_price['PA-529S'], currency='UAH', due_date='2026-10-03', revision='A',
        destination_id=places['ZHY-METAL'], origin_country='UA',
        direct_reason='Поповнення сірої фарби до мінімального запасу')
    cert_angle = document('KM-CERT-ZK0311', 'Сертифікат якості до поставки ZK-0311',
        'Кутник сталевий 40×40×4, 200 шт. з 300 за замовленням ZK-0311. Решта 100 шт. — наступною машиною.')
    received = act('receive', purchase_id=po_angle, code='KM-L-MA-7075-0926', location_id=places['ZHY-METAL'],
        quantity='200', documents={'certificate': cert_angle.pk})['lot_id']
    act('quality', lot_id=received, result='approved', inspector_id=quality.pk, note='Сертифікат звірено, геометрія в допуску')
    for article, lot, qty in (('MA-7075', metal['MA-7075'], 260), ('MA-7075', received, 200), ('MS-6061', metal['MS-6061'], 120),
            ('CB-2903', metal['CB-2903'], 4800), ('HN-4402', metal['HN-4402'], 4800),
            ('LW-4000', metal['LW-4000'], 4800), ('PA-187B', metal['PA-187B'], 144)):
        moved = act('transfer', lot_id=lot, quantity=str(qty), location_id=places['ZHY-SHOP'],
            code='KM-T-' + article + '-' + str(lot), reason='Видача в цех під наряд VZ-0141-1', production_id=job1)['lot_id']
        act('reserve', lot_id=moved, quantity=str(qty), production_id=job1)
    cert_rest = document('KM-CERT-ZK0311-REST', 'Сертифікат решти поставки ZK-0311',
        'Кутник сталевий 40×40×4, решта 100 шт. за ZK-0311. Разом прийнято 300 шт.; 20 шт. видано під VZ-0141-1.')
    rest = act('receive', purchase_id=po_angle, code='KM-L-MA-7075-ZK0311-REST',
        location_id=places['ZHY-METAL'], quantity='100', documents={'certificate': cert_rest.pk})['lot_id']
    act('quality', lot_id=rest, result='approved', inspector_id=quality.pk,
        note='Решту поставки й сертифікат звірено, геометрія в допуску')
    rest_shop = act('transfer', lot_id=rest, quantity='20', location_id=places['ZHY-SHOP'],
        code='KM-T-MA-7075-ZK0311-REST', reason='Решта матеріалу під VZ-0141-1', production_id=job1)['lot_id']
    act('reserve', lot_id=rest_shop, quantity='20', production_id=job1)
    act('start', production_id=job1)
    for operation, instruction, days in data.ROUTE:
        act('operator', production_id=job1, operation=operation, operator_id=people['Ігор Бондар'].pk,
            result='done', minutes=240, defects='0', note='Виконано для 120 стелажів СМ-1800 за VZ-0141-1')
    batch_passport = document('KM-PASS-VZ-0141-1', 'Паспорт партії 120 стелажів СМ-1800',
        'VZ-0141-1 для ZM-0141: виготовлено 120 стелажів СМ-1800, версія A. '
        'Формування, зварювання, зачищення, фарбування й складання завершено; геометрію та комплектність перевірено.')
    produced = act('finish', production_id=job1, quantity='120', code='KM-L-SM-1800-VZ0141',
        location_id=places['ZHY-SHOP'], labor_cost='72000', documents={'passport': batch_passport.pk})['lot_id']
    act('quality', lot_id=produced, result='approved', inspector_id=quality.pk,
        note='120 стелажів відповідають специфікації; паспорт партії перевірено')
    ready = act('transfer', lot_id=produced, quantity='120', location_id=places['ZHY-FG'],
        code='KM-T-SM-1800-VZ0141', reason='Готова допущена партія для відвантаження за ZM-0141')['lot_id']
    act('reserve', lot_id=ready, quantity='120', line_id=zm141['SM-1800'].pk)
    act('ship', line_id=zm141['SM-1800'].pk, lot_id=ready, quantity='120', reference='VN-0141-1')
    shipment_doc = document('KM-VN-0141-1', 'Видаткова накладна VN-0141-1 · Логістик Парк',
        'Відвантажено 120 стелажів СМ-1800 з партії VZ-0141-1 за паспортом KM-PASS-VZ-0141-1. '
        'Це частина ZM-0141: решта 134 вироби ще не відвантажена.')
    act('link_document', document_id=shipment_doc.pk, order_id=zm141_id)
    act('reserve', lot_id=finished['SV-1500'], quantity='24', line_id=zm141['SV-1500'].pk)
    Task.objects.create(title='Підготувати решту 134 вироби за ZM-0141: СМ-2000, СВ-1500, ШМ-2 і ТІ-1', priority='high',
        status='active', assignee=people['Ігор Бондар'].full_name, assignee_employee=people['Ігор Бондар'],
        branch=branches['ZHY'], deadline='2026-10-12', category='Виробництво', sales_order_id=zm141_id)

    # Case 2: only the approved batch ships.
    shm2_kyiv = deliver('KM-P-0916', shm2_ok, 'KYI-WH', 40)
    zm144, zm144_id = order('ZM-0144', 'OFFICE', 'Андрій Мельник', '2026-10-03', 'KYI-WH',
        [('SHM-2', 50), ('SHM-1', 30), ('TI-1', 20)])
    order_quality_doc = document('KM-ZM-0144', 'Замовлення покупця ZM-0144 · Офіс Сіті',
        'Замовлено 50 шаф ШМ-2, 30 шаф ШМ-1 і 20 тумб ТІ-1. Під відвантаження у Києві '
        'зарезервовано лише 40 допущених шаф ШМ-2 з партії від 15.09 за паспортом KM-PASS-SHM-2.')
    act('link_document', document_id=order_quality_doc.pk, order_id=zm144_id)
    quality_doc = document('KM-QC-SHM-2-0918', 'Акт невідповідності партії ШМ-2 від 18.09',
        'Партія KM-L-SHM-2-0918: 25 шаф ШМ-2 заблоковано через непрофарбовані зварні шви; '
        'паспорт не оформлено, резервування й відвантаження заборонено. Наталія Ткаченко '
        'має організувати перефарбування та оформлення паспорта до 07.10.2026. '
        'Цей акт не є паспортом або дозволом на відвантаження.')
    act('link_document', document_id=quality_doc.pk, order_id=zm144_id)
    for code, lot, qty in (('SHM-2', shm2_kyiv, 40), ('SHM-1', kyiv['SHM-1'], 30), ('TI-1', kyiv['TI-1'], 20)):
        act('reserve', lot_id=lot, quantity=str(qty), line_id=zm144[code].pk)
        act('ship', line_id=zm144[code].pk, lot_id=lot, quantity=str(qty), reference='VN-0144-1')
    quality_shipment_doc = document('KM-VN-0144-1', 'Видаткова накладна VN-0144-1 · Офіс Сіті',
        'Шафи ШМ-2 — 40 (партія від 15.09), шафи ШМ-1 — 30, тумби ТІ-1 — 20. '
        'Решта 10 шаф ШМ-2 чекає: партія від 18.09 заблокована контролем якості.')
    act('link_document', document_id=quality_shipment_doc.pk, order_id=zm144_id)
    act('invoice', order_id=zm144_id, code='RF-0144', due_date='2026-10-15')
    Task.objects.create(title='Перефарбувати партію ШМ-2 від 18.09 (25 шт.) і оформити паспорт', priority='high',
        status='active', assignee=quality.full_name, assignee_employee=quality, branch=branches['ZHY'],
        deadline='2026-10-07', category='Якість', sales_order_id=zm144_id)
    Task.objects.create(title='Узгодити з «Офіс Сіті» новий строк для 10 шаф ШМ-2', priority='medium',
        status='active', assignee=sales.full_name, assignee_employee=sales, branch=branches['KYI'],
        deadline='2026-10-06', category='Продажі', sales_order_id=zm144_id)

    # Case 3: invoice, partial payment and a reminder.
    dnipro = {'VS-1500': deliver('KM-P-0922', finished['VS-1500'], 'DNI-WH', 36),
              'SV-1200': deliver('KM-P-0923', finished['SV-1200'], 'DNI-WH', 24)}
    zm137, zm137_id = order('ZM-0137', 'AGRO', 'Дмитро Савченко', '2026-09-29', 'DNI-WH',
        [('VS-1500', 30), ('SV-1200', 20)])
    for code, qty in (('VS-1500', 30), ('SV-1200', 20)):
        act('reserve', lot_id=dnipro[code], quantity=str(qty), line_id=zm137[code].pk)
        act('ship', line_id=zm137[code].pk, lot_id=dnipro[code], quantity=str(qty), reference='VN-0137-1')
    payment_shipment_doc = document('KM-VN-0137-1', 'Видаткова накладна VN-0137-1 · Агроснаб Дніпро',
        'За ZM-0137 відвантажено 30 верстаків ВС-1500 і 20 столів СВ-1200 з Дніпра. '
        'Сума відвантаження 420 000,00 грн без ПДВ.')
    act('link_document', document_id=payment_shipment_doc.pk, order_id=zm137_id)
    invoice = act('invoice', order_id=zm137_id, code='RF-0137', due_date='2026-10-01')
    invoice_doc = document('KM-RF-0137', 'Рахунок RF-0137 · Агроснаб Дніпро',
        'Рахунок за відвантаженням VN-0137-1 за ZM-0137: 420 000,00 грн без ПДВ. Строк оплати 01.10.2026.')
    act('link_document', document_id=invoice_doc.pk, invoice_id=invoice['invoice_id'])
    act('payment', invoice_id=invoice['invoice_id'], amount=str((D(invoice['amount']) * D('0.6')).quantize(D('.01'))), reference='PD-5521')
    payment_doc = document('KM-PD-5521', 'Платіжне доручення PD-5521 · Агроснаб Дніпро',
        'Часткова оплата за рахунком RF-0137: 252 000,00 грн з 420 000,00 грн. Залишок 168 000,00 грн.')
    act('link_document', document_id=payment_doc.pk, invoice_id=invoice['invoice_id'])
    manager = people['Дмитро Савченко']
    reminder_doc = document('KM-REM-RF-0137', 'Нагадування про доплату за RF-0137',
        'Після оплати PD-5521 на 252 000,00 грн залишок за RF-0137 становить 168 000,00 грн. '
        'Дмитро Савченко, керівник філії Дніпро, має нагадати покупцю про доплату до 06.10.2026.')
    act('link_document', document_id=reminder_doc.pk, invoice_id=invoice['invoice_id'])
    Task.objects.create(title='Нагадати «Агроснаб Дніпро» про доплату 168 000 грн за RF-0137', priority='high',
        status='active', assignee=manager.full_name, assignee_employee=manager, branch=branches['DNI'],
        deadline='2026-10-06', category='Фінанси', sales_order_id=zm137_id)

    # Background: Lviv branch, a closed school order and an open quote.
    lviv = deliver('KM-P-0930', finished['SV-1500'], 'LVI-WH', 4)
    deliver('KM-P-1003', finished['VS-1500'], 'LVI-WH', 6, receive=False, due='2026-10-07')
    zm146, _ = order('ZM-0146', 'AUTO', "Мар'яна Гнатюк", '2026-10-10', 'LVI-WH', [('VS-1500', 6), ('SV-1500', 4)])
    act('reserve', lot_id=lviv, quantity='4', line_id=zm146['SV-1500'].pk)
    zm139, zm139_id = order('ZM-0139', 'SCHOOL', 'Олена Коваль', '2026-09-25', 'ZHY-FG', [('TI-1', 10), ('SV-1200', 8)])
    for code, qty in (('TI-1', 10), ('SV-1200', 8)):
        act('reserve', lot_id=finished[code], quantity=str(qty), line_id=zm139[code].pk)
        act('ship', line_id=zm139[code].pk, lot_id=finished[code], quantity=str(qty), reference='VN-0139-1')
    paid = act('invoice', order_id=zm139_id, code='RF-0139', due_date='2026-10-02')
    act('payment', invoice_id=paid['invoice_id'], amount=paid['amount'], reference='PD-5490')
    order('ZM-0148', 'LOGISTIC', 'Андрій Мельник', '2026-11-10', 'ZHY-FG', [('SM-2000', 40)], confirm=False)

    if version == '1.1':
        aw_counts = _populate_aw(act, document, items, suppliers, customers, people, places, branches)

    clock.value = {**clock.value, 'as_of': AS_OF}
    clock.save(update_fields=['value'])
    cases = [{**public, 'steps': [{**step, **refs} for step, refs in zip(public['steps'], CASE_REFS[public['key']])]}
             for public in PUBLIC_CASES]
    Configuration.objects.create(key='demo_cases', value={'version': version, 'synthetic': True, 'cases': cases})
    result = {'version': version, 'synthetic': True, 'company': data.COMPANY['name'], 'as_of': AS_OF,
        'currency': 'UAH', 'cases': [c['title'] for c in cases],
        'counts': {'branches': Branch.objects.count(), 'locations': Location.objects.count(),
                   'items': Item.objects.count(), 'orders': SalesLine.objects.values('order').distinct().count()},
        'source': 'Microsoft AdventureWorks (MIT): артикули, ролі постачальників, строки, маршрут; решта синтетична',
        'notice': 'Демо-дані. Не реальні клієнти, платежі чи логістика.'}
    if version == '1.1':
        result['counts'].update(aw_counts)
        result['source'] += ('; v1.1: каталог, специфікації й велике замовлення з AdventureWorks SalesOrder '
                             + str(aw.ORDER['aw_sales_order_id']) + ' (див. bos4_demo_provenance)')
    Configuration.objects.create(key=MARKER, value=result)
    Configuration.objects.create(key='erp_dataset', value={'bos4_demo': True, 'synthetic': True, 'version': version})
    return result


def _populate_aw(act, document, items, suppliers, customers, people, places, branches):
    """v1.1: AdventureWorks catalog (40 localized derivatives) and order 47395 at furniture scale.

    Real AW keys (ProductID, ProductNumber, SalesOrderDetailID) are stored on every derived row; scenario
    links (customer, branch, dates, documents, task) are marked as such in bos4_demo_provenance.
    """
    for aw_number, m in sorted(aw.MATERIALS.items()):
        if m['article'] in items:
            continue
        items[m['article']] = act('item', code=m['article'], name=m['name'], unit=m['unit'], kind='material',
            method='buy', revision='A', currency='UAH', planned_cost=m['price'], minimum='100', lead_days=15,
            required_documents=[], external_codes={'Артикул AdventureWorks': aw_number})['item_id']
    for p in aw.PRODUCTS:
        passport = document('KM-PASS-' + p['code'], 'Паспорт виробу ' + p['name'],
            p['name'] + '. Похідний виріб від AdventureWorks ' + p['aw_number'] + ' (' + p['aw_name'] + '). '
            'Специфікація: ' + ', '.join(a + ' × ' + q for a, q in sorted(p['bom'].items())) + '. '
            'Маршрут: ' + ', '.join(step[0] for step in data.ROUTE) + '. Гарантія 24 місяці.')
        items[p['code']] = act('item', code=p['code'], name=p['name'], unit='шт.', kind='product', method='make',
            revision='A', currency='UAH', planned_cost=p['planned_cost'], minimum='5', lead_days=10,
            required_documents=['passport'], document_id=passport.pk,
            bom=[{'item_id': items[a], 'quantity': q} for a, q in sorted(p['bom'].items())],
            routing=[{'name': n, 'instruction': i, 'days': d} for n, i, d in data.ROUTE],
            external_codes={'AdventureWorks ProductID': str(p['aw_product_id']),
                            'AdventureWorks ProductNumber': p['aw_number']})['item_id']
    customer = Counterparty.objects.create(name=AW_CUSTOMER['name'], type='customer',
        address=AW_CUSTOMER['city'], notes='Демо-клієнт, вигаданий контрагент. Склад замовлення — '
        'AdventureWorks SalesOrder ' + str(aw.ORDER['aw_sales_order_id']) + '.')
    lines = aw.ORDER['lines']
    out = act('order', code=AW_ORDER_CODE, customer_id=customer.pk, owner_id=people['Олена Коваль'].pk,
        due_date='2026-11-27', currency='UAH', branch_id=branches['KYI'].pk,
        fulfillment_location_id=places['ZHY-FG'], notes='Демо-замовлення; ціни без ПДВ.',
        lines=[{'item_id': items[l['code']], 'quantity': str(l['quantity']), 'price': l['price']} for l in lines])
    act('confirm_order', order_id=out['order_id'])
    units = sum(l['quantity'] for l in lines)
    total = sum((D(l['price']) * l['quantity'] for l in lines), D(0))
    if total != D(aw.ORDER['total_uah']):
        raise ValueError('Сума сценарних рядків не збігається з ORDER.total_uah')
    hryvnia = lambda value: f'{D(value):,.2f}'.replace(',', ' ').replace('.', ',') + ' грн'
    order_doc = document('KM-' + AW_ORDER_CODE, 'Замовлення покупця ' + AW_ORDER_CODE + ' · ' + customer.name,
        f'Каркаси й стелажі для мережі складів: {len(lines)} позицій, {units} шт. Сума '
        + hryvnia(total) + ' без ПДВ (сценарна ціна від специфікацій). Строк 27.11.2026. '
        'Склад позицій і кількості — AdventureWorks ' + aw.ORDER['aw_sales_order_number']
        + f' × {aw.QTY_SCALE}. Ціна AW, перерахована за курсом НБУ {aw.RATE["uah_per_unit"]} грн/USD на '
        + aw.RATE['date'] + ': ' + hryvnia(aw.ORDER['aw_total_uah'])
        + f' ({aw.ORDER["aw_total_usd"]} USD).')
    act('link_document', document_id=order_doc.pk, order_id=out['order_id'])
    supply = _supply_aw(act, document, items, suppliers, people, places, out['order_id'])
    Task.objects.create(title=f'Завершити виробництво й відвантаження решти {units - supply["aw_shipped_units"]} '
        'каркасів і стелажів за великим замовленням ' + customer.name, priority='high', status='active',
        assignee=people['Ігор Бондар'].full_name, assignee_employee=people['Ігор Бондар'], branch=branches['ZHY'],
        deadline='2026-10-20', category='Виробництво', sales_order_id=out['order_id'])
    Configuration.objects.create(key='bos4_demo_provenance', value={
        'synthetic': True, 'pins': aw.PINS, 'ledger': [list(row) for row in aw.LEDGER],
        'aw_sales_order_id': aw.ORDER['aw_sales_order_id'], 'aw_order_date': aw.ORDER['aw_order_date'],
        'rate': aw.RATE, 'aw_total_usd': aw.ORDER['aw_total_usd'], 'aw_total_uah': aw.ORDER['aw_total_uah'],
        'scenario_total_uah': aw.ORDER['total_uah'],
        'order_code': AW_ORDER_CODE, 'excluded_leaves': aw.EXCLUDED_LEAVES,
        'aw_work_order_ids': [j['aw_work_order_id'] for j in aw.JOBS],
        'aw_vendor_ids': {p['article']: p['aw_vendor_id'] for p in aw.PURCHASES},
        'first_start': aw.FIRST_START, 'as_of': aw.AS_OF,
        'scenario': ['клієнт ' + customer.name, 'філія й склад виконання', 'строк 27.11.2026',
                     'документи й доручення', 'ціни матеріалів у UAH', 'сценарна ціна рядків',
                     'дата закупівлі й старту виробництва']})
    return {'aw_products': len(aw.PRODUCTS), 'aw_order_lines': len(lines), 'aw_order_units': units, **supply}


def _supply_aw(act, document, items, suppliers, people, places, order_id):
    """v1.1 supply chain for the large order as of aw.AS_OF: AW ProductInventory stock, ProductVendor purchases
    (received), WorkOrder jobs (finished, running or planned), shipment, invoice and part payment."""
    certificate = document('KM-CERT-AW-0150', 'Сертифікат якості металопрокату · залишок складу',
        'Метал на складі на початок виконання замовлення ' + AW_ORDER_CODE + '. Кількості — AdventureWorks '
        'ProductInventory (місця зберігання 1–6), перераховані за правилом «Залишок» у bos4_demo_provenance.')
    delivered = document('KM-CERT-ZK-0150', 'Сертифікати постачальників металу · закупівлі ZK-0150',
        'Металопрокат за закупівлями ZK-0150-01…' + f'{len(aw.PURCHASES):02d}' + ' під замовлення ' + AW_ORDER_CODE
        + ' прийнято повністю; марка сталі й геометрія відповідають специфікаціям.')
    inspector, foreman = people['Наталія Ткаченко'].pk, people['Ігор Бондар'].pk
    pool = {}                                  # article → [lot id, free quantity] in issue order
    stock_lots = 0

    def admit(lot, item, note):
        act('quality', lot_id=lot, result='approved', inspector_id=inspector, note=note)
        pool.setdefault(item.code, []).append([lot, None])

    for row in aw.STOCK:
        if D(row['quantity']) <= 0:
            continue
        item = Item.objects.get(pk=items[row['article']])
        lot = act('opening', code='KM-L-AW-' + row['article'], item_id=item.pk, location_id=places['ZHY-METAL'],
            quantity=row['quantity'], unit_cost=str(item.planned_cost), currency='UAH', revision='A',
            documents={'certificate': certificate.pk} if 'certificate' in item.required_documents else {},
            reason='Залишок на складі металу (AdventureWorks ProductInventory)')['lot_id']
        admit(lot, item, 'Вхідний контроль пройдено')
        pool[item.code][-1][1] = D(row['quantity'])
        stock_lots += 1
    for n, p in enumerate(aw.PURCHASES, 1):
        item = Item.objects.get(pk=items[p['article']])
        po = act('purchase', code=f'ZK-0150-{n:02d}', item_id=item.pk, supplier_id=suppliers[p['supplier']].pk,
            quantity=p['quantity'], price=p['price'], currency='UAH', due_date=p['due_date'], revision='A',
            destination_id=places['ZHY-METAL'], origin_country='UA',
            direct_reason=f'Дефіцит під замовлення {AW_ORDER_CODE}: потреба {p["need"]}, на складі {p["on_hand"]}')['purchase_id']
        lot = act('receive', purchase_id=po, code=f'KM-L-ZK-0150-{n:02d}', location_id=places['ZHY-METAL'],
            quantity=p['quantity'],
            documents={'certificate': delivered.pk} if 'certificate' in item.required_documents else {})['lot_id']
        admit(lot, item, 'Поставку прийнято повністю, сертифікат і кількість звірено')
        pool[item.code][-1][1] = D(p['quantity'])
    lines = {line.item.code: line.pk for line in SalesLine.objects.filter(order_id=order_id).select_related('item')}
    products = {p['code']: p for p in aw.PRODUCTS}
    shipped = []
    for job in aw.JOBS:
        product, qty = products[job['product']], D(job['quantity'])
        production = act('job', code=job['code'], item_id=items[job['product']], quantity=str(job['quantity']),
            location_id=places['ZHY-SHOP'], owner_id=foreman, due_date=job['due_date'],
            line_id=lines[job['product']])['production_id']
        if job['stage'] == 'planned':
            continue
        for article, rate in sorted(product['bom'].items()):
            need = D(rate) * qty
            for n, entry in enumerate(pool[article]):
                take = min(need, entry[1])
                if not take:
                    continue
                moved = act('transfer', lot_id=entry[0], quantity=str(take), location_id=places['ZHY-SHOP'],
                    code=f'KM-T-{job["code"]}-{article}-{n}', reason='Видача в цех під наряд ' + job['code'],
                    production_id=production)['lot_id']
                act('reserve', lot_id=moved, quantity=str(take), production_id=production)
                entry[1] -= take
                need -= take
                if not need:
                    break
            if need:
                raise ValueError(f'Бракує {article} для {job["code"]}: перевірте закупівлі v1.1.')
        act('start', production_id=production)
        route = data.ROUTE if job['stage'] == 'finished' else data.ROUTE[:aw.RUNNING_DONE]
        for operation, _, _ in route:
            act('operator', production_id=production, operation=operation, operator_id=foreman, result='done',
                minutes=240, defects='0', note=f'Виконано для {job["quantity"]} шт. за {job["code"]}')
        if job['stage'] != 'finished':
            continue
        passport = document('KM-PASS-' + job['code'], f'Паспорт партії {job["quantity"]} шт. · {product["name"]}',
            f'{job["code"]} для {AW_ORDER_CODE}: виготовлено {job["quantity"]} шт. «{product["name"]}», версія A. '
            'Усі операції маршруту завершено; геометрію, покриття й комплектність перевірено.')
        made = act('finish', production_id=production, quantity=str(job['quantity']), code='KM-L-' + job['code'],
            location_id=places['ZHY-SHOP'], labor_cost=str(D(aw.LABOR[product['kind']]) * qty),
            documents={'passport': passport.pk})['lot_id']
        act('quality', lot_id=made, result='approved', inspector_id=inspector, note='Партія відповідає специфікації')
        ready = act('transfer', lot_id=made, quantity=str(job['quantity']), location_id=places['ZHY-FG'],
            code='KM-T-' + job['code'] + '-FG', reason='Готова допущена партія для ' + AW_ORDER_CODE)['lot_id']
        act('reserve', lot_id=ready, quantity=str(job['quantity']), line_id=lines[job['product']])
        act('ship', line_id=lines[job['product']], lot_id=ready, quantity=str(job['quantity']), reference='VN-0150-1')
        shipped.append(job)
    units = sum(j['quantity'] for j in shipped)
    shipment = document('KM-VN-0150-1', 'Видаткова накладна VN-0150-1 · ' + AW_CUSTOMER['name'],
        f'Відвантажено {len(shipped)} позицій, {units} шт. за {AW_ORDER_CODE}: '
        + ', '.join(j['code'] for j in shipped) + '. Паспорти партій — KM-PASS-VZ-0150-…')
    act('link_document', document_id=shipment.pk, order_id=order_id)
    due = (date.fromisoformat(aw.AS_OF) + timedelta(days=aw.INVOICE_DAYS)).isoformat()
    invoice = act('invoice', order_id=order_id, code='RF-0150', due_date=due)
    paid = (D(invoice['amount']) * D(aw.PAYMENT_SHARE)).quantize(D('0.01'))
    act('payment', invoice_id=invoice['invoice_id'], amount=str(paid), reference='PD-0150-1')
    return {'aw_stock_lots': stock_lots, 'aw_purchases': len(aw.PURCHASES), 'aw_jobs': len(aw.JOBS),
            'aw_shipped_units': units, 'aw_invoice': invoice['amount'], 'aw_paid': str(paid)}
