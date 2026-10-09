"""Build the compact AdventureWorks subset for the BoS 4 demo v1.1 (erp/bos4_demo_aw_v11.py).

Reads the AdventureWorks OLTP CSV files (MIT licence) line by line from a local checkout of
github.com/microsoft/sql-server-samples and writes only the rows the demo needs, each with its
AdventureWorks keys, plus the pins and the ledger of every transformation. Raw CSVs never enter Git.

    python scripts/bos4_aw_subset.py --source <sql-server-samples checkout> --commit <sha>

The output is deterministic for the same pinned files: re-running it must reproduce the module byte
for byte (tests compare the recorded SHA-256 pins with the files when they are available).
"""
import argparse
import collections
import datetime
import hashlib
from decimal import Decimal as D, ROUND_HALF_UP
from pathlib import Path
import pprint

CSV_DIR = 'samples/databases/adventure-works/oltp-install-script'
FILES = ('AWBuildVersion', 'Product', 'BillOfMaterials', 'SalesOrderHeader', 'SalesOrderDetail',
         'ProductInventory', 'ProductVendor', 'PurchaseOrderHeader', 'PurchaseOrderDetail', 'Vendor', 'WorkOrder')
SALES_ORDER = '47395'              # the AW reseller order with the most distinct finished goods (40)
SUBCATEGORIES = {'2': 'bike', '14': 'frame'}   # Road Bikes, Road Frames
QTY_SCALE = 5                      # AW OrderQty × 5: a furniture distributor's volume
# The AW line price is converted to UAH exactly (Decimal, pinned NBU rate) and kept on every line. The order
# itself uses a separate localized scenario price built from the AW-derived BOM; both totals are recorded.
RATE = {'currency': 'USD', 'uah_per_unit': '44.6819', 'date': '2026-10-01',
        'source': 'НБУ, офіційний курс гривні: bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&date=20261001'}
LABOR = {'frame': '600', 'bike': '900'}        # UAH per unit: cutting, welding, painting, assembly
MARKUP = {'frame': '1.45', 'bike': '1.50'}     # selling price = planned cost × markup, rounded to 10 UAH
PAINT_KG_PER_OZ = '0.0283495'
PAINT_COVERAGE = '6'               # liquid frame paint (oz) → powder coating for a furniture frame (kg)
FASTENER_FACTOR = '8'              # bolts per crank/headset → bolts per five-shelf rack
STORAGE = {'1', '2', '3', '4', '5', '6'}   # AW Location: Tool Crib … Miscellaneous Storage → the order's own store
# The large order's materials are kept apart from the v1.0 metal store: AW stock and v1.1 deliveries only.
ORDER_STORE = {'key': 'ZHY-AW', 'name': 'Склад комплектації великих замовлень', 'branch': 'ZHY'}
# AW vendor of each real purchase record → BoS supplier. «METAL» is the v1.0 supplier that already stands for
# Custom Frames, Inc.; every other AW vendor gets its own localized synthetic counterparty (city centre point).
VENDORS = {
    '1568': {'key': 'METAL'},
    '1514': {'key': 'AW-1514', 'name': 'Кріпмаркет', 'city': 'Полтава', 'lat': 49.58925, 'lng': 34.55367},
    '1540': {'key': 'AW-1540', 'name': 'Метизи Захід', 'city': 'Львів', 'lat': 49.83826, 'lng': 24.02324},
    '1566': {'key': 'AW-1566', 'name': 'Кріплення Поділля', 'city': 'Вінниця', 'lat': 49.23278, 'lng': 28.48097},
    '1648': {'key': 'AW-1648', 'name': 'Імпорт Кріплення', 'city': 'Одеса', 'lat': 46.47747, 'lng': 30.73262},
    '1692': {'key': 'AW-1692', 'name': 'Порошкові покриття Дніпро', 'city': 'Дніпро', 'lat': 48.4593, 'lng': 35.03865},
}
FIRST_START = '2026-09-22'         # scenario day production starts; every delivery is due the day before
AS_OF = '2026-10-05'               # scenario «today»: jobs due before it are finished and shipped
RUNNING_DONE = 2                   # route operations already reported on a job still running at AS_OF
PAYMENT_SHARE = '0.5'              # part of the shipment invoice already paid
INVOICE_DAYS = 14                  # invoice due = AS_OF + INVOICE_DAYS

