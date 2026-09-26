"""Policy-admitted operational sources grouped by the recorded branch.

Directory membership is not a new permission boundary. An order belongs to its
recorded branch; stock belongs to its physical location, including cross-branch
fulfilment. Values are current balances, not cash balances or process timings.
"""
from collections import defaultdict
from decimal import Decimal

from django.utils import timezone

from boss_project.policy import Policy
from branches.models import Branch
from . import service
from .balances import exact, invoice_settlement, money_text, quantity_text
from .models import InvoiceLink, Item, Location, Lot, Movement, Reservation, SalesLine, SalesOrder
from .order_trace import ReadStateChanged, digest, serial

BRANCH_FIELDS = ('id', 'code', 'name', 'short_name', 'type', 'lat', 'lng')


@exact
def collect(policy):
    branches = list(policy.queryset(Branch).order_by('pk').values(*BRANCH_FIELDS))
    locations = list(policy.queryset(Location).order_by('pk').values('id', 'branch_id'))
    orders = list(policy.queryset(SalesOrder).order_by('pk').values('id', 'branch_id'))
    items = {item.pk: item for item in policy.queryset(Item).order_by('pk')}
    lots = list(policy.queryset(Lot).select_related('item').order_by('pk'))
    lot_ids = {lot.pk for lot in lots}
    location_branch = {row['id']: row['branch_id'] for row in locations}
    order_branch = {row['id']: row['branch_id'] for row in orders}
    documents = set(policy.documents().values_list('pk', flat=True))
    reservations = defaultdict(lambda: Decimal(0))
    for row in policy.queryset(Reservation).filter(lot_id__in=lot_ids):
        reservations[row.lot_id] += row.quantity
    points = {}

    def point(pk):
        if pk not in points:
            points[pk] = {'branch': next((b for b in branches if b['id'] == pk), None),
                'location_ids': [], 'order_ids': [], 'lot_ids': [], 'movement_ids': [],
                'invoice_ids': [], 'document_ids': set(), 'stock': {},
                'money': {} if policy.ceo else None,
                'completeness': 'complete' if policy.ceo else 'restricted',
                'movement_scope': 'latest_300_visible_global'}
        return points[pk]

    for branch in branches:
        point(branch['id'])
    for row in locations:
        point(row['branch_id'])['location_ids'].append(row['id'])
    for row in orders:
        point(row['branch_id'])['order_ids'].append(row['id'])
    for line in policy.queryset(SalesLine).filter(order_id__in=order_branch):
        item = items.get(line.item_id)
        if item and item.document_id in documents:
            point(order_branch[line.order_id])['document_ids'].add(item.document_id)
    for lot in lots:
        if lot.location_id not in location_branch or lot.item_id not in items:
            continue
        p = point(location_branch[lot.location_id])
        p['lot_ids'].append(lot.pk)
        item = items[lot.item_id]
        p['document_ids'].update(value for value in lot.documents.values() if value in documents)
        if item.document_id in documents:
            p['document_ids'].add(item.document_id)
        stock = p['stock'].setdefault(item.pk, {'item_id': item.pk, 'code': item.code,
            'name': item.name, 'unit': item.unit, 'quantity': Decimal(0),
            'reserved': Decimal(0), 'available': Decimal(0) if policy.ceo else None, 'lot_ids': []})
        stock['lot_ids'].append(lot.pk)
        stock['quantity'] += lot.quantity
        stock['reserved'] += reservations[lot.pk]
        # Hidden reservations must never be subtracted into a non-CEO number.
        if policy.ceo and service.usable(lot):
            stock['available'] += service.free(lot)
    lot_branch = {lot.pk: location_branch[lot.location_id] for lot in lots if lot.location_id in location_branch}
    for movement in policy.queryset(Movement).order_by('-pk')[:300]:
        if movement.lot_id in lot_branch:
            point(lot_branch[movement.lot_id])['movement_ids'].append(movement.pk)
    for link in policy.queryset(InvoiceLink).filter(order_id__in=order_branch).select_related('invoice').order_by('pk'):
        p = point(order_branch[link.order_id])
        inv = link.invoice
        p['invoice_ids'].append(inv.pk)
        if policy.ceo:
            totals = p['money'].setdefault(inv.currency, {'currency': inv.currency,
                **{key: Decimal(0) for key in ('invoiced', 'gross_invoiced', 'credited', 'paid', 'open', 'customer_credit')},
                'invoice_ids': []})
            settlement = invoice_settlement(inv)
            totals['invoice_ids'].append(inv.pk)
            for field, value in {'invoiced': settlement['net_amount'], 'gross_invoiced': inv.amount,
                    'credited': settlement['effective_credit'], 'paid': inv.paid,
                    'open': settlement['receivable'], 'customer_credit': settlement['customer_credit']}.items():
                totals[field] += value
    for p in points.values():
        p['document_ids'] = sorted(p['document_ids'])
        p['stock'] = list(p['stock'].values())
        for stock in p['stock']:
            for key in ('quantity', 'reserved', 'available'):
                if stock[key] is not None:
                    stock[key] = quantity_text(stock[key])
        if p['money'] is not None:
            p['money'] = [p['money'][currency] for currency in sorted(p['money'])]
            for totals in p['money']:
                for key in ('invoiced', 'gross_invoiced', 'credited', 'paid', 'open', 'customer_credit'):
                    totals[key] = money_text(totals[key])
    return serial({'schema': 'bos.workpoints.v1', 'scope': 'visible_records', 'points': list(points.values()),
        'basis': 'Замовлення — за записаною філією; запаси й рухи — за місцем партії. Рахунки після чинних коригувань, за валютами; це не залишок коштів. Для обмежених ролей резерви лише видимі, доступний залишок не розкривається.'})


def build(request):
    # This is an optimistic consistency check, never a claim of atomic snapshot.
    first = Policy(request)
    access = first.access_revision()
    if getattr(request, 'bos_access_revision', access) != access:
        raise ReadStateChanged()
    before = service.fingerprint()
    body = collect(first)
    second = Policy(request)
    if second.access_revision() != access or digest(collect(second)) != digest(body):
        raise ReadStateChanged()
    final = Policy(request)
    if final.access_revision() != access or service.fingerprint() != before:
        raise ReadStateChanged()
    request.bos_access_revision = access
    body.update(access_revision=access, generated_at=timezone.now().isoformat())
    return body
