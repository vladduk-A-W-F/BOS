"""Gate 7 additive B03 fixture: actual HTTPS commands, never ORM or live data."""
import hashlib
import json
from uuid import uuid4

COLLECTION_COUNTS = {
    'cancellations': 2, 'cancellation_releases': 1, 'goods_returns': 2,
    'supplier_claims': 2, 'invoice_adjustments': 2, 'invoice_adjustment_lines': 2,
}


def read(client):
    status, body = client.request('GET', '/api/erp/snapshot/')
    assert status == 200, (status, body[:200])
    return json.loads(body)


def command(client, payload):
    status, body = client.request('POST', '/api/erp/preview/', payload)
    assert status == 200, (payload['action'], status, body[:400])
    preview = json.loads(body)
    status, body = client.request('POST', '/api/operations/confirm/',
        {'proposal_id': preview['id'], 'confirmed': True})
    assert status == 200, (payload['action'], status, body[:400])
    receipt = json.loads(body)
    assert receipt['state'] == 'succeeded'
    return receipt


def populate(client, import_receipt, seed):
    first = read(client)
    assert all(first.get(name) == [] for name in COLLECTION_COUNTS)
    def target(entity, external_id):
        found = [r['target_id'] for r in import_receipt['mappings']
                 if r['entity'] == entity and r['external_id'] == external_id]
        assert len(found) == 1
        return found[0]
    po = target('purchase_open_balance', 'purchase-line-eur')
    line = target('sales_line', 'sale-line-eur')
    order = target('sales_order', 'sale-eur')
    lot = target('opening_lot', 'lot-two-eur')
    location = target('location', 'warehouse-eur')
    records = []
    def act(action, **fields):
        return command(client, dict(action='erp_' + action, **fields))
    def correction(action, code, **fields):
        payload = dict(action='erp_' + action, operation_id=str(uuid4()), code=code,
            reason='Синтетичний доказ збереження історії у резервній копії',
            business_date=first['as_of'], **fields)
        result = command(client, payload)
        records.append({'payload': payload, 'receipt': result})
        return result
    received = act('receive', purchase_id=po, code='RESTORE-B03-RCV',
                   location_id=location, quantity='2.000')
    candidates = [r for r in read(client)['source_movements']
                  if r['kind'] == 'receipt' and r['lot_id'] == received['lot_id']]
    assert len(candidates) == 1
    returned = correction('return_supplier', 'RESTORE-B03-SUP-RET',
                          receipt_id=candidates[0]['id'], quantity='1.000')
    assert returned['allocated_cost'] == '1.31'
    claim = correction('confirm_supplier_claim', 'RESTORE-B03-CLAIM',
        claim_id=returned['claim_id'], amount='1.31', currency='EUR',
        source_document_id=seed['import_document']['document_id'])
    assert claim['amount'] == '1.31'
    cancel_po = correction('cancel_remaining', 'RESTORE-B03-PO-CANCEL',
                           purchase_id=po, quantity='1.000')
    assert cancel_po['effective_open'] == '2.000'
    act('quality', lot_id=lot, result='approved', inspector_id=seed['employee_id'],
        note='Синтетично перевірено партію перед відвантаженням')
    reservation = act('reserve', lot_id=lot, line_id=line, quantity='2.500')
    cancel_so = correction('cancel_remaining', 'RESTORE-B03-SO-CANCEL',
                           line_id=line, quantity='0.500')
    assert cancel_so['effective_open'] == '2.000'
    assert cancel_so['released'] == [{'reservation_id': reservation['reservation_id'],
        'quantity': '0.500', 'before_quantity': '2.500', 'after_quantity': '2.000'}]
    act('ship', line_id=line, lot_id=lot, quantity='1.000', reference='RESTORE-B03-SHIP')
    candidates = [r for r in read(client)['source_movements']
        if r['kind'] == 'shipment' and r['line_id'] == line and r['reference'] == 'RESTORE-B03-SHIP']
    assert len(candidates) == 1
    invoice = act('invoice', order_id=order, code='RESTORE-B03-INVOICE',
                  due_date=next(r['due_date'] for r in first['orders'] if r['id'] == order))
    customer_return = correction('return_from_shipment', 'RESTORE-B03-CUSTOMER-RET',
        shipment_id=candidates[0]['id'], quantity='0.500', location_id=location)
    assert customer_return['allocated_cost'] == '1.17'
    credit = correction('credit_invoice', 'RESTORE-B03-CREDIT',
        invoice_id=invoice['invoice_id'], basis='return', allocations=[{
            'invoice_line_index': 0, 'return_id': customer_return['goods_return_id'], 'quantity': '0.500'}])
    assert credit['total'] == '2.06' and credit['settlement']['receivable'] == '2.06'
    reversal = correction('reverse_credit', 'RESTORE-B03-REVERSAL',
                          credit_id=credit['invoice_adjustment_id'])
    assert reversal['total'] == '2.06' and reversal['settlement']['receivable'] == '4.12'
    snapshot = read(client)
    assert {name: len(snapshot[name]) for name in COLLECTION_COUNTS} == COLLECTION_COUNTS
    current_po = next(r for r in snapshot['purchases'] if r['id'] == po)
    current_line = next(r for r in snapshot['lines'] if r['id'] == line)
    current_invoice = next(r for r in snapshot['invoices'] if r['invoice_id'] == invoice['invoice_id'])
    from decimal import Decimal as D
    assert [D(current_po[k]) for k in ('quantity','received','cancelled_quantity','open_quantity','returned_quantity')] == [D('5'),D('2'),D('1'),D('2'),D('1')]
    assert [D(current_line[k]) for k in ('quantity','shipped','cancelled_quantity','open_quantity','returned_quantity')] == [D('2.5'),D('1'),D('.5'),D('1'),D('.5')]
    assert [D(current_invoice[k]) for k in ('amount','paid','effective_credit','receivable')] == [D('4.12'),D(0),D(0),D('4.12')]
    return {'records': records, 'snapshot': snapshot, 'counts': COLLECTION_COUNTS,
        'snapshot_sha256': hashlib.sha256(json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode()).hexdigest()}


def verify_restored(client, expected):
    assert read(client) == expected['snapshot'], 'Restored B03 complete snapshot changed'
    for row in expected['records']:
        payload, receipt = row['payload'], row['receipt']
        url = '/api/erp/corrections/outcome/?action=' + payload['action'] + '&operation_id=' + payload['operation_id']
        status, body = client.request('GET', url)
        assert status == 200, (payload['action'], status, body[:200])
        result = json.loads(body)
        assert result['state'] == 'succeeded' and result['receipt'] == receipt
        assert command(client, payload) == receipt, 'New proposal with the same domain intent duplicated an effect'
    assert read(client) == expected['snapshot'], 'Read/replay after restore changed business state'
    return {'correction_actions': len(expected['records']), 'six_populated_ledgers': expected['counts'],
            'snapshot_sha256': expected['snapshot_sha256'], 'new_business_effects': 0}
