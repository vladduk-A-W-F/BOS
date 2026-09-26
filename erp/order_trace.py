"""Read-only order sources. Optimistic double-read, never an atomic snapshot.

Policy itself traverses global ERP sets. The projection is order-scoped; its
cost is not guaranteed to be local. Private dependency digests never leave here.
"""
import hashlib
import json
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from boss_project.policy import Policy
from operations.models import Configuration, Document
from operations.service import as_of
from tasks.models import Task
from tasks.queries import source_refs as task_source_refs
from . import service
from .balances import exact, quantity_text
from .models import (InvoiceLink, Lot, Movement, OrderCancellation, Production,
                     Reservation, SalesLine, SalesOrder)

LIMIT = 100
SCHEMA = 'bos.order-trace.v1'
BASIS = 'Відвантажено — історична кількість позиції; фізичне повернення її не зменшує. Відкрито = замовлено − відвантажено − скасовано.'
RESTRICTED = 'Повне пояснення недоступне в поточному доступі.'


class ReadStateChanged(Exception):
    pass


def serial(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True))


def digest(value):
    return hashlib.sha256(json.dumps(serial(value), ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def write_revision():
    # Empty list is the missing sentinel; a GET must never create the mutex.
    return list(Configuration.objects.filter(key='erp_write').values('id', 'value'))


def rows(queryset, *fields):
    return list(queryset.order_by('pk').values(*fields))


def person(pk, name, role):
    return {'id': pk, 'name': name, 'role': role} if pk is not None else None


def cap(values):
    return values[:LIMIT], len(values) > LIMIT


def grouped(values, key):
    result = defaultdict(list)
    for value in values:
        result[value[key]].append(value)
    return result


def admitted(policy, model, source):
    ids = [row['id'] for row in source]
    return set(policy.queryset(model).filter(pk__in=ids).values_list('pk', flat=True)) if ids else set()


def lot_admission(policy, lot, revision):
    """Materialize document admission, without revealing a hidden latest version.

    usable() remains the business rule including verified stored bytes. Its
    result and document metadata are part of both private read revisions.
    """
    needed = lot.item.required_documents
    metadata = []
    permitted = True
    for kind in needed:
        pk = lot.documents.get(kind)
        doc = Document.objects.filter(pk=pk).first()
        latest = Document.objects.filter(code=doc.code).order_by('-pk').first() if doc else None
        pair = []
        for value in (doc, latest):
            pair.append(None if value is None else {
                'id': value.pk, 'code': value.code, 'revision': value.revision,
                'status': value.status, 'checksum': value.checksum,
                'file': value.original_file.name, 'size': value.size,
                'access_level': value.access_level,
            })
            if value is not None and not policy.documents().filter(pk=value.pk).exists():
                permitted = False
        metadata.append({'kind': kind, 'documents': pair})
    value = service.usable(lot, revision) if permitted else None
    return value, {'lot_id': lot.pk, 'revision': revision, 'quality': lot.quality,
                   'lot_revision': lot.revision, 'documents': lot.documents,
                   'required_documents': needed, 'metadata': metadata, 'usable': value}


@exact
def collect(policy, pk):
    """Two independent invocations materialize all consumed values and sets.

    Unfiltered scoped rows serve only completeness/digest checks. Every returned
    row is admitted separately; no private IDs/counts/types appear in the DTO.
    """
    order = policy.queryset(SalesOrder).get(pk=pk)
    order_values = rows(SalesOrder.objects.filter(pk=order.pk),
        'id', 'code', 'status', 'due_date', 'owner_id', 'owner__full_name')[0]
    lines = rows(SalesLine.objects.filter(order=order),
        'id', 'item_id', 'item__code', 'item__name', 'item__unit', 'revision', 'quantity', 'shipped')
    line_ids = [row['id'] for row in lines]
    cancellations = rows(OrderCancellation.objects.filter(line_id__in=line_ids),
        'id', 'line_id', 'quantity', 'created_at')
    reservations = rows(Reservation.objects.filter(line_id__in=line_ids),
        'id', 'line_id', 'lot_id', 'quantity')
    shipments = rows(Movement.objects.filter(line_id__in=line_ids, kind='shipment'),
        'id', 'line_id', 'lot_id', 'purchase_id', 'production_id', 'quantity', 'created_at')
    lots = sorted({row['lot_id'] for row in reservations + shipments})
    receipts = rows(Movement.objects.filter(lot_id__in=lots, kind='receipt'),
        'id', 'lot_id', 'purchase_id', 'production_id', 'line_id', 'quantity', 'created_at')
    jobs = rows(Production.objects.filter(line_id__in=line_ids),
        'id', 'code', 'line_id', 'status', 'due_date', 'owner_id', 'owner__full_name')
    tasks = rows(Task.objects.filter(sales_order=order),
        'id', 'title', 'status', 'deadline', 'assignee_employee_id', 'assignee_employee__full_name')
    invoices = rows(InvoiceLink.objects.filter(order=order),
        'id', 'invoice_id', 'invoice__code', 'invoice__currency', 'invoice__due_date')
    source = {'order': order_values, 'lines': lines, 'cancellations': cancellations,
              'reservations': reservations, 'shipments': shipments, 'receipts': receipts,
              'jobs': jobs, 'tasks': tasks, 'invoices': invoices, 'admission': [],
              'task_sources': [(obj.pk, task_source_refs(obj)) for obj in
                               Task.objects.filter(pk__in=[row['id'] for row in tasks]).order_by('pk')]}
    visible = {name: admitted(policy, model, values) for name, model, values in (
        ('lines', SalesLine, lines), ('cancellations', OrderCancellation, cancellations),
        ('reservations', Reservation, reservations), ('shipments', Movement, shipments),
        ('receipts', Movement, receipts), ('jobs', Production, jobs), ('invoices', InvoiceLink, invoices))}
    # Policy.tasks() includes historical source refs; a direct Task scope is not sufficient.
    visible['tasks'] = set(policy.tasks().filter(sales_order=order).values_list('pk', flat=True))
    source['visible'] = {key: sorted(value) for key, value in visible.items()}
    restricted = any(len(source[key]) != len(visible[key]) for key in visible)
    partial = False
    by_cancel = grouped(cancellations, 'line_id')
    by_reserve = grouped(reservations, 'line_id')
    by_ship = grouped(shipments, 'line_id')
    by_receipt = grouped(receipts, 'lot_id')
    lot_models = {obj.pk: obj for obj in policy.queryset(Lot).filter(pk__in=lots).select_related('item')}
    line_dtos = []
    for line in lines:
        if line['id'] not in visible['lines']:
            continue
        cs, rs, ss = by_cancel[line['id']], by_reserve[line['id']], by_ship[line['id']]
        allowed_c = [value for value in cs if value['id'] in visible['cancellations']]
        allowed_r = [value for value in rs if value['id'] in visible['reservations']]
        allowed_s = [value for value in ss if value['id'] in visible['shipments']]
        line_restricted = len(cs) != len(allowed_c) or len(rs) != len(allowed_r) or len(ss) != len(allowed_s)
        cancelled = sum((value['quantity'] for value in allowed_c), Decimal(0)) if len(cs) == len(allowed_c) else None
        opened = line['quantity'] - line['shipped'] - cancelled if cancelled is not None else None
        if opened is not None and opened < 0:
            raise ValueError('Історія скасувань перевищує потребу продажу.')
        reserve_refs = []
        usable_reserved = Decimal(0) if len(rs) == len(allowed_r) else None
        for reservation in allowed_r:
            lot = lot_models.get(reservation['lot_id'])
            if lot is None:
                # Fail closed even if an inconsistent Policy admits the edge only.
                line_restricted = True; usable_reserved = None
                continue
            usable, dependency = lot_admission(policy, lot, line['revision'])
            source['admission'].append(dependency)
            if usable is None:
                line_restricted = True; usable_reserved = None
            elif usable_reserved is not None and usable:
                usable_reserved += reservation['quantity']
            reserve_refs.append({'id': reservation['id'], 'lot_id': lot.pk,
                                 'quantity': quantity_text(reservation['quantity']), 'usable': usable})
        origins = []
        visible_lots = {row['lot_id'] for row in allowed_r + allowed_s}
        for lot_id in sorted(visible_lots):
            for receipt in by_receipt[lot_id]:
                if receipt['id'] not in visible['receipts']:
                    line_restricted = True
                    continue
                if receipt['purchase_id'] is not None:
                    # Movement Policy checks its direct purchase FK, never item similarity.
                    origins.append({'relation': 'lot_origin', 'lot_id': lot_id,
                                    'receipt_id': receipt['id'], 'purchase_id': receipt['purchase_id']})
        refs = {
            'cancellations': [{'id': row['id'], 'quantity': quantity_text(row['quantity']),
                              'created_at': row['created_at']} for row in allowed_c],
            'reservations': reserve_refs,
            'shipments': [{'id': row['id'], 'lot_id': row['lot_id'],
                           'quantity': quantity_text(row['quantity']), 'created_at': row['created_at']} for row in allowed_s],
            'lot_origins': origins,
        }
        has_more = {}
        for key in refs:
            refs[key], has_more[key] = cap(refs[key])
        line_partial = any(has_more.values())
        refs['line'] = {'type': 'sales_line', 'id': line['id']}
        line_dtos.append({'line_id': line['id'], 'item': {'id': line['item_id'], 'code': line['item__code'],
            'name': line['item__name'], 'unit': line['item__unit']}, 'revision': line['revision'],
            'ordered': quantity_text(line['quantity']), 'shipped': quantity_text(line['shipped']),
            'cancelled': quantity_text(cancelled) if cancelled is not None else None,
            'open': quantity_text(opened) if opened is not None else None,
            'usable_reserved': quantity_text(usable_reserved) if usable_reserved is not None else None,
            'source_refs': refs, 'basis': BASIS, 'has_more': has_more,
            'completeness': 'restricted' if line_restricted else 'partial' if line_partial else 'complete'})
        restricted |= line_restricted
        partial |= line_partial
    job_dtos = [{'id': row['id'], 'code': row['code'], 'line_id': row['line_id'], 'status': row['status'],
                 'due_date': row['due_date'], 'owner': person(row['owner_id'], row['owner__full_name'], 'job_owner')}
                for row in jobs if row['id'] in visible['jobs']]
    task_dtos = [{'id': row['id'], 'title': row['title'], 'status': row['status'], 'deadline': row['deadline'],
                  'assignee': person(row['assignee_employee_id'], row['assignee_employee__full_name'], 'task_assignee')}
                 for row in tasks if row['id'] in visible['tasks']]
    invoice_dtos = [{'invoice_id': row['invoice_id'], 'code': row['invoice__code'],
                    'currency': row['invoice__currency'], 'due_date': row['invoice__due_date']}
                   for row in invoices if row['id'] in visible['invoices']]
    capped = [cap(values) for values in (line_dtos, job_dtos, task_dtos, invoice_dtos)]
    more = dict(zip(('lines', 'jobs', 'tasks', 'invoices'), (value[1] for value in capped)))
    partial |= any(more.values())
    source['as_of'] = str(as_of())
    result = {'schema': SCHEMA, 'order': {'id': order.pk, 'code': order_values['code'],
        'status': order_values['status'], 'due_date': order_values['due_date'],
        'owner': person(order_values['owner_id'], order_values['owner__full_name'], 'order_owner')},
        'as_of': source['as_of'], 'scope': {'order_id': order.pk, 'purchase_allocation': 'not_recorded',
            'message': 'Призначення очікуваних закупівель цьому замовленню не зафіксовано'},
        'lines': capped[0][0], 'linked_jobs': capped[1][0], 'linked_tasks': capped[2][0],
        'linked_invoice_refs': capped[3][0], 'limits': {'per_section': LIMIT, 'has_more': more},
        'completeness': 'restricted' if restricted else 'partial' if partial else 'complete'}
    if restricted:
        result['scope']['explanation'] = RESTRICTED
    return serial(result), digest(source)


def build(request, pk):
    first_policy = Policy(request)
    first_access = first_policy.access_revision()
    if getattr(request, 'bos_access_revision', first_access) != first_access:
        raise ReadStateChanged()
    before = write_revision()
    body, first_digest = collect(first_policy, pk)
    middle = write_revision()
    second_policy = Policy(request)
    if second_policy.access_revision() != first_access:
        raise ReadStateChanged()
    try:
        _, second_digest = collect(second_policy, pk)
    except ObjectDoesNotExist:
        raise ReadStateChanged() from None
    final_policy = Policy(request)
    final_access = final_policy.access_revision()
    after = write_revision()
    if before != middle or middle != after or first_digest != second_digest or first_access != final_access:
        raise ReadStateChanged()
    request.bos_access_revision = final_access
    body['access_revision'] = final_access
    body['generated_at'] = timezone.now().isoformat()
    return body
