"""Opt-in browser checks for three bounded synthetic UI flows, separate from Gate 10.

Called only by the owner of a fresh isolated browser/server/SQLite run. UI actions
use the existing preview/confirm path; SQLite is an independent read-only oracle.
Replay uses the same authenticated browser and the same confirmed proposal ID.
This is not the Gate 6 end-to-end business scenario or general invoice extraction.
"""
from contextlib import closing
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qs, urlsplit
import uuid


SCHEMA = 'bos.flow-browser.v1'
CHECKS = ('supply_transfer_confirm_replay', 'settlement_payment_confirm_replay',
          'document_match_explicit_exception')


def require(condition, code):
    if not condition:
        raise AssertionError(code)


def _connect(database):
    return sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)


def _one(connection, sql, args=()):
    rows = connection.execute(sql, args).fetchall()
    require(len(rows) == 1, 'Expected exactly one explicit synthetic fixture')
    return rows[0]


def validate_isolation(origin, database, report):
    """Refuse mutation before browser calls unless this runner owns synthetic data."""
    address = urlsplit(origin)
    require(address.scheme == 'http' and address.hostname == '127.0.0.1'
            and address.port and not address.username and not address.password
            and address.path in ('', '/') and not address.query and not address.fragment,
            'An explicit isolated loopback origin is required')
    database = Path(database).resolve()
    isolation = report.get('isolation', {})
    require(isolation.get('vendor') == 'sqlite' and isolation.get('database_initially_absent') is True
            and isolation.get('origin') == origin and isolation.get('database')
            and Path(isolation['database']).resolve() == database,
            'Flow checks require the current runner owned SQLite database')
    require(database.is_file(), 'The owned synthetic database is missing')
    with closing(_connect(database)) as connection:
        marker = json.loads(_one(connection,
            'SELECT value FROM operations_configuration WHERE key=?', ('ua_workpoints_dataset',))[0])
        require(marker.get('synthetic') is True and marker.get('currency') == 'UAH',
                'Explicit synthetic UA fixture marker is required')
        order_id = _one(connection, 'SELECT id FROM erp_salesorder WHERE code=?', ('UA-DEMO-KY-SO',))[0]
        item_id = _one(connection, 'SELECT id FROM erp_item WHERE code=?', ('UA-DEMO-PRODUCT',))[0]
        line_id = _one(connection, 'SELECT id FROM erp_salesline WHERE order_id=? AND item_id=?',
                       (order_id, item_id))[0]
        purchase_id, supplier_id = _one(connection,
            'SELECT id,supplier_id FROM erp_purchase WHERE code=? AND item_id=?', ('UA-DEMO-KY-PO', item_id))
        return {'order_id': order_id, 'item_id': item_id, 'line_id': line_id,
                'purchase_id': purchase_id, 'supplier_id': supplier_id,
                'target_id': _one(connection, 'SELECT id FROM erp_location WHERE code=?', ('UA-DEMO-KY-WH',))[0],
                'source_lot_id': _one(connection, 'SELECT id FROM erp_lot WHERE code=?', ('UA-DEMO-LV-LOT',))[0],
                'invoice_id': _one(connection, 'SELECT id FROM operations_invoice WHERE code=?', ('UA-DEMO-KY-INV',))[0],
                'document_id': _one(connection, 'SELECT id FROM operations_document WHERE code=?', ('UA-DEMO-CERT',))[0]}