COLORS = {'Black': ('B', 'чорний', 'RAL 9005'), 'Red': ('R', 'червоний', 'RAL 3020'),
          'Yellow': ('Y', 'жовтий', 'RAL 1023')}
FRAME_TIERS = {'LL': 'Економ', 'ML': 'Стандарт', 'HL': 'Посилений'}
BIKE_SERIES = {'Road-650': ('650', 'Економ'), 'Road-550-W': ('550W', 'Стандарт, вузький'),
               'Road-250': ('250', 'Посилений')}

# AW leaf material → (BoS article, Ukrainian name, unit, supplier key, scenario price UAH, kind)
# AW leaf material → (BoS article, Ukrainian name, unit, supplier key, scenario price UAH, kind, BoS units per AW unit)
MATERIALS = {
    'MS-0253': ('MS-0253', 'Лист сталевий 1250×2500×1,0 мм', 'шт.', 'METAL', '1690.00', 'metal', '0.1'),
    'MS-1256': ('MS-1256', 'Заготовка сталева 2 мм, стійка', 'шт.', 'METAL', '120.00', 'metal', '1'),
    'MS-1981': ('MS-1981', 'Заготовка сталева 1,5 мм, розкіс', 'шт.', 'METAL', '45.00', 'metal', '1'),
    'MS-2259': ('MS-2259', 'Заготовка сталева 3 мм, опора', 'шт.', 'METAL', '70.00', 'metal', '1'),
    'MS-2341': ('MS-2341', 'Заготовка сталева 1,5 мм, поперечина', 'шт.', 'METAL', '60.00', 'metal', '1'),
    'MS-2348': ('MS-2348', 'Заготовка сталева 2 мм, кронштейн', 'шт.', 'METAL', '40.00', 'metal', '1'),
    'MB-2024': ('MB-2024', 'Труба профільна 40×20×1,5, 2 м', 'шт.', 'METAL', '310.00', 'metal', '1'),
    'MB-6061': ('MB-6061', 'Труба профільна 30×30×1,5, 2 м', 'шт.', 'METAL', '295.00', 'metal', '1'),
    'PA-187B': ('PA-187B', 'Фарба порошкова чорна RAL 9005', 'кг', 'PAINT', '265.00', 'paint', None),
    'PA-361R': ('PA-361R', 'Фарба порошкова червона RAL 3020', 'кг', 'PAINT', '290.00', 'paint', None),
    'PA-823Y': ('PA-823Y', 'Фарба порошкова жовта RAL 1023', 'кг', 'PAINT', '295.00', 'paint', None),
    'CB-2903': ('CB-2903', 'Болт М8×20 оцинкований', 'шт.', 'FAST', '3.40', 'fastener', None),
    'CN-6137': ('CN-6137', 'Гайка фланцева М8', 'шт.', 'FAST', '2.10', 'fastener', None),
    'PB-6109': ('PB-6109', 'Болт М10×30 оцинкований', 'шт.', 'FAST', '5.20', 'fastener', None),
    'LN-9080': ('LN-9080', 'Гайка самоконтрувальна М10', 'шт.', 'FAST', '3.10', 'fastener', None),
    'KW-4091': ('KW-4091', 'Шайба стопорна М10', 'шт.', 'FAST', '1.40', 'fastener', None),
}
# Bicycle-only leaves that have no furniture counterpart; listed in the ledger, never in a BOM.
EXCLUDED_PREFIXES = {
    'AR': 'кільце рульової колонки', 'BA': 'кулька підшипника', 'BE': 'підшипник', 'CA': 'шатун',
    'CH': 'ланцюг', 'CR': 'зірка або кільце колонки', 'DC': 'наклейка', 'FB': 'гальмо', 'FC': 'рамка перемикача',
    'FH': 'вільний хід', 'FL': 'тяга перемикача', 'GP': 'ролик перемикача', 'GT': 'обмотка керма',
    'LR-2398': 'стопорне кільце підшипника каретки', 'LR-8520': 'нижнє кільце колонки', 'NI': 'ніпель', 'PD': 'педаль', 'RA': 'кільце підшипника', 'RB': 'гальмо',
    'RC': 'рамка перемикача', 'RF': 'відбивач', 'RM': 'обід', 'SD': 'вісь', 'SE': 'сідло', 'SH': 'корпус втулки',
    'SK': 'спиця', 'SL': 'вузол сідла', 'SP': 'підсідельна труба', 'TI': 'шина', 'TP': 'ролик натягувача',
    'TT': 'камера',
}


