"""Explicit response projections; raw financial/history payloads stay server-side."""
from copy import deepcopy
from boss_project.policy import Policy, CEO_ACTIONS
from django.core.exceptions import ObjectDoesNotExist

ERP_FIELDS = {
    'tasks':'title category priority assignee_id deadline order_id status result archived is_overdue',
    'items': 'id code name unit kind method revision document_id material external_codes required_documents bom routing minimum lead_days currency',
    'locations': 'id code name kind supplier_id branch_id',
    'lots': 'id code item_id location_id revision quantity quality currency documents reserved available missing_documents',
    'orders': 'id code customer_id owner_id due_date currency status branch_id',
    'lines': 'id order_id item_id revision quantity shipped invoiced',
    'jobs': 'id code line_id item_id quantity produced revision bom routing location_id owner_id due_date status needs_review currency',
    'reservations': 'id lot_id line_id production_id quantity',
    'purchases': 'id code item_id supplier_id quantity received currency due_date original_due revision production_id request_id quote_id approval_snapshot status',
    'inspections': 'id lot_id result inspector_id created_at',
    'changes': 'id code item_id document_id target_revision status created_at',
    'operator_entries': 'id production_id operation operator_id result minutes defects created_at',
    'movements': 'id lot_id quantity kind reference line_id production_id purchase_id created_at',
    'invoices': 'invoice_id order_id code due_date currency',
}

ERP_FIELDS['lines'] += ' cancelled_quantity open_quantity returned_quantity return_visibility'
ERP_FIELDS['purchases'] += ' cancelled_quantity open_quantity returned_quantity effective_status return_visibility'
ERP_FIELDS.update({
 'source_movements':'id kind lot_id lot_code item_id location_id line_id purchase_id quantity revision currency reference created_at',
 'cancellations':'id operation_id code line_id purchase_id quantity business_date created_at event_id',
 'cancellation_releases':'id cancellation_id reservation_id quantity before_quantity after_quantity',
 'goods_returns':'id operation_id code direction source_id result_id lot_id source_lot_id line_id purchase_id quantity source_quantity currency business_date created_at event_id',
 'supplier_claims':'id record_kind return_id parent_id code currency business_date created_at event_id confirmed_by_id',
 'invoice_adjustments':'','invoice_adjustment_lines':''})


def select(row, fields):
    return {k: row[k] for k in fields if k in row}


def snapshot(policy, data):
    if policy.ceo:
        return data
    data = deepcopy(data)
    for name, fields in ERP_FIELDS.items():
        allowed = fields.split()
        if policy.role == 'manager' and name == 'purchases':
            allowed += ['price', 'extras']
        if policy.role == 'manager' and name == 'lines':
            allowed += ['price']
        data[name] = [select(x, allowed) for x in data.get(name, [])] if allowed else []
        if name == 'purchases' and policy.role == 'observer':
            for row in data[name]:
                source = row.get('approval_snapshot')
                if isinstance(source, dict):
                    public = select(source, ('source','request_id','request_code','quote_id','quote_code','batch_id','external_id','source_order_code','source_line_id'))
                    public['source_documents'] = {kind:select(document, ('document_id','code'))
                        for kind,document in source.get('source_documents',{}).items()}
                    row['approval_snapshot'] = public
    # Events contain arbitrary prior payloads. Non-CEO history uses metadata
    # only, after checking every referenced object with today's permissions.
    events = []
    for row in data.get('events', [])+data.get('correction_events', []):
        if row['action'] in CEO_ACTIONS:
            continue
        try:
            policy.check_payload(row.get('payload', {}))
            if row['action'] in __import__('erp.corrections',fromlist=['ACTIONS']).ACTIONS:policy.check_payload(row.get('result', {}))
        except (PermissionError, ObjectDoesNotExist):
            continue
        events.append(select(row, ('id', 'action', 'role', 'created_at')))
    data['events'] = list({row['id']:row for row in events if row['id'] in {x['id'] for x in data.get('events',[])}}.values())
    data['correction_events'] = list({row['id']:row for row in events if row['id'] in {x['id'] for x in data.get('correction_events',[])}}.values())
    data.pop('costs', None)
    data.pop('home', None)
    return data