def _business_digest(connection):
    # Approval/session/mutex bookkeeping is separate from business mutation.
    names = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        if row[0].startswith(('erp_', 'finance_')) or row[0] in
        ('operations_document', 'operations_invoice', 'operations_auditevent')]
    state = {}
    for name in names:
        require(re.fullmatch(r'[a-z_]+', name), 'Unexpected business table identifier')
        rows = connection.execute('SELECT * FROM "' + name + '" ORDER BY 1').fetchall()
        state[name] = [[{'sha256': hashlib.sha256(value).hexdigest()} if isinstance(value, bytes)
                        else value for value in row] for row in rows]
    return hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def facts(database, selected, transfer_code, payment_reference):
    with closing(_connect(database)) as connection:
        # One read transaction makes the independent oracle internally consistent.
        connection.execute('BEGIN')
        events = connection.execute('SELECT id,action,payload FROM erp_event ORDER BY id').fetchall()
        matching = {'transfer': [], 'payment': []}
        for pk, action, raw in events:
            payload = json.loads(raw)
            if action == 'erp_transfer' and payload.get('code') == transfer_code:
                matching['transfer'].append(pk)
            if action == 'erp_payment' and payload.get('reference') == payment_reference:
                matching['payment'].append(pk)
        amount, paid, currency = _one(connection,
            'SELECT CAST(amount AS TEXT),CAST(paid AS TEXT),currency FROM operations_invoice WHERE id=?',
            (selected['invoice_id'],))
        quantities = [Decimal(row[0]) for row in connection.execute(
            'SELECT CAST(quantity AS TEXT) FROM erp_lot WHERE item_id=?', (selected['item_id'],))]
        return {'business_sha256': _business_digest(connection), 'event_count': len(events),
                'movement_count': _one(connection, 'SELECT count(*) FROM erp_movement')[0],
                'invoice_count': _one(connection, 'SELECT count(*) FROM operations_invoice')[0],
                'source_quantity': _one(connection, 'SELECT CAST(quantity AS TEXT) FROM erp_lot WHERE id=?',
                                        (selected['source_lot_id'],))[0],
                'item_quantity': str(sum(quantities, Decimal(0))),
                'destination': connection.execute(
                    'SELECT id,item_id,location_id,CAST(quantity AS TEXT),currency,quality FROM erp_lot WHERE code=?',
                    (transfer_code,)).fetchall(),
                'invoice': {'amount': amount, 'paid': paid, 'currency': currency}, 'events': matching}


def validate_transfer(before, after, selected):
    require(after['event_count'] == before['event_count'] + 1
            and after['movement_count'] == before['movement_count'] + 2
            and len(after['events']['transfer']) == 1
            and not before['events']['transfer'] and not before['destination'],
            'Transfer must create exactly one event and two physical movements')
    require(Decimal(after['source_quantity']) == Decimal(before['source_quantity']) - 1
            and Decimal(after['item_quantity']) == Decimal(before['item_quantity']),
            'Transfer must conserve the actual item quantity')
    require(len(after['destination']) == 1, 'Transfer must create exactly one destination lot')
    _, item_id, location_id, quantity, currency, quality = after['destination'][0]
    require(item_id == selected['item_id'] and location_id == selected['target_id']
            and Decimal(quantity) == 1 and currency == 'UAH' and quality == 'approved',
            'Persisted destination does not match the explicit transfer')
    require(after['invoice'] == before['invoice'] and after['invoice_count'] == before['invoice_count'],
            'Stock transfer must not mutate invoice money')


def validate_payment(before, after):
    require(after['event_count'] == before['event_count'] + 1 and len(after['events']['payment']) == 1
            and not before['events']['payment'], 'Payment must create exactly one matching event')
    require(Decimal(after['invoice']['paid']) == Decimal(before['invoice']['paid']) + Decimal('12.34')
            and after['invoice']['amount'] == before['invoice']['amount']
            and after['invoice']['currency'] == before['invoice']['currency'] == 'UAH',
            'Persisted payment must be exactly 12.34 UAH')
    require(after['movement_count'] == before['movement_count']
            and after['invoice_count'] == before['invoice_count']
            and after['destination'] == before['destination']
            and after['source_quantity'] == before['source_quantity']
            and after['item_quantity'] == before['item_quantity'], 'Payment must not mutate stock or create invoices')


