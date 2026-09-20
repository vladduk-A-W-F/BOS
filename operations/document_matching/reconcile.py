"""One full-PO, one-item invoice against explicit candidates and receipt facts.

No DB, filesystem, network, provider invocation or business operation. Access
and original-byte verification are obligations of the future server adapter.
Receipts are original purchase movements; returns must be linked by the adapter.
The current remaining stock is deliberately not an input to invoice matching.
"""
from copy import deepcopy
from decimal import Context, Decimal, localcontext, ROUND_HALF_EVEN

from . import contract as c
from .mock_adapter import extract_mock


def reconcile(draft, context):
    c.context(context)
    result = {'schema': c.SCHEMA, 'provider': c.PROVIDER, 'source': None, 'fields': None,
              'matches': None, 'comparison': None, 'exceptions': [],
              'decision': 'needs_information', 'operation_proposal': None}
    def issue(code):
        if code not in result['exceptions']:
            result['exceptions'].append(code)
    if context['access'] == 'restricted':
        issue('restricted')
        return result
    try:
        c.draft(draft, context['source'])
    except c.ContractError as exc:
        if exc.code != 'source_changed':
            raise
        issue('source_changed')
        result['decision'] = 'reject_draft'
        return result
    result['source'] = deepcopy(draft['source'])
    c.require(draft == extract_mock(context['source']), 'mock_evidence_mismatch')
    if draft['state'] != 'extracted':
        result['exceptions'] = list(draft['exceptions'])
        return result
    result['fields'] = deepcopy(draft['fields'])
    fields = draft['fields']; line = fields['lines'][0]
    supplier_ids = sorted(row['id'] for row in context['suppliers']
                          if row['type'] == 'supplier' and row['is_active']
                          and row['edrpou'] == fields['supplier_edrpou']['value'])
    item_ids = sorted(row['id'] for row in context['items']
                      if row['code'] == line['item_code']['value']
                      and row['revision'] == line['revision']['value'] and row['unit'] == line['unit']['value'])
    selected = context['selection']
    result['matches'] = {'supplier_candidate_ids': supplier_ids, 'item_candidate_ids': item_ids,
                         'supplier_id': None, 'item_id': None, 'purchase_id': None, 'receipt_ids': []}
    for name, candidates in (('supplier', supplier_ids), ('item', item_ids)):
        chosen = selected[name + '_id']
        if not candidates:
            issue(name + '_missing')
        elif chosen is None:
            issue(name + ('_ambiguous' if len(candidates) > 1 else '_selection_required'))
        elif chosen not in candidates:
            issue(name + '_selection_mismatch')
        else:
            result['matches'][name + '_id'] = chosen
    purchase = context['purchase']
    if purchase is None:
        issue('purchase_missing')
        return result
    if selected['purchase_id'] != purchase['id']:
        issue('purchase_selection_mismatch')
    else:
        result['matches']['purchase_id'] = purchase['id']
    for key in ('supplier_id', 'item_id'):
        if purchase[key] != result['matches'][key]:
            issue('purchase_' + key.removesuffix('_id') + '_mismatch')
    for key in ('revision', 'unit'):
        if purchase[key] != line[key]['value']:
            issue(key + '_mismatch')
    if purchase['currency'] != fields['currency']['value']:
        issue('currency_mismatch')
    if fields['tax_basis']['value'] != 'excluding_VAT':
        issue('unsupported_tax_basis')
    if Decimal(purchase['extras']) != 0:
        issue('unsupported_extras')
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        quantity = Decimal(line['quantity']['value']); ordered = Decimal(purchase['quantity'])
        price = Decimal(line['unit_price']['value']); po_price = Decimal(purchase['price'])
        line_total = Decimal(line['line_total']['value']); total = Decimal(fields['total']['value'])
        calculated = (quantity * price).quantize(Decimal('0.01'))
        c.require(calculated <= Decimal('9999999999999.99'), 'decimal_range')
        if quantity != ordered:
            issue('full_purchase_quantity_mismatch')
        if price != po_price:
            issue('price_mismatch')
        if line_total != calculated:
            issue('line_total_mismatch')
        if total != line_total:
            issue('invoice_total_mismatch')
        gross = Decimal(0); returned = Decimal(0)
        receipt_ids = []
        for receipt in context['receipts']:
            if any(receipt[key] != purchase[key] for key in ('item_id', 'revision', 'unit', 'currency')) or receipt['purchase_id'] != purchase['id']:
                issue('receipt_source_mismatch')
                continue
            gross += Decimal(receipt['quantity'])
            returned += Decimal(receipt['returned_quantity'])
            receipt_ids.append(receipt['id'])
        net = gross - returned
        result['matches']['receipt_ids'] = sorted(receipt_ids)
        if gross > ordered:
            issue('receipt_overage')
        if net != quantity:
            issue('received_quantity_mismatch')
        def pair(invoice, expected, places):
            return {'invoice': c.formatted(invoice, places), 'expected': c.formatted(expected, places),
                    'difference': c.formatted(invoice - expected, places)}
        same_unit = purchase['unit'] == line['unit']['value']
        same_currency = purchase['currency'] == fields['currency']['value']
        result['comparison'] = {
            'invoice_currency': fields['currency']['value'], 'purchase_currency': purchase['currency'],
            'invoice_unit': line['unit']['value'], 'purchase_unit': purchase['unit'],
            'quantity': pair(quantity, ordered, 3) if same_unit else None,
            'price': pair(price, po_price, 2) if same_unit and same_currency else None,
            'line_total': pair(line_total, calculated, 2),
            'invoice_total': pair(total, line_total, 2), 'receipt_quantity': {
                'gross': c.formatted(gross, 3), 'returned': c.formatted(returned, 3),
                'net': c.formatted(net, 3), 'invoice': c.formatted(quantity, 3),
                'difference': c.formatted(net - quantity, 3) if same_unit else None}}
    if not result['exceptions']:
        result['decision'] = 'accept_draft'
    return result
