"""Policy-projected operational network. No demo values and no writes on reads."""
from copy import deepcopy
from decimal import Decimal as D
from math import isfinite

from django.conf import settings

from .balances import exact, money_text, money
from . import queries, network_workflow

CURRENCIES = ('UAH', 'EUR', 'USD')
TABLES = ('points', 'lots', 'purchases', 'orders', 'jobs', 'transfers', 'invoices', 'retentions')
MONEY_FIELDS = {
    'unit_cost', 'value', 'total_cost', 'amount', 'paid', 'open', 'price', 'extras',
    'planned_cost', 'actual_cost', 'effective_credit', 'net_amount', 'receivable',
    'customer_credit', 'retained', 'collectible', 'credit_basis', 'credit_source_error',
}


def filters(params):
    currency = params.get('currency', 'UAH')
    if currency not in CURRENCIES:
        raise ValueError('Оберіть валюту UAH, EUR або USD.')
    branch = params.get('branch_id', '')
    point = params.get('location_id', '')
    for key, value in (('branch_id', branch), ('location_id', point)):
        if value and not (key == 'branch_id' and value == 'unassigned'):
            if not isinstance(value, str) or not value.isascii() or not value.isdigit() or int(value) <= 0:
                raise ValueError('Некоректний фільтр точки або філії.')
    return currency, branch, point


def coordinate(lat, lng):
    if lat is None or lng is None:
        return None
    try:
        a, b = float(lat), float(lng)
    except (TypeError, ValueError, OverflowError):
        return None
    return (a, b) if isfinite(a) and isfinite(b) and -90 <= a <= 90 and -180 <= b <= 180 else None