def summary(policy, data):
    if policy.ceo:
        return data
    tasks = set(policy.tasks().values_list('pk', flat=True))
    return {'as_of': data['as_of'], 'overdue_tasks': [x for x in data['overdue_tasks'] if x['id'] in tasks]}


def comparison(policy, data):
    policy.requests().get(code=data['request']['code'])
    quote_codes = set(policy.quotes().values_list('code', flat=True))
    data = deepcopy(data)
    data['rows'] = [x for x in data['rows'] if x['code'] in quote_codes]
    data['request']['allocation_visibility'] = 'complete'
    if not policy.ceo:
        from erp.models import Purchase
        linked = Purchase.objects.filter(request__code=data['request']['code'])
        if linked.exclude(pk__in=policy.queryset(Purchase).values('pk')).exists():
            data['request'].update(allocated_quantity=None, remaining_quantity=None,
                                   allocation_visibility='restricted')
    if policy.role == 'observer':
        for row in data['rows']:
            row.pop('total', None)
            row['terms'] = select(row['terms'], ('revision', 'lead_weeks', 'valid_until', 'moq', 'coating_included', 'material_certificate'))
        data['recommended'] = None
    else:
        from decimal import Decimal
        eligible = [x for x in data['rows'] if not x['reasons']]
        data['recommended'] = min(eligible, key=lambda x: Decimal(x['total']))['code'] if eligible else None
    return data


def audit(policy, rows):
    if policy.ceo:
        return list(rows)
    result = []
    for row in rows:
        if row['action'].startswith(('salary.', 'transaction.', 'employee.', 'identity.')) or row['action'] in CEO_ACTIONS:
            continue
        if row['action'].startswith('chatmessage.') and row['payload'].get('actor_id') != policy.actor.user_id:
            continue
        try:
            policy.check_payload(row['payload'])
            if row['task_id']:
                policy.tasks().get(pk=row['task_id'])
        except (PermissionError, ObjectDoesNotExist):
            continue
        result.append(select(row, ('id', 'action', 'task_id', 'created_at')))
    return result


def receipt(policy, value):
    if policy.ceo:
        return value
    # The input can remain visible after the created output changes scope.
    # Check today's output identities before disclosing a stored receipt.
    policy.check_payload(value)
    from erp.corrections import ACTIONS as CORRECTIONS
    if value.get('action') in CORRECTIONS:
        allowed={'state','action','operation_id','erp_event_id','actor_role','impact','prospective','cancellation_id','line_id','purchase_id','cancelled_quantity','effective_open','released',
            'goods_return_id','receipt_id','shipment_id','movement_id','lot_id','claim_id','quantity','currency'}
        out=select(deepcopy(value),allowed)
        out['released']=[select(row,('reservation_id','quantity','before_quantity','after_quantity')) for row in out.get('released',[])] if 'released' in out else []
        if 'released' not in value:out.pop('released',None)
    else:out = deepcopy(value)
    out.pop('cost', None)
    out.pop('amount', None)
    out.pop('paid', None)
    references = {'tasks':'task_id','items': 'item_id', 'lots': 'lot_id', 'orders': 'order_id',
                  'lines': 'line_id', 'jobs': 'production_id', 'purchases': 'purchase_id',
                  'changes': 'change_id', 'reservations': 'reservation_id', 'invoices': 'invoice_id',
                  'cancellations':'cancellation_id','goods_returns':'goods_return_id','supplier_claims':'claim_id','source_movements':'movement_id'}
    impact = []
    for row in out.get('impact', []):
        if row.get('field') not in ERP_FIELDS.get(row.get('kind'), '').split():
            continue
        name = references.get(row.get('kind'))
        if name:
            policy.check_reference(name, row['id'])
        # Legacy display strings contain no machine-verifiable referenced IDs.
        # Keep the historical receipt intact, disclose only the change label.
        if row.get('field') in ('bom', 'documents', 'routing'):
            row = {**row, 'before': 'Збережено в історії', 'after': 'Перегляньте поточну доступну версію'}
        impact.append(row)
    out['impact'] = impact
    return out