MATERIALS_BY_ARTICLE = {v[0]: v for v in MATERIALS.values()}


def rows(path):
    with open(path, encoding='utf-8', errors='strict') as handle:
        for line in handle:
            line = line.rstrip('\n')
            if line:
                yield line.split('\t')


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def money(value):
    return str(D(value).quantize(D('0.01'), rounding=ROUND_HALF_UP))


def excluded(number):
    return EXCLUDED_PREFIXES.get(number) or EXCLUDED_PREFIXES.get(number.split('-')[0])


def build(source):
    base = Path(source) / CSV_DIR
    pins = {name + '.csv': sha256(base / (name + '.csv')) for name in FILES}
    build_version = next(rows(base / 'AWBuildVersion.csv'))[1]
    product = {r[0]: r for r in rows(base / 'Product.csv')}
    bom = collections.defaultdict(list)
    for r in rows(base / 'BillOfMaterials.csv'):
        if r[1] and not r[4].strip():       # assembly rows still in force (no EndDate)
            bom[r[1]].append((r[2], D(r[7]), r[5].strip()))
    material_ids = {r[0]: r[2] for r in product.values() if r[2] in MATERIALS}
    header = next(r for r in rows(base / 'SalesOrderHeader.csv') if r[0] == SALES_ORDER)
    details = [r for r in rows(base / 'SalesOrderDetail.csv')
               if r[0] == SALES_ORDER and product[r[4]][18] in SUBCATEGORIES]

    def leaves(pid, multiplier=D(1), out=None):
        out = collections.Counter() if out is None else out
        for child, qty, unit in bom.get(pid, ()):
            if bom.get(child):
                leaves(child, multiplier * qty, out)
            else:
                out[(child, unit)] += multiplier * qty
        return out

    products, seen_codes, dropped = [], set(), collections.Counter()
    for pid in sorted({r[4] for r in details}, key=int):
        p = product[pid]
        name, number, color, size, kind = p[1], p[2], p[5], p[10], SUBCATEGORIES[p[18]]
        letter, color_ua, ral = COLORS[color]
        height = 1000 + 20 * int(size)
        if kind == 'frame':
            tier = name.split(' ')[0]
            narrow = '-W' in name
            code = f'KS-{tier}{"W" if narrow else ""}-{letter}-{height}'
            title = (f'Каркас стелажа {FRAME_TIERS[tier]}{", вузький" if narrow else ""}, '
                     f'{color_ua}, H {height} мм')
        else:
            model = name.split(' ')[0]
            series, tier_ua = BIKE_SERIES[model]
            code = f'SK-{series}-{letter}-{height}'
            title = f'Стелаж складський С-{series[:3]} ({tier_ua}), {color_ua}, H {height} мм'
        assert code not in seen_codes, code
        seen_codes.add(code)
        materials = {}
        for (child, unit), qty in sorted(leaves(pid).items(), key=lambda t: product[t[0][0]][2]):
            aw_number = product[child][2]
            if aw_number in MATERIALS:
                article, _, _, _, _, mkind, per_aw = MATERIALS[aw_number]
                if mkind == 'paint':
                    assert unit == 'OZ', (aw_number, unit)
                    qty = (qty * D(PAINT_KG_PER_OZ) * D(PAINT_COVERAGE)).quantize(D('0.01'), rounding=ROUND_HALF_UP)
                elif mkind == 'fastener':
                    assert unit == 'EA', (aw_number, unit)
                    qty = qty * D(FASTENER_FACTOR)
                else:
                    assert unit == 'EA', (aw_number, unit)
                    qty = qty * D(per_aw)
                materials[article] = format(qty.normalize(), 'f')
            elif excluded(aw_number):
                dropped[aw_number] += 1
            else:
                raise SystemExit(f'Unmapped AdventureWorks leaf {aw_number} ({product[child][1]})')
        cost = sum((D(MATERIALS_BY_ARTICLE[a][4]) * D(q) for a, q in materials.items()), D(LABOR[kind]))
        price = (cost * D(MARKUP[kind]) / 10).quantize(D('1'), rounding=ROUND_HALF_UP) * 10
        products.append({
            'code': code, 'name': title, 'kind': kind, 'height_mm': height, 'color': ral,
            'aw_product_id': int(pid), 'aw_number': number, 'aw_name': name,
            'planned_cost': money(cost), 'price': money(price), 'bom': materials,
        })
    by_pid = {p['aw_product_id']: p for p in products}
    lines = []
    for r in sorted(details, key=lambda r: int(r[1])):
        unit_usd = D(r[6]) * (1 - D(r[7]))
        lines.append({'aw_detail_id': int(r[1]), 'aw_product_id': int(r[4]), 'code': by_pid[int(r[4])]['code'],
                      'aw_qty': int(r[3]), 'quantity': int(r[3]) * QTY_SCALE,
                      'aw_unit_price_usd': r[6], 'aw_unit_discount': r[7],
                      'aw_unit_price_uah': money(unit_usd * D(RATE['uah_per_unit'])),
                      'price': by_pid[int(r[4])]['price']})
    stock, purchases = stock_and_purchases(base, material_ids, products, lines, header[2][:10])
    return {
        'stock': stock, 'purchases': purchases, 'jobs': jobs(base, header[2][:10], lines),
        'pins': {'repository': 'https://github.com/microsoft/sql-server-samples', 'path': CSV_DIR,
                 'aw_build_version': build_version, 'license': 'MIT (Copyright (c) Microsoft Corporation)',
                 'csv_sha256': pins},
        'order': {'aw_sales_order_id': int(SALES_ORDER), 'aw_sales_order_number': header[7],
                  'aw_order_date': header[2][:10], 'aw_customer_id': int(header[10]), 'lines': lines,
                  'aw_total_usd': money(sum(D(l['aw_unit_price_usd']) * (1 - D(l['aw_unit_discount'])) * l['quantity']
                                           for l in lines)),
                  'aw_total_uah': money(sum(D(l['aw_unit_price_uah']) * l['quantity'] for l in lines)),
                  'total_uah': money(sum(D(l['price']) * l['quantity'] for l in lines))},
        'products': products,
        'materials': {k: dict(zip(('article', 'name', 'unit', 'supplier', 'price', 'kind', 'per_aw_unit'), v))
                      for k, v in MATERIALS.items()},
        'excluded_leaves': {k: EXCLUDED_PREFIXES.get(k) or EXCLUDED_PREFIXES[k.split('-')[0]] for k in sorted(dropped)},
    }