def _json_response(response, schema=None):
    require(response.status == 200, 'Flow endpoint did not return HTTP 200')
    value = response.json()
    require(isinstance(value, dict), 'Expected an object response')
    if schema:
        require(value.get('schema') == schema, 'Unexpected flow schema')
    return value


def _endpoint(response, origin, path, method='GET'):
    return response.url.split('?', 1)[0] == origin + path and response.request.method == method


def _combo(scope, label):
    return scope.get_by_role('combobox', name=re.compile('^' + re.escape(label)))


def _open_order(page, expect):
    expect(page.get_by_role('heading', name='Філії та робочі точки', exact=True)).to_be_visible()
    # Global fetch invalidates the workpoint bundle after every successful POST,
    # including an idempotent replay. Re-read explicitly before opening a record.
    page.get_by_role('button', name='Оновити робочі точки', exact=True).click()
    chooser = _combo(page, 'Робоча точка')
    expect(chooser).to_have_count(1)
    expect(chooser).to_be_visible()
    options = chooser.locator('option').evaluate_all(
        '(xs)=>xs.filter(x=>x.value).map(x=>({value:x.value,text:x.textContent}))')
    kyiv = [option for option in options if 'Київ' in option['text']]
    require(len(kyiv) == 1, 'Exactly one explicit Kyiv workpoint is required')
    chooser.select_option(kyiv[0]['value'])
    page.get_by_role('button', name='UA-DEMO-KY-SO', exact=True).click()
    dialog = page.locator('dialog[open]')
    expect(dialog).to_have_count(1)
    expect(dialog.get_by_role('heading', name='Замовлення · UA-DEMO-KY-SO', exact=True)).to_be_visible()
    return dialog


def _replay(page, proposal_id):
    # No new preview or business intent. The browser keeps its normal session/CSRF handling.
    return page.evaluate('''async proposal_id => {
      const response = await fetch('/api/operations/confirm/', {method:'POST',
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({proposal_id,confirmed:true})});
      return {status:response.status,body:await response.json()};
    }''', proposal_id)


def finish_report(report):
    checks = report.get('flow_checks', [])
    report['flow_complete'] = (report.get('flow_schema') == SCHEMA and len(checks) == len(CHECKS)
        and {row.get('id') for row in checks} == set(CHECKS)
        and all(row.get('passed') is True for row in checks))
    return report['flow_complete']