@exact
def build(policy, params):
    currency, selected_branch, selected_point = filters(params)
    # Reuse the existing field projections and corrected open quantities.
    data = queries.snapshot(policy)
    branches = deepcopy(data.get('branches', []))
    by_branch = {row['id']: row for row in branches}
    locations = deepcopy(data['locations'])
    by_location = {row['id']: row for row in locations}
    items = {row['id']: row for row in data['items']}
    partners = {row['id']: row for row in data['partners']}

    if selected_branch not in ('', 'unassigned') and int(selected_branch) not in by_branch:
        raise ValueError('Філія недоступна.')
    if selected_point and int(selected_point) not in by_location:
        raise ValueError('Точка недоступна.')

    for row in locations:
        branch = by_branch.get(row.get('branch_id'), {})
        own = coordinate(row.get('lat'), row.get('lng'))
        center = coordinate(branch.get('lat'), branch.get('lng'))
        place = own or center
        # A supplier's own point belongs to no branch: label it with the supplier, not "unassigned".
        supplier = partners.get(row.get('supplier_id'), {}).get('name') if row.get('kind') == 'supplier' else None
        row.update(branch_name=branch.get('short_name') or branch.get('name') or supplier or 'Без прив’язки',
                   map_lat=place[0] if place else None, map_lng=place[1] if place else None,
                   coordinate_basis='point' if own else 'branch' if center else 'missing')

    def matches(location_id):
        location = by_location.get(location_id, {})
        if selected_point and location_id != int(selected_point):
            return False
        if selected_branch == 'unassigned':
            return location.get('branch_id') is None
        return not selected_branch or location.get('branch_id') == int(selected_branch)

    def located(row, location_id):
        location = by_location.get(location_id, {})
        return {**row, 'location_id': location_id, 'location_name': location.get('name', 'Без прив’язки'),
                'branch_id': location.get('branch_id')}

    def item_fields(row):
        item = items.get(row.get('item_id'), {})
        return {**row, 'item_code': item.get('code', ''), 'item_name': item.get('name', ''), 'unit': item.get('unit', '')}

    rows = {name: [] for name in TABLES}
    rows['points'] = [deepcopy(row) for row in locations if matches(row['id'])]
    for source in data['lots']:
        if source['currency'] != currency or not matches(source['location_id']):
            continue
        row = item_fields(located(deepcopy(source), source['location_id']))
        if policy.ceo:
            row['value'] = money_text(money(D(row['quantity']) * D(row['unit_cost'])))
        rows['lots'].append(row)

    for point in rows['points']:
        lots = [row for row in rows['lots'] if row['location_id'] == point['id']]
        point['lot_count'] = len(lots)
        if policy.ceo:
            point['inventory_value'] = money_text(sum((D(row['value']) for row in lots), D(0)))

    # A supplier's own point (kind=supplier) is the origin of its deliveries on the map.
    supplier_points = {}
    for row in locations:
        if row.get('kind') == 'supplier' and row.get('supplier_id'):
            supplier_points.setdefault(row['supplier_id'], row['id'])
    for source in data['purchases']:
        location_id = source.get('destination_id')
        if source['currency'] != currency or not matches(location_id):
            continue
        row = item_fields(located(deepcopy(source), location_id))
        row['supplier_name'] = partners.get(source['supplier_id'], {}).get('name', '')
        row['origin_location_id'] = supplier_points.get(source['supplier_id'])
        row['process'] = 'import' if source.get('origin_country') not in ('', None, 'UA') else 'purchase'
        rows['purchases'].append(row)

    all_orders = {row['id']: row for row in data['orders']}
    for source in data['orders']:
        location_id = source.get('fulfillment_location_id')
        if source['currency'] != currency or not matches(location_id):
            continue
        row = located(deepcopy(source), location_id)
        # The organisational owner is independent of the physical fulfillment
        # point; keep both identities even for a cross-branch order.
        row['location_branch_id'] = row['branch_id']
        row['branch_id'] = source.get('branch_id')
        row['customer_name'] = partners.get(source['customer_id'], {}).get('name', '')
        row['process'] = 'export' if source.get('destination_country') not in ('', None, 'UA') else 'sale'
        row['open_line_count'] = sum(D(line['open_quantity']) > 0 for line in data['lines'] if line['order_id'] == source['id'])
        rows['orders'].append(row)

    for source in data['jobs']:
        if source['currency'] == currency and matches(source['location_id']):
            rows['jobs'].append(item_fields(located(deepcopy(source), source['location_id'])))

    for source in data.get('transfers', []):
        if source['currency'] != currency or not matches(source['source_location_id']):
            continue
        row = item_fields(deepcopy(source))
        origin = by_location.get(row['source_location_id'], {})
        destination = by_location.get(row['destination_id'], {})
        row.update(source_location_name=origin.get('name', ''), destination_name=destination.get('name', ''),
                   source_branch_id=origin.get('branch_id'), destination_branch_id=destination.get('branch_id'))
        rows['transfers'].append(row)

    for source in data['invoices']:
        order = all_orders.get(source['order_id'], {})
        location_id = order.get('fulfillment_location_id')
        if source['currency'] != currency or not matches(location_id):
            continue
        row = located(deepcopy(source), location_id)
        # The organisational owner is independent of the physical fulfillment
        # point; keep both identities even for a cross-branch order.
        row['location_branch_id'] = row['branch_id']
        row['branch_id'] = order.get('branch_id')
        row['customer_name'] = partners.get(order.get('customer_id'), {}).get('name', '')
        rows['invoices'].append(row)
    invoice_ids = {row['invoice_id'] for row in rows['invoices']}
    if policy.ceo:
        rows['retentions'] = [deepcopy(row) for row in data.get('retentions', []) if row['invoice_id'] in invoice_ids]
    else:
        # The network intentionally has one financial visibility rule: CEO only.
        # Generic purchasing projections allow managers prices; those are omitted here.
        for name, values in rows.items():
            for row in values:
                for key in MONEY_FIELDS:
                    row.pop(key, None)
                row.pop('approval_snapshot', None)

    transit = [row for row in rows['transfers'] if row['status'] == 'in_transit']
    metrics = {
        'point_count': len(rows['points']), 'lot_count': len(rows['lots']),
        'open_purchases': sum(D(row['open_quantity']) > 0 for row in rows['purchases']),
        'open_orders': sum(row['open_line_count'] > 0 for row in rows['orders']),
        'in_transit_count': len(transit),
    }
    if policy.ceo:
        metrics.update(
            inventory_value=money_text(sum((D(row['value']) for row in rows['lots']), D(0))),
            in_transit_value=money_text(sum((D(row['total_cost']) for row in transit), D(0))),
            receivable=money_text(sum((D(row['receivable']) for row in rows['invoices']), D(0))),
            retained=money_text(sum((D(row['retained']) for row in rows['invoices']), D(0))),
            collectible=money_text(sum((D(row['collectible']) for row in rows['invoices']), D(0))),
        )
    capabilities = policy.capabilities()
    return {
        **network_workflow.build(policy, {'currency': currency,
            'branch_id': selected_branch, 'location_id': selected_point}),
        'schema': 'bos.network.v1', 'as_of': data['as_of'], 'data_mode': settings.BOS_DATA_MODE,
        'currency': currency, 'currency_options': list(CURRENCIES),
        'filters': {'branch_id': selected_branch, 'location_id': selected_point},
        'branches': branches, 'locations': locations, 'rows': rows, 'metrics': metrics,
        'capabilities': {'write': capabilities['write'], 'finance': policy.ceo,
                         'export': capabilities['export_workspace']},
        'warnings': [
            'Показані доступні вашій ролі записи. Фільтр філії застосовано до фізичних точок, а не організаційної філії продажу; права доступу не змінюються.',
            'Точки без координат показані за центром філії або залишаються тільки в таблиці.',
            'Товари в дорозі віднесені до точки-відправника; лінії позначають зв’язки, а не дороги.',
            'Імпорт та експорт позначають міжнародні закупівлі й продажі за країною; митне оформлення не виконується.',
        ],
    }