def physical(per_aw, qty):
    """AW stock/EA unit → BoS unit without usage factors: 1 EA = 1 шт. (MS-0253: 0,1 листа); paint 1 = 1 кг."""
    return qty * D(per_aw or '1')


def stock_and_purchases(base, material_ids, products, lines, order_date):
    inventory = collections.defaultdict(list)
    for r in rows(base / 'ProductInventory.csv'):
        if r[0] in material_ids and r[1] in STORAGE:
            inventory[material_ids[r[0]]].append({'aw_location_id': int(r[1]), 'shelf': r[2], 'bin': int(r[3]),
                                                  'aw_quantity': int(r[4])})
    vendors = {r[0]: r[2] for r in rows(base / 'Vendor.csv')}
    offers = {(r[0], r[1]): r for r in rows(base / 'ProductVendor.csv') if r[0] in material_ids}
    headers = {r[0]: r for r in rows(base / 'PurchaseOrderHeader.csv')}
    # The material's real AW purchase record: the first complete PO line (header Status 4, RejectedQty 0) whose
    # header OrderDate is on or after the AW sales order date; ties by PurchaseOrderID, then detail id.
    records = {}
    for r in rows(base / 'PurchaseOrderDetail.csv'):
        if r[4] not in material_ids:
            continue
        h = headers[r[0]]
        if h[6][:10] < order_date or h[2] != '4' or D(r[8]) != 0:
            continue
        key = (h[6][:10], int(r[0]), int(r[1]))
        if material_ids[r[4]] not in records or key < records[material_ids[r[4]]][0]:
            records[material_ids[r[4]]] = (key, r, h)
    by_code = {p['code']: p for p in products}
    need = collections.Counter()
    for line in lines:
        for article, qty in by_code[line['code']]['bom'].items():
            need[article] += D(qty) * line['quantity']
    stock, purchases = [], []
    for aw_number, (article, _, unit, supplier, price, kind, per_aw) in sorted(MATERIALS.items()):
        rows_ = sorted(inventory[aw_number], key=lambda x: (x['aw_location_id'], x['shelf'], x['bin']))
        on_hand = physical(per_aw, sum(D(x['aw_quantity']) for x in rows_)).quantize(D('0.01'), rounding=ROUND_HALF_UP)
        stock.append({'article': article, 'aw_rows': rows_, 'quantity': format(on_hand.normalize(), 'f')})
        _, detail, head = records[aw_number]
        t = offers[(detail[4], head[4])]                 # the same Product–Vendor pair in ProductVendor
        aw_unit = t[9].strip()
        # MinOrderQty applies only where the AW purchase unit is the stock unit (EA); packs (CAN/CTN/CS/GAL)
        # have no size in AW, so they are not converted.
        minimum = physical(per_aw, D(t[6])) if aw_unit == 'EA' else D(0)
        shortage = need[article] - on_hand
        if shortage <= 0:
            continue
        quantity = max(shortage, minimum).to_integral_value(rounding='ROUND_CEILING')
        lead = int(t[2])
        due = datetime.date.fromisoformat(FIRST_START) - datetime.timedelta(days=1)
        purchases.append({'article': article, 'need': format(need[article].normalize(), 'f'),
                          'on_hand': format(on_hand.normalize(), 'f'), 'quantity': str(quantity), 'price': price,
                          'lead_days': lead, 'due_date': due.isoformat(),
                          'ordered_date': (due - datetime.timedelta(days=lead)).isoformat(),
                          'supplier': VENDORS[head[4]]['key'], 'aw_vendor_id': int(head[4]),
                          'aw_vendor_name': vendors[head[4]], 'aw_purchase_order_id': int(head[0]),
                          'aw_po_detail_id': int(detail[1]), 'aw_po_order_date': head[6][:10],
                          'aw_po_due_date': detail[2][:10], 'aw_po_qty': int(detail[3]),
                          'aw_po_received_qty': detail[7], 'aw_po_unit_price_usd': detail[5],
                          'aw_po_unit_price_uah': money(D(detail[5]) * D(RATE['uah_per_unit'])),
                          'aw_min_order_qty': int(t[6]), 'aw_unit': aw_unit})
    return stock, purchases


