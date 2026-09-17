"""C03 gate7 additive fixture: fresh synthetic HTTPS source, binding and restore."""
import hashlib
import http.client
import json
from datetime import date, timedelta
from uuid import uuid4

SOURCE = 'synthetic-restore'
ACCOUNT = 'RESTORE-MULTI-CCY'
CODE = 'RESTORE-STATEMENT'
CSV = (
    'external_id,booking_date,direction,amount,currency,counterparty_external_id,invoice_reference,purpose\n'
    'RESTORE-EUR,2026-09-12,in,4.56,EUR,RESTORE-CUSTOMER,,Синтетичне нове надходження\n'
    'RESTORE-USD,2026-09-12,in,123.45,USD,RESTORE-CUSTOMER,RESTORE-STMT-INV,Синтетична звірка історичного запису\n'
    'RESTORE-UAH,2026-09-12,in,9801.07,UAH,RESTORE-CUSTOMER,,Синтетичний історичний запис\n'
).encode('utf-8')


def read(client, path):
    code, body = client.request('GET', path)
    assert code == 200, (path, code, body[:300])
    return json.loads(body)


def upload(client):
    boundary = 'BoSRestore' + uuid4().hex
    parts = []
    for name, value in [('code', CODE), ('revision', 'A'), ('title', 'Синтетична виписка для відновлення')]:
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode())
    parts += [(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="restore.csv"\r\nContent-Type: text/csv\r\n\r\n').encode(), CSV, (f'\r\n--{boundary}--\r\n').encode()]
    headers = {'Host': f'localhost:{client.port}', 'Origin': client.origin,
        'Cookie': '; '.join(k + '=' + v for k, v in client.cookies.items()),
        'X-CSRFToken': client.cookies['csrftoken'],
        'Content-Type': 'multipart/form-data; boundary=' + boundary}
    conn = http.client.HTTPSConnection('localhost', client.port, context=client.ctx, timeout=15)
    try:
        conn.request('POST', '/api/statements/sources/', b''.join(parts), headers)
        response = conn.getresponse(); body = response.read()
        assert response.status == 201, (response.status, body[:400])
    finally:
        conn.close()
    doc = json.loads(body)
    assert doc['status'] == 'needs_review' and doc['row_count'] == 3
    assert doc['checksum'] == hashlib.sha256(CSV).hexdigest()
    status, body = client.request('POST', f"/api/operations/documents/{doc['id']}/review/", {'checksum': doc['checksum']})
    assert status == 200 and json.loads(body)['status'] == 'approved'
    status, body = client.request('GET', f"/api/operations/documents/{doc['id']}/download/")
    assert status == 200 and body == CSV
    return doc


def act(client, payload, records=None):
    status, body = client.request('POST', '/api/erp/preview/', payload)
    assert status == 200, (payload['action'], status, body[:400])
    proposal = json.loads(body)
    assert proposal.get('id') and proposal['payload']['action'] == payload['action']
    confirm = {'proposal_id': proposal['id'], 'confirmed': True}
    status, body = client.request('POST', '/api/operations/confirm/', confirm)
    assert status == 200, (payload['action'], status, body[:400])
    receipt = json.loads(body)
    assert receipt['state'] == 'succeeded'
    status, body = client.request('POST', '/api/operations/confirm/', confirm)
    assert status == 200 and json.loads(body) == receipt
    if records is not None:
        records.append({'proposal_id': proposal['id'], 'payload': payload, 'receipt': receipt})
    return receipt


def snapshot(client, import_id, line_ids):
    result = {
        'import': read(client, f'/api/statements/imports/{import_id}/'),
        'imports': read(client, '/api/statements/imports/?limit=100'),
        'lines': read(client, '/api/statements/lines/?limit=100'),
        'details': {line_id: read(client, '/api/statements/lines/' + line_id + '/') for line_id in line_ids},
        'summary': read(client, '/api/statements/summary/'),
        'journal': read(client, '/api/transactions/summary/'),
    }
    assert result['imports']['next_cursor'] is None and result['lines']['next_cursor'] is None
    return result


def populate(client, import_receipt, seed):
    """Call after C01 tasks, BEFORE B03 freezes the whole ERP+home snapshot."""
    assert read(client, '/api/statements/imports/')['items'] == []
    def target(entity, external):
        values = [row['target_id'] for row in import_receipt['mappings'] if row['entity'] == entity and row['external_id'] == external]
        assert len(values) == 1
        return values[0]
    as_of = read(client, '/api/erp/snapshot/')['as_of']
    due = str(date.fromisoformat(as_of) + timedelta(days=7))
    lot, item = target('opening_lot', 'lot-two-usd'), target('item', 'material-usd')
    # A separate USD customer order avoids altering the original B03 EUR scenario.
    order = act(client, {'action': 'erp_order', 'code': 'RESTORE-STMT-SO',
        'customer_id': seed['counterparty_id'], 'owner_id': seed['employee_id'],
        'due_date': due, 'currency': 'USD',
        'lines': [{'item_id': item, 'quantity': '1.000', 'price': '2.34'}]})
    order_id = order['order_id']
    rows = [row for row in read(client, '/api/erp/snapshot/')['lines'] if row['order_id'] == order_id]
    assert len(rows) == 1
    line = rows[0]['id']
    act(client, {'action': 'erp_confirm_order', 'order_id': order_id})
    act(client, {'action': 'erp_quality', 'lot_id': lot, 'result': 'approved',
        'inspector_id': seed['employee_id'], 'note': 'Синтетичний контроль окремої USD поставки'})
    act(client, {'action': 'erp_reserve', 'lot_id': lot, 'line_id': line, 'quantity': '1.000'})
    act(client, {'action': 'erp_ship', 'lot_id': lot, 'line_id': line,
        'quantity': '1.000', 'reference': 'RESTORE-STMT-SHIP'})
    invoice = act(client, {'action': 'erp_invoice', 'order_id': order_id,
        'code': 'RESTORE-STMT-INV', 'due_date': due})
    assert invoice['amount'] == '2.34'
    document = upload(client)
    records = []
    imported = act(client, {'action': 'erp_statement_import', 'document_id': document['id'],
        'source_sha256': document['checksum'], 'source_system': SOURCE, 'account_ref': ACCOUNT,
        'format': 'bos_statement_csv_v1', 'parser_version': '1'}, records)
    assert imported['counts'] == {'create': 3, 'reuse': 0, 'total': 3}
    ids = {row['external_id']: row['line_id'] for row in imported['lines']}
    assert len(ids) == 3
    receipts = {}
    for currency, transaction_id in [('EUR', None), ('USD', seed['transaction_ids'][1]), ('UAH', seed['transaction_ids'][2])]:
        transaction = {'mode': 'existing_transaction', 'transaction_id': transaction_id} if transaction_id else {
            'mode': 'create_transaction', 'category': 'customer', 'description': 'Синтетична звірка нового EUR надходження'}
        allocations = []
        if currency == 'USD':
            allocations = [{'allocation_key': '68cf6eb0-8e9c-43ef-91b4-e01e934e151e',
                'mode': 'new_payment', 'invoice_id': invoice['invoice_id'], 'amount': '2.34',
                'currency': 'USD', 'invoice_match': 'exact_reference',
                'reason': 'Повний номер рахунку звірено із синтетичною випискою'}]
        receipts[currency] = act(client, {'action': 'erp_statement_reconcile',
            'line_id': ids['RESTORE-' + currency], 'transaction': transaction,
            'matching': {'kind': 'manual', 'counterparty_id': seed['counterparty_id'],
                'counterparty_external_id': 'RESTORE-CUSTOMER'},
            'reason': 'Явна звірка джерела та контрагента для репетиції відновлення',
            'allocations': allocations}, records)
        assert receipts[currency]['transaction_created'] is (currency == 'EUR')
        assert receipts[currency]['binding_created'] is True
    status, body = client.request('DELETE', f"/api/transactions/{receipts['EUR']['transaction_id']}/", {})
    assert status == 204, (status, body[:300])
    saved = snapshot(client, imported['import_id'], list(ids.values()))
    assert len(saved['imports']['items']) == 1 and len(saved['lines']['items']) == 3
    assert sum(len(x['allocations']) for x in saved['details'].values()) == 1
    eur = saved['details'][ids['RESTORE-EUR']]
    assert eur['transaction']['archived_at'] and eur['line']['cash_recorded'] is True
    assert eur['current_summary']['unallocated'] == '4.56'
    usd = saved['details'][ids['RESTORE-USD']]
    assert usd['current_summary']['allocated'] == '2.34' and usd['current_summary']['unallocated'] == '121.11'
    assert usd['transaction']['id'] == seed['transaction_ids'][1]
    assert usd['invoices'][0]['settlement']['paid'] == '2.34'
    assert usd['invoices'][0]['settlement']['receivable'] == '0.00'
    assert saved['journal']['includes_archived'] is True
    journal = {row['currency']: row for row in saved['journal']['currencies']}
    for currency, value in [('EUR', '21.95'), ('USD', '123.45'), ('UAH', '9801.07')]:
        assert journal[currency]['in'] == value and journal[currency]['out'] == '0.00' and journal[currency]['net'] == value
    totals = {row['currency']: row for row in saved['summary']['currencies']}
    for currency, value in [('EUR', '4.56'), ('USD', '123.45'), ('UAH', '9801.07')]:
        assert totals[currency]['imported']['in'] == totals[currency]['recorded']['in'] == value
        assert totals[currency]['unposted']['in'] == '0.00'
    status, exported = client.request('GET', f"/api/statements/imports/{imported['import_id']}/export/")
    assert status == 200
    return {'import_id': imported['import_id'], 'line_ids': list(ids.values()), 'document_id': document['id'],
        'source_sha256': document['checksum'], 'state': saved, 'records': records, 'export': exported.decode('utf-8'),
        'state_sha256': hashlib.sha256(json.dumps(saved, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}


def verify_restored(client, expected):
    status, original = client.request('GET', f"/api/operations/documents/{expected['document_id']}/download/")
    assert status == 200 and original == CSV and hashlib.sha256(original).hexdigest() == expected['source_sha256']
    assert snapshot(client, expected['import_id'], expected['line_ids']) == expected['state']
    for record in expected['records']:
        status, body = client.request('POST', '/api/operations/confirm/',
            {'proposal_id': record['proposal_id'], 'confirmed': True})
        assert status == 403, (status, body[:300])
        status, body = client.request('POST', '/api/erp/preview/', record['payload'])
        assert status == 200, (record['payload']['action'], status, body[:400])
        reused = json.loads(body)
        assert reused['state'] == 'no_change' and reused['id'] is None
        assert reused['first_commit_receipt'] == record['receipt']
    status, exported = client.request('GET', f"/api/statements/imports/{expected['import_id']}/export/")
    assert status == 200 and exported.decode('utf-8') == expected['export']
    assert snapshot(client, expected['import_id'], expected['line_ids']) == expected['state']
    return {'tables_populated': 3, 'statement_lines': 3, 'allocations': 1,
        'new_transaction': 1, 'existing_transaction_bindings': 2,
        'archived_transaction_in_totals': True, 'source_sha256': expected['source_sha256'],
        'state_sha256': expected['state_sha256'], 'original_intent_receipts': 4,
        'old_session_execution_refused': True, 'new_business_effects': 0}
