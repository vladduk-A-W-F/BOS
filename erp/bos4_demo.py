"""BoS 4 demo company through ordinary ERP commands, never an alternate ledger.

Trusted management command for a fresh demo database only (BOS_DATA_MODE=demo).
It never resets or mixes with existing rows. Data sources: erp/bos4_demo_data.py.
"""
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
from . import bos4_demo_data as data
from .models import Item, Location, SalesLine
from .network_demo import _assert_empty_business
from .service import dispatch, write_lock


VERSION = '1.0'
MARKER = 'bos4_demo_seed'
SEED_DATE = '2026-09-21'
AS_OF = '2026-10-05'
PREFIX = 'KM-'


def _existing():
    marker = Configuration.objects.filter(key=MARKER).first()
    if marker is None:
        return None
    receipt = marker.value
    if not isinstance(receipt, dict) or receipt.get('version') != VERSION or receipt.get('synthetic') is not True:
        raise CommandError('Невідома квитанція демо-компанії. Автоматичних змін немає.')
    return {**receipt, 'created': False}


def _assert_no_connectors():
    from connectors.models import Connector, ConnectorSnapshot
    if Connector.objects.exists() or ConnectorSnapshot.objects.exists():
        raise CommandError('База містить підключені джерела. Змішування з демо-даними заборонене.')


def seed_bos4_demo():
    """All rows commit together; only owned new files may be cleaned."""
    if getattr(settings, 'BOS_DATA_MODE', None) != 'demo':
        raise CommandError('Демо-компанія дозволена лише за BOS_DATA_MODE=demo.')
    if connection.in_atomic_block:
        raise CommandError('Створення демо-компанії потребує власної зовнішньої транзакції.')
    existing = _existing()
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
            existing = _existing()
            if existing is not None:
                return existing
            _assert_empty_business()
            _assert_no_connectors()
            result = _populate(pending_files)
            transaction.on_commit(finalize)
        return {**result, 'created': True}
    except BaseException:
        if not committed:
            for receipt in reversed(pending_files):
                private_document_storage.discard_new(receipt)
        raise


def _populate(pending_files):
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

    clock.value = {**clock.value, 'as_of': AS_OF}
    clock.save(update_fields=['value'])
    cases = [
        {'key': 'components', 'title': 'Комплектуючі для партії меблів',
         'summary': 'Закупівля → приймання → виробництво → відвантаження 120 стелажів. Решта 134 вироби замовлення ще в роботі.',
         'result': {'label': 'Виготовлено й відвантажено', 'value': '120 стелажів СМ-1800'},
         'steps': [
             {'title': 'Замовлення й закупівля', 'text': 'ZM-0141: 254 вироби на 1 922 800 грн; ZK-0311: 300 кутників',
              'order': 'ZM-0141', 'purchase': 'ZK-0311', 'document': 'KM-ZM-0141'},
             {'title': 'Приймання й видача в цех', 'text': 'Прийнято 200 + 100 кутників; 480 кутників і решту матеріалів зарезервовано',
              'purchase': 'ZK-0311', 'document': 'KM-CERT-ZK0311-REST'},
             {'title': 'Виробництво й якість', 'text': '5 операцій завершено; випущено й допущено 120 стелажів СМ-1800',
              'production': 'VZ-0141-1', 'lot': 'KM-L-SM-1800-VZ0141', 'document': 'KM-PASS-VZ-0141-1'},
             {'title': 'Відвантаження', 'text': '120 стелажів відвантажено з Житомира; решта 134 вироби ще не відвантажена',
              'shipment': 'VN-0141-1', 'lot': 'KM-T-SM-1800-VZ0141', 'document': 'KM-VN-0141-1'}]},
        {'key': 'quality', 'title': 'Відвантаження лише допущеної партії',
         'summary': 'Клієнт отримує тільки перевірені шафи; заблокована партія чекає.',
         'result': {'label': 'Відвантажено', 'value': '40 з 50 шаф'},
         'steps': [
             {'title': 'Резерв', 'text': 'Партія від 15.09 у Києві', 'order': 'ZM-0144', 'document': 'KM-ZM-0144'},
             {'title': 'Контроль якості', 'text': 'Партія від 18.09 заблокована', 'lot': 'KM-L-SHM-2-0918', 'document': 'KM-QC-SHM-2-0918'},
             {'title': 'Відвантаження', 'text': '90 виробів за накладною', 'shipment': 'VN-0144-1', 'document': 'KM-VN-0144-1'},
             {'title': 'Доручення', 'text': 'Перефарбувати 25 шаф', 'task': 'Перефарбувати партію ШМ-2', 'document': 'KM-QC-SHM-2-0918'}]},
        {'key': 'payment', 'title': 'Рахунок, оплата й нагадування',
         'summary': 'Часткова оплата не губиться: на решту є відповідальний і строк.',
         'result': {'label': 'Залишок до оплати', 'value': '168 000 грн'},
         'steps': [
             {'title': 'Відвантаження', 'text': '30 верстаків і 20 столів', 'order': 'ZM-0137', 'document': 'KM-VN-0137-1'},
             {'title': 'Рахунок', 'text': '420 000 грн, строк 01.10', 'invoice': 'RF-0137', 'document': 'KM-RF-0137'},
             {'title': 'Оплата', 'text': '252 000 грн, 60%', 'payment': 'PD-5521', 'document': 'KM-PD-5521'},
             {'title': 'Нагадування', 'text': 'Доручення керівнику філії', 'task': 'Нагадати «Агроснаб Дніпро»', 'document': 'KM-REM-RF-0137'}]},
    ]
    Configuration.objects.create(key='demo_cases', value={'version': VERSION, 'synthetic': True, 'cases': cases})
    result = {'version': VERSION, 'synthetic': True, 'company': data.COMPANY['name'], 'as_of': AS_OF,
        'currency': 'UAH', 'cases': [c['title'] for c in cases],
        'counts': {'branches': Branch.objects.count(), 'locations': Location.objects.count(),
                   'items': Item.objects.count(), 'orders': SalesLine.objects.values('order').distinct().count()},
        'source': 'Microsoft AdventureWorks (MIT): артикули, ролі постачальників, строки, маршрут; решта синтетична',
        'notice': 'Демо-дані. Не реальні клієнти, платежі чи логістика.'}
    Configuration.objects.create(key=MARKER, value=result)
    Configuration.objects.create(key='erp_dataset', value={'bos4_demo': True, 'synthetic': True, 'version': VERSION})
    return result