def jobs(base, order_date, lines):
    """One job per order line. Its AW WorkOrder is the product's first one starting on or after the AW order
    date; AW start offsets and durations are kept, shifted so the earliest start is FIRST_START."""
    wanted = {line['aw_product_id'] for line in lines}
    first = {}
    for r in rows(base / 'WorkOrder.csv'):
        pid, start = int(r[1]), r[5][:10]
        if pid in wanted and start >= order_date and (pid not in first or (start, int(r[0])) < (first[pid][5][:10], int(first[pid][0]))):
            first[pid] = r
    day = datetime.date.fromisoformat
    shift = day(FIRST_START) - min(day(first[l['aw_product_id']][5][:10]) for l in lines)
    out = []
    for n, line in enumerate(lines, 1):
        r = first[line['aw_product_id']]
        out.append({'code': f'VZ-0150-{n:02d}', 'product': line['code'], 'aw_detail_id': line['aw_detail_id'],
                    'quantity': line['quantity'], 'aw_work_order_id': int(r[0]), 'aw_order_qty': int(r[2]),
                    'aw_scrapped_qty': int(r[4]), 'aw_start_date': r[5][:10], 'aw_due_date': r[7][:10],
                    'start_date': (day(r[5][:10]) + shift).isoformat(), 'due_date': (day(r[7][:10]) + shift).isoformat()})
        out[-1]['stage'] = ('finished' if out[-1]['due_date'] < AS_OF else
                            'running' if out[-1]['start_date'] <= AS_OF else 'planned')
    return out