def run_flow_checks(page, origin, database, output, report):
    """Run on the already-authenticated CEO page; leave Gate 10 check IDs untouched."""
    require('flow_schema' not in report, 'Refusing to overwrite prior flow evidence')
    report.update(flow_schema=SCHEMA, flow_checks=[], flow_screenshots=[], flow_complete=False,
                  flow_scope='Synthetic supply transfer, payment, and unsupported document read; not Gate 6')
    selected = validate_isolation(origin, database, report)
    from playwright.sync_api import expect
    output = Path(output).resolve()
    transfer_code = 'UI-FLOW-LOT-' + uuid.uuid4().hex[:12]
    payment_reference = 'UI-FLOW-PAY-' + uuid.uuid4().hex[:12]
    snapshot = lambda: facts(database, selected, transfer_code, payment_reference)

    def screenshot(name):
        path = output / (name + '.png')
        require(not path.exists(), 'Refusing to replace prior flow screenshot')
        page.screenshot(path=str(path))
        report['flow_screenshots'].append(path.name)

    def passed(name, **evidence):
        report['flow_checks'].append({'id': name, 'passed': True, **evidence})
        print('BOS_FLOW_CHECK ' + name, flush=True)

    def commit(action, before, validate, prefix):
        dialog = page.locator('dialog[open]')
        with page.expect_response(lambda response: _endpoint(response, origin, '/api/erp/preview/', 'POST')) as seen:
            dialog.get_by_role('button', name='Перевірити операцію', exact=True).click()
        proposal = _json_response(seen.value)
        require(proposal.get('payload', {}).get('action') == 'erp_' + action, 'Wrong proposed action')
        uuid.UUID(proposal['id'])
        expect(dialog.get_by_text('Перевірку пройдено', exact=True)).to_be_visible()
        preview_facts = snapshot()
        require(preview_facts == before, 'Preview changed business state')
        screenshot('flow-' + prefix + '-preview')
        with page.expect_response(lambda response: _endpoint(response, origin, '/api/operations/confirm/', 'POST')) as seen:
            dialog.get_by_role('button', name='Погодити й виконати', exact=True).click()
        receipt = _json_response(seen.value)
        expect(dialog).to_have_count(0)
        expect(page.get_by_role('heading', name='Результат погодженої дії', exact=True)).to_be_visible()
        confirmed = snapshot()
        validate(before, confirmed)
        screenshot('flow-' + prefix + '-confirmed')
        replay = _replay(page, proposal['id'])
        require(replay['status'] == 200 and replay['body'] == receipt, 'Replay did not return the stored receipt')
        after_replay = snapshot()
        require(after_replay == confirmed, 'Replay duplicated or changed business records')
        return {'proposal_id': proposal['id'], 'payload': proposal['payload'], 'receipt': receipt,
                'before': before, 'after_preview': preview_facts, 'after_confirm': confirmed,
                'after_replay': after_replay, 'preview_status': 200, 'confirm_status': 200,
                'replay_status': replay['status'], 'replay_transport': 'same browser session HTTP; same proposal'}

    # Existing UA seed: Kyiv demand is reserved; Lviv has unreserved approved stock.
    dialog = _open_order(page, expect)
    panel = dialog.get_by_role('region', name='Забезпечення замовлення', exact=True)
    expect(panel).to_be_visible()
    expect(_combo(panel, 'Позиція замовлення')).to_have_value('')
    expect(_combo(panel, 'Місце призначення')).to_have_value('')
    _combo(panel, 'Позиція замовлення').select_option(str(selected['line_id']))
    path = '/api/erp/lines/' + str(selected['line_id']) + '/supply-options/'
    with page.expect_response(lambda response: _endpoint(response, origin, path)
            and parse_qs(urlsplit(response.url).query).get('target_location_id') == [str(selected['target_id'])]) as seen:
        _combo(panel, 'Місце призначення').select_option(str(selected['target_id']))
    supply = _json_response(seen.value, 'bos.supply-options.v1')
    require(supply.get('line', {}).get('id') == selected['line_id']
            and supply.get('target_location', {}).get('id') == selected['target_id']
            and supply.get('supported') is True and supply.get('operation_proposal') is None,
            'Supply did not use the explicit source and destination')
    expect(panel.get_by_role('button', name='Перемістити · UA-DEMO-LV-LOT', exact=True)).to_be_visible()
    panel.scroll_into_view_if_needed()
    screenshot('flow-supply-selected')
    before = snapshot()
    panel.get_by_role('button', name='Перемістити · UA-DEMO-LV-LOT', exact=True).click()
    dialog = page.locator('dialog[open]')
    expect(dialog.get_by_role('heading', name='Перемістити матеріал', exact=True)).to_be_visible()
    expect(_combo(dialog, 'Вихідна партія')).to_have_value(str(selected['source_lot_id']))
    expect(_combo(dialog, 'Куди')).to_have_value(str(selected['target_id']))
    expect(dialog.get_by_label('Кількість', exact=True)).to_have_value('')
    dialog.get_by_label('Кількість', exact=True).fill('1')
    dialog.get_by_label('Код партії у новому місці', exact=True).fill(transfer_code)
    dialog.get_by_label('Підстава', exact=True).fill('Синтетична перевірка переміщення UI')
    evidence = commit('transfer', before, lambda old, new: validate_transfer(old, new, selected), 'supply')
    passed(CHECKS[0], explicit_line_id=selected['line_id'], explicit_target_id=selected['target_id'],
           supply_response=supply, **evidence)

    dialog = _open_order(page, expect)
    panel = dialog.get_by_role('region', name='Розрахунки за замовленням', exact=True)
    expect(panel).to_be_visible()
    with page.expect_response(lambda response: _endpoint(response, origin,
            '/api/erp/orders/' + str(selected['order_id']) + '/settlement/')) as seen:
        panel.get_by_role('button', name='Оновити розрахунки', exact=True).click()
    settlement = _json_response(seen.value, 'bos.order-settlement.v1')
    require(settlement.get('order', {}).get('id') == selected['order_id'], 'Wrong settlement order')
    expect(panel.get_by_role('button', name='Зареєструвати оплату · UA-DEMO-KY-INV', exact=True)).to_be_visible()
    panel.scroll_into_view_if_needed()
    screenshot('flow-settlement')
    before = snapshot()
    panel.get_by_role('button', name='Зареєструвати оплату · UA-DEMO-KY-INV', exact=True).click()
    dialog = page.locator('dialog[open]')
    expect(_combo(dialog, 'Рахунок')).to_have_value(str(selected['invoice_id']))
    dialog.get_by_label('Сума у валюті рахунку', exact=True).fill('12.34')
    dialog.get_by_label('Унікальний номер підтвердження оплати', exact=True).fill(payment_reference)
    evidence = commit('payment', before, validate_payment, 'payment')
    passed(CHECKS[1], settlement_response=settlement, **evidence)

    # Use the native mobile navigation, then restore a desktop viewport for evidence.
    page.set_viewport_size({'width': 390, 'height': 1000})
    page.get_by_label('Розділ системи', exact=True).select_option('erp:purchase')
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.get_by_role('button', name='Відкрити UA-DEMO-KY-PO', exact=True).click()
    dialog = page.locator('dialog[open]')
    panel = dialog.get_by_role('region', name='Зіставлення документа закупівлі', exact=True)
    expect(panel).to_be_visible()
    _combo(panel, 'Документ для зіставлення').select_option(str(selected['document_id']))
    _combo(panel, 'Постачальник у документі').select_option(str(selected['supplier_id']))
    _combo(panel, 'Номенклатура у документі').select_option(str(selected['item_id']))
    before = snapshot()
    path = '/api/erp/purchases/' + str(selected['purchase_id']) + '/document-match/'
    with page.expect_response(lambda response: _endpoint(response, origin, path)) as seen:
        panel.get_by_role('button', name='Зіставити документ', exact=True).click()
    value = _json_response(seen.value, 'bos.document-match-read.v1')
    query = parse_qs(urlsplit(seen.value.url).query)
    require(all(query.get(key) == [str(selected[key])] for key in ('document_id', 'supplier_id', 'item_id')),
            'Document match omitted explicit identifiers')
    draft = value.get('draft', {})
    require(draft.get('schema') == 'bos.document-match.v1'
            and draft.get('provider') == 'mock.synthetic-invoice.v1'
            and draft.get('exceptions') == ['unsupported_document']
            and draft.get('decision') == 'needs_information' and draft.get('fields') is None
            and draft.get('operation_proposal') is None
            and draft.get('source', {}).get('document_id') == selected['document_id'],
            'Ordinary synthetic seed document must return explicit unsupported_document')
    expect(panel.get_by_role('heading', name='Зіставлення потребує перевірки', exact=True)).to_be_visible()
    expect(panel.get_by_text('Формат змісту не підтримується навчальним зіставленням.', exact=True)).to_be_visible()
    after = snapshot()
    require(after == before, 'Document matching changed business records')
    panel.scroll_into_view_if_needed()
    screenshot('flow-document-match')
    passed(CHECKS[2], selection=selected, response=value, before=before, after=after,
           scope='Actual ordinary seeded document bytes; explicit unsupported exception, no extraction claim')
    dialog.get_by_role('button', name='Закрити', exact=True).click()
    require(finish_report(report), 'Not all bounded flow checks completed')
