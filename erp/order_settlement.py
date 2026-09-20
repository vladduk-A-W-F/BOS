"""CEO-only, order-scoped current settlement and durable payment sources.

The existing amount-free order trace is deliberately unchanged. This is an
optimistic double read, not an atomic snapshot or a cash/bank balance. Returned
source lists are bounded; all scoped rows still contribute to the balances.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from boss_project.policy import Policy
from operations.models import Invoice
from .balances import exact, invoice_settlement, money_text
from .models import Event, InvoiceAdjustment, InvoiceLink, SalesOrder
from .order_trace import ReadStateChanged, digest, serial, write_revision

SCHEMA = 'bos.order-settlement.v1'
LIMIT = 100
MONEY_FIELDS = ('gross_invoiced', 'credited', 'invoiced', 'paid', 'open', 'customer_credit')
BASIS = ('Поточні пов’язані рахунки після чинних кредитів і сторнування; '
         'оплачено — облікове поле рахунку. Історія оплат звіряється окремо. '
         'Валюти не конвертуються; це не залишок коштів і не підтвердження банку.')


def require_ceo(policy):
    # This guard precedes order lookup and every financial/source query.
    if not policy.ceo:
        raise PermissionError('Фінансовий розрахунок недоступний для цієї ролі.')


def payment_value(value):
    """Validate legacy JSON without float arithmetic or silently rounding it."""
    if type(value) not in (str, int, float) or len(str(value)) > 64:
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    if (not amount.is_finite() or amount <= 0 or amount > Decimal('999999999999.99')
            or amount.as_tuple().exponent < -2):
        return None
    return amount


@exact
def payment_history(invoice, events):
    entries, issues, references = [], set(), set()
    recorded = Decimal(0)
    for event in events:
        problems = []
        raw_id, raw_reference = event['payload__invoice_id'], event['payload__reference']
        amount = payment_value(event['payload__amount'])
        if type(raw_id) is not int or raw_id != invoice.pk:
            problems.append('invalid_invoice_id')
        if amount is None:
            problems.append('invalid_amount')
        # The existing writer treats reference as an exact opaque key.
        # Trimming here would merge distinct, valid payment confirmations.
        reference = raw_reference if isinstance(raw_reference, str) else None
        if not reference or not 1 <= len(reference.strip()) <= 60 or len(reference) > 4000:
            reference = None
            problems.append('invalid_reference')
        if reference is not None:
            if reference in references:
                problems.append('duplicate_reference')
            references.add(reference)
        if not problems:
            recorded += amount
        else:
            issues.add('invalid_history')
        entries.append({'event_id': event['id'], 'invoice_id': invoice.pk,
                        'amount': money_text(amount) if amount is not None else None,
                        'currency': invoice.currency, 'reference': reference,
                        'created_at': event['created_at'], 'issues': problems})
    difference = invoice.paid - recorded
    if not events and invoice.paid:
        issues.add('missing_history')
    if difference:
        issues.add('sum_mismatch')
    status = 'missing' if 'missing_history' in issues else 'inconsistent' if issues else 'complete'
    return {'status': status, 'recorded_total': money_text(recorded),
            'invoice_paid': money_text(invoice.paid), 'difference': money_text(difference),
            'issues': sorted(issues), 'entries': entries[:LIMIT], 'has_more': len(entries) > LIMIT}


@exact
def collect(policy, order_id):
    require_ceo(policy)
    order = policy.queryset(SalesOrder).get(pk=order_id)
    links = list(policy.queryset(InvoiceLink).filter(order=order).order_by('pk').values('id', 'invoice_id'))
    # A partial financial ledger must not look like a full order balance. Current
    # CEO policy admits these rows; explicitly retain the check at each edge.
    if len(links) != InvoiceLink.objects.filter(order=order).count():
        raise PermissionError('Розрахунок недоступний у поточному доступі.')
    invoice_ids = [row['invoice_id'] for row in links]
    invoices = list(policy.queryset(Invoice).filter(pk__in=invoice_ids).order_by('pk'))
    if len(invoices) != len(invoice_ids):
        raise PermissionError('Розрахунок недоступний у поточному доступі.')
    credit_rows = list(policy.queryset(InvoiceAdjustment).filter(invoice_id__in=invoice_ids)
                       .order_by('pk').values('id', 'code', 'invoice_id', 'kind', 'total', 'currency',
                                             'reversed_credit_id', 'reversal__id', 'created_at'))
    if len(credit_rows) != InvoiceAdjustment.objects.filter(invoice_id__in=invoice_ids).count():
        raise PermissionError('Розрахунок недоступний у поточному доступі.')
    # Numeric-string IDs are legacy malformed records: include them for explicit
    # reconciliation failure, never silently treat them as a valid payment.
    events = policy.queryset(Event).filter(action='erp_payment',
                      payload__invoice_id__in=invoice_ids + [str(pk) for pk in invoice_ids])
    # Selecting JSON key transforms in SQLite can decode a numeric string as a
    # number. Preserve original JSON types, then retain only consumed fields.
    event_rows = [{'id': row['id'], 'created_at': row['created_at'],
                   **{'payload__' + key: row['payload'].get(key)
                      for key in ('invoice_id', 'amount', 'reference')}}
                  for row in events.order_by('pk').values('id', 'created_at', 'payload')
                  if isinstance(row['payload'], dict)] if invoice_ids else []
    credits, payments = defaultdict(list), defaultdict(list)
    credit_ids = {row['id'] for row in credit_rows}
    invoice_id_set, invoice_id_strings = set(invoice_ids), {str(pk) for pk in invoice_ids}
    for row in credit_rows:
        credits[row['invoice_id']].append(row)
    for row in event_rows:
        # Query scope is verified again before associating an event. In
        # particular a JSON boolean must never alias integer invoice ID 1.
        value = row['payload__invoice_id']
        if type(value) is int or (type(value) is str and value in invoice_id_strings):
            if int(value) in invoice_id_set:
                payments[int(value)].append(row)
    source = {'order': {'id': order.pk, 'code': order.code, 'status': order.status},
              'links': links, 'invoices': [], 'credits': credit_rows, 'payments': event_rows}
    totals, invoice_dtos = {}, []
    incomplete = partial = False
    link_by_invoice = {row['invoice_id']: row['id'] for row in links}
    for invoice in invoices:
        settlement = invoice_settlement(invoice)
        values = dict(zip(MONEY_FIELDS, (invoice.amount, settlement['effective_credit'],
                      settlement['net_amount'], invoice.paid, settlement['receivable'],
                      settlement['customer_credit'])))
        group = totals.setdefault(invoice.currency, {key: Decimal(0) for key in MONEY_FIELDS})
        for key, value in values.items():
            group[key] += value
        history = payment_history(invoice, payments[invoice.pk])
        adjustments = [{'adjustment_id': row['id'], 'code': row['code'], 'kind': row['kind'],
                        'amount': money_text(row['total']), 'currency': row['currency'],
                        'active': row['kind'] == 'credit' and row['reversal__id'] is None,
                        'reversed_credit_id': row['reversed_credit_id'] if row['reversed_credit_id'] in credit_ids else None,
                        'created_at': row['created_at']} for row in credits[invoice.pk]]
        more = {'payments': history['has_more'], 'adjustments': len(adjustments) > LIMIT}
        partial |= any(more.values())
        incomplete |= history['status'] != 'complete'
        invoice_dtos.append({'invoice_id': invoice.pk, 'invoice_link_id': link_by_invoice[invoice.pk],
                             'code': invoice.code, 'currency': invoice.currency, 'due_date': invoice.due_date,
                             **{key: money_text(value) for key, value in values.items()},
                             'payment_history': history, 'adjustments': adjustments[:LIMIT], 'has_more': more})
        source['invoices'].append({'id': invoice.pk, 'code': invoice.code, 'currency': invoice.currency,
                                   'due_date': invoice.due_date, **values})
    more_invoices = len(invoice_dtos) > LIMIT
    partial |= more_invoices
    body = {'schema': SCHEMA, 'order': source['order'], 'scope': 'linked_invoices', 'basis': BASIS,
            'totals': [{'currency': currency, **{key: money_text(value) for key, value in totals[currency].items()}}
                       for currency in sorted(totals)], 'invoices': invoice_dtos[:LIMIT],
            'payment_history_status': 'incomplete' if incomplete else 'complete',
            'limits': {'per_section': LIMIT, 'has_more': {'invoices': more_invoices},
                       'totals_scope': 'all_linked_invoices', 'payment_reconciliation_scope': 'all_scoped_events'},
            'completeness': 'incomplete_history' if incomplete else 'partial' if partial else 'complete'}
    return serial(body), digest(source)


def build(request, order_id):
    first = Policy(request)
    require_ceo(first)
    access = first.access_revision()
    if getattr(request, 'bos_access_revision', access) != access:
        raise ReadStateChanged()
    before = write_revision()
    body, first_digest = collect(first, order_id)
    middle = write_revision()
    second = Policy(request)
    if second.access_revision() != access:
        raise ReadStateChanged()
    try:
        _, second_digest = collect(second, order_id)
    except (ObjectDoesNotExist, PermissionError):
        raise ReadStateChanged() from None
    final_access = Policy(request).access_revision()
    after = write_revision()
    if before != middle or middle != after or first_digest != second_digest or access != final_access:
        raise ReadStateChanged()
    request.bos_access_revision = final_access
    body.update(access_revision=final_access, generated_at=timezone.now().isoformat())
    return body