LEDGER = (
    ('Вибір замовлення', f'SalesOrderHeader/Detail {SALES_ORDER}: замовлення реселера з найбільшою кількістю '
     'різних готових виробів (40). Узято лише рядки Road Bikes (підкатегорія 2) і Road Frames (14).'),
    ('Кількість', f'OrderQty × {QTY_SCALE} — обсяг дистриб’ютора меблів; позиція й склад рядків — з AW.'),
    ('Перерахунок ціни AW', 'aw_unit_price_uah = UnitPrice × (1 − UnitPriceDiscount) (USD, SalesOrderDetail) × '
     f'{RATE["uah_per_unit"]} грн/USD (НБУ, {RATE["date"]}); Decimal, до копійки ROUND_HALF_UP. Підсумки: '
     'aw_total_usd і aw_total_uah = Σ ціна × кількість рядка (кількість після масштабу).'),
    ('Сценарна ціна', 'Окремо від ціни AW, позначена як сценарна: планова собівартість = Σ (кількість у специфікації × '
     f'сценарна ціна матеріалу) + робота {LABOR["frame"]} грн (каркас) / {LABOR["bike"]} грн (стелаж); ціна '
     f'замовлення = собівартість × {MARKUP["frame"]} / {MARKUP["bike"]}, округлено до 10 грн. Підсумок total_uah. '
     'Різницю між ціною AW і сценарною ціною не приховано: обидві в кожному рядку.'),
    ('Виріб', 'Road Frame → «Каркас стелажа» (LL/ML/HL → Економ/Стандарт/Посилений, «-W» → вузький); '
     'Road Bike → «Стелаж складський» серії 650/550/250. Колір AW → колір фарби RAL. '
     'Висота H = 1000 + 20 × Size (см AW). Локалізована похідна, не велосипед.'),
    ('Специфікація', 'BillOfMaterials (рядки без EndDate) розгорнуто до листових матеріалів; кількості множаться '
     'вздовж дерева. Метал (Metal Sheet/Bar) → сталеві заготовки й профіль: 1 EA = 1 шт. заготовки під висоту H; '
     'MS-0253 — частка повного листа 1250×2500, 1 EA = 0,1 листа. '
     f'Фарба OZ → кг: × {PAINT_KG_PER_OZ} × {PAINT_COVERAGE} (порошкове покриття). '
     f'Кріплення (болти, гайки, шайби): × {FASTENER_FACTOR} на стелаж.'),
    ('Виключено', 'Велосипедні деталі без меблевого відповідника (колеса, шини, гальма, ланцюг, сідла, педалі, '
     'підшипники, наклейки) — список у EXCLUDED_LEAVES, у специфікацію не входять.'),
    ('Залишок', 'ProductInventory, місця зберігання AW 1–6 (Tool Crib … Miscellaneous Storage) → окремий '
     f'«{ORDER_STORE["name"]}» у Житомирі: запас і поставки цього замовлення зберігаються окремо від складу металу '
     'демо 1.0, тому дефіцит рахується лише від цього складу, а партії 1.0 не видаються під VZ-0150. '
     'Лише перерахунок одиниць: 1 одиниця AW = 1 шт. (MS-0253 — 0,1 листа); фарба: 1 одиниця запасу AW = 1 кг — '
     'сценарне припущення, бо одиницю запасу фарби AW не вказує. Коефіцієнти витрати (покриття, кріплення на '
     'стелаж) до залишку не застосовуються.'),
    ('Закупівля', 'Запис закупівлі AW на кожен матеріал: перший рядок PurchaseOrderDetail зі статусом заголовка '
     'Complete (4) і RejectedQty 0, де OrderDate заголовка не раніше дати замовлення AW. Звідти постачальник (VendorID '
     '→ Vendor), номери PO й рядка, кількість, отримано, UnitPrice (USD) × ' + RATE['uah_per_unit'] + ' = '
     'aw_po_unit_price_uah. AverageLeadTime і MinOrderQty — з ProductVendor для тієї ж пари продукт–постачальник. '
     'Постачальник BoS: Custom Frames, Inc. — чинний «Металопрокат Центр» (METAL); кожен інший постачальник AW — '
     'власний локалізований вигаданий контрагент (VENDORS), один до одного. Сценарне перетворення: кількість = '
     'потреба (Σ специфікація × кількість рядка) − залишок окремого складу, округлено вгору; для EA не менше '
     'MinOrderQty, для упаковок (CAN/CTN/CS/GAL) розмір в AW не задано — MinOrderQty записано як є. Строк поставки — '
     f'день перед стартом виробництва ({FIRST_START}), дата замовлення = строк − AverageLeadTime. Ціна закупівлі — '
     'сценарна ціна матеріалу за одиницю BoS, окремо від ціни AW.'),
    ('Виробництво', 'Одна робота на рядок замовлення, кількість = кількість рядка. WorkOrder — перший для того ж '
     'ProductID зі StartDate не раніше дати замовлення AW; зміщення старту й тривалість збережено, графік зсунуто так, '
     f'щоб найраніший старт був {FIRST_START}. Строк роботи = DueDate AW + зсув.'),
    ('Виконання', f'Стан на {AS_OF} (сценарний): усі закупівлі прийнято повністю й допущено якістю; роботи зі строком '
     f'раніше {AS_OF} виконано (усі операції маршруту), допущено, відвантажено одним документом VN-0150-1; роботи, що '
     f'вже почалися, мають {RUNNING_DONE} перші операції. Матеріал видається в цех під роботу й резервується: '
     'спершу залишок AW, далі прийняті закупівлі. Робота за випуск = ставка «Сценарна ціна» × кількість. Рахунок '
     f'RF-0150 — на відвантажене, строк {AS_OF} + {INVOICE_DAYS} дн.; сплачено частку {PAYMENT_SHARE}.'),
    ('Сценарне', 'Ціни матеріалів у UAH, клієнт, строк, філія, документи, доручення, дата закупівлі й старту '
     'виробництва, стан виконання й оплата — сценарні, не з AW.'),
)


