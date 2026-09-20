"""Read-only, unallocated supply options for one purchased sales item.

A purchase has no destination/order allocation unless linked to a production
job. Expected receipts therefore remain an indication, never promised stock.
All writes still belong to the existing ERP preview/confirm commands.
"""
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from boss_project.policy import Policy
from . import service
from .balances import exact, purchase_open, quantity_text, sales_open
from .models import Location, Lot, Purchase, Reservation, SalesLine
from .order_trace import ReadStateChanged, digest, serial, write_revision

LIMIT = 100
ZERO = Decimal(0)
SCHEMA = 'bos.supply-options.v1'


def identifier(value, *, optional=False):
    if optional and value is None:
        return None
    if type(value) is not int or value <= 0:
        raise ValueError('Потрібен додатний цілий ідентифікатор.')
    return value


def location_row(location):
    return {'id': location.pk, 'code': location.code, 'name': location.name,
            'branch_id': location.branch_id}


@exact
def collect(policy, line_id, target_location_id=None):
    line = policy.queryset(SalesLine).select_related('item', 'order').get(pk=line_id)
    item, order = line.item, line.order
    locations = {row.pk: row for row in policy.queryset(Location).order_by('pk')}
    target = locations.get(target_location_id)
    if target_location_id is not None and target is None:
        raise Location.DoesNotExist('Запис недоступний.')
    supported = item.method == 'buy' and order.status == 'confirmed'
    remaining = sales_open(line)
    visible_reserves = list(policy.queryset(Reservation).filter(line=line).select_related('lot__item'))
    own_visible = sum((r.quantity for r in visible_reserves), ZERO)
    # A hidden reservation must not become an inferred available balance.
    own_usable = (sum((r.quantity for r in visible_reserves if service.usable(r.lot, line.revision)), ZERO)
                  if policy.ceo else None)
    need = max(remaining - own_usable, ZERO) if policy.ceo else None
    stock, waiting, purchases = [], [], []
    free_total = local_free = incoming = ZERO
    for lot in policy.queryset(Lot).filter(item=item, quantity__gt=0).select_related('item').order_by('pk'):
        location = locations.get(lot.location_id)
        if location is None:
            continue
        related = ('target' if target and location.pk == target.pk else
                   'other_location' if target else
                   'order_branch' if location.branch_id is not None and location.branch_id == order.branch_id else
                   'other_or_unassigned_branch')
        row = {'lot_id': lot.pk, 'code': lot.code, 'location': location_row(location),
               'relation': related, 'revision': lot.revision, 'quality': lot.quality,
               'quantity': quantity_text(lot.quantity), 'unit': item.unit,
               'available': None, 'eligible': None, 'reason': 'availability_restricted',
               'document_ids': sorted(set(lot.documents.values()))}
        if policy.ceo:
            good = service.usable(lot, line.revision)
            amount = max(service.free(lot), ZERO) if good else ZERO
            row.update(available=quantity_text(amount), eligible=good and amount > 0)
            if lot.revision != line.revision:
                row['reason'] = 'revision_mismatch'
            elif lot.quality != 'approved':
                row['reason'] = 'quality_' + lot.quality
            elif not good:
                row['reason'] = 'document_admission_required'
            elif amount <= 0:
                row['reason'] = 'fully_reserved'
            else:
                row['reason'] = 'available'
            if good and amount > 0:
                free_total += amount
                if target and location.pk == target.pk:
                    local_free += amount
                stock.append(row)
            else:
                waiting.append(row)
        else:
            # One neutral list: classification itself must not leak a hidden
            # latest document version, reservation or its effect on availability.
            stock.append(row)
    for po in policy.queryset(Purchase).filter(item=item).select_related('production').order_by('due_date', 'pk'):
        amount = purchase_open(po)
        if amount <= 0:
            continue
        usable_for_line = po.revision == line.revision and po.production_id is None
        row = {'purchase_id': po.pk, 'code': po.code, 'revision': po.revision,
               'unit': item.unit, 'open_quantity': quantity_text(amount),
               'due_date': po.due_date.isoformat(), 'currency': po.currency,
               'allocation': 'not_recorded' if po.production_id is None else 'production',
               'eligible_as_unallocated_expectation': usable_for_line,
               'reason': 'revision_mismatch' if po.revision != line.revision else
                         'allocated_to_production' if po.production_id else 'unallocated_expected_receipt'}
        purchases.append(row)
        if usable_for_line:
            incoming += amount
    uncovered = max(need - free_total, ZERO) if policy.ceo else None
    quantity = lambda value: quantity_text(value) if value is not None else None
    totals = {'remaining': quantity(remaining), 'reserved_visible': quantity(own_visible),
              'reserved_usable': quantity(own_usable), 'quantity_to_cover': quantity(need),
              'available_all_locations': quantity(free_total if policy.ceo else None),
              'available_target': quantity(local_free if policy.ceo and target else None),
              'target_gap': quantity(max(need - local_free, ZERO) if policy.ceo and target else None),
              'uncovered_after_stock': quantity(uncovered),
              'unallocated_expected': quantity(incoming if policy.ceo else None),
              'indicative_after_expected': quantity(max(uncovered - incoming, ZERO) if policy.ceo else None)}
    sections = {'stock': stock, 'waiting': waiting, 'purchases': purchases}
    return serial({'schema': SCHEMA, 'scope': 'visible_sources',
        'line': {'id': line.pk, 'order_id': order.pk, 'item_id': item.pk, 'item_code': item.code,
                 'revision': line.revision, 'unit': item.unit, 'order_branch_id': order.branch_id},
        'target_location': location_row(target) if target else None,
        'target_required_for_transfer': target is None, 'supported': supported,
        'reason': None if supported else 'requires_confirmed_order_and_purchased_item',
        'quantities': totals, **{key: values[:LIMIT] for key, values in sections.items()},
        'limits': {'per_section': LIMIT, 'has_more': {key: len(values) > LIMIT for key, values in sections.items()},
                   'totals_include_all_visible_sources': policy.ceo},
        'completeness': 'complete' if policy.ceo else 'restricted',
        'operation_proposal': None,
        'basis': 'Потреба після придатного резерву цього замовлення. Вільні партії можуть бути в іншій точці; '
                 'вибір місця явний. Відкриті закупівлі не розподілені цьому замовленню, не є гарантованим '
                 'залишком і можуть бути потрібні іншим замовленням. Строки та фактичну поставку перевіряйте окремо. '
                 'Переміщення зберігає якість; нове приймання потребує її перевірки.'})


def build(request, line_id, target_location_id=None):
    identifier(line_id)
    identifier(target_location_id, optional=True)
    first = Policy(request)
    access = first.access_revision()
    if getattr(request, 'bos_access_revision', access) != access:
        raise ReadStateChanged()
    revision_before = write_revision()
    before = service.fingerprint()
    body = collect(first, line_id, target_location_id)
    revision_middle = write_revision()
    second = Policy(request)
    if second.access_revision() != access:
        raise ReadStateChanged()
    try:
        after = collect(second, line_id, target_location_id)
    except ObjectDoesNotExist:
        raise ReadStateChanged() from None
    final_fingerprint = service.fingerprint()
    final_access = Policy(request).access_revision()
    revision_after = write_revision()
    if (revision_before != revision_middle or revision_middle != revision_after or
            digest(body) != digest(after) or before != final_fingerprint or final_access != access):
        raise ReadStateChanged()
    request.bos_access_revision = access
    body.update(access_revision=access, generated_at=timezone.now().isoformat())
    return body