def render(data, commit):
    head = (
        '"""AdventureWorks subset for the BoS 4 demo v1.1. Generated by scripts/bos4_aw_subset.py; do not edit.\n\n'
        'Source: Microsoft AdventureWorks OLTP sample, MIT License, Copyright (c) Microsoft Corporation.\n'
        'Every row keeps its AdventureWorks keys; LEDGER lists each transformation; SCENARIO marks what is not AW.\n'
        '"""\n\n'
    )
    pins = {**data.pop('pins'), 'commit': commit}
    parts = [head, 'PINS = ' + pprint.pformat(pins, width=110, sort_dicts=True) + '\n\n',
             'RATE = ' + pprint.pformat(RATE, width=110, sort_dicts=True) + '\n',
             'LABOR = ' + pprint.pformat(LABOR, sort_dicts=True) + '\n',
             'MARKUP = ' + pprint.pformat(MARKUP, sort_dicts=True) + '\n',
             f'QTY_SCALE = {QTY_SCALE!r}\n',
             f'PAINT_KG_PER_OZ = {PAINT_KG_PER_OZ!r}\nPAINT_COVERAGE = {PAINT_COVERAGE!r}\n',
             f'FASTENER_FACTOR = {FASTENER_FACTOR!r}\n',
             f'FIRST_START = {FIRST_START!r}\nAS_OF = {AS_OF!r}\n',
             'ORDER_STORE = ' + pprint.pformat(ORDER_STORE, sort_dicts=True) + '\n',
             'VENDORS = ' + pprint.pformat(VENDORS, width=110, sort_dicts=True) + '\n',
             f'RUNNING_DONE = {RUNNING_DONE!r}\nPAYMENT_SHARE = {PAYMENT_SHARE!r}\nINVOICE_DAYS = {INVOICE_DAYS!r}\n\n',
             'LEDGER = ' + pprint.pformat(LEDGER, width=110) + '\n\n']
    for key in ('materials', 'products', 'order', 'stock', 'purchases', 'jobs', 'excluded_leaves'):
        parts.append(key.upper() + ' = ' + pprint.pformat(data[key], width=110, sort_dicts=True) + '\n\n')
    return ''.join(parts).rstrip('\n') + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--source', required=True, help='local sql-server-samples checkout')
    parser.add_argument('--commit', required=True, help='exact commit of that checkout')
    parser.add_argument('--output', default=str(Path(__file__).resolve().parents[1] / 'erp' / 'bos4_demo_aw_v11.py'))
    args = parser.parse_args()
    Path(args.output).write_text(render(build(args.source), args.commit), encoding='utf-8')


if __name__ == '__main__':
    main()
