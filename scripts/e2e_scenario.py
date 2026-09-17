"""Gate 6: frozen EUR oracle, fresh owned DB/media, actual CSRF HTTP writers.

Direct execution creates its own new SQLite database. verify.py may supply an
unused check_<uuid>.sqlite3 or its explicitly disposable PostgreSQL database.
Existing databases are refused before migrations; all original source DBs are
read only for file SHA proof. No demo seed or external network is used.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal as D
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
DRAFT_SHA = '10e8b6e671db8e2656683ebfa16bfabc1a75989543e353b6c37d17e43e27616f'
DOMAIN_APPS = {'operations','erp','finance','employees','branches','tasks','ai_assistant'}
IMMUTABLE_LEDGERS = {'erp.Event','erp.Movement','erp.GoodsReturn','erp.SupplierClaim','erp.Inspection',
    'erp.InvoiceLink','finance.StatementImport','finance.StatementAllocation','finance.FinancialIntent',
    'operations.AuditEvent','operations.ActionProposal'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode(value):
    from django.core.serializers.json import DjangoJSONEncoder
    def default(v):
        if isinstance(v, (bytes, memoryview)):
            return {'bytes': len(v), 'sha256': sha(bytes(v))}
        return DjangoJSONEncoder().default(v)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), default=default)


def reserve_environment():
    """Accept only unused verifier paths; a direct run owns all mutable paths."""
    if not __debug__ or os.environ.get('PYTHONOPTIMIZE', '') not in ('', '0'):
        raise RuntimeError('Assertions must be enabled.')
    backend = os.environ.get('BOS_VERIFY_DB', 'sqlite')
    name = os.environ.get('BOS_TEST_DB_NAME')
    supplied = name is not None
    if supplied:
        if Path(os.environ.get('BOS_PROJECT_ROOT', '')).resolve() != ROOT:
            raise RuntimeError('Supplied database requires BOS_PROJECT_ROOT matching this source.')
        work = Path(tempfile.mkdtemp(prefix='bos-gate6-'))
        if backend == 'sqlite':
            target = Path(name)
            if (not target.is_absolute() or target.is_symlink() or target.exists()
                    or not re.fullmatch(r'check_[a-f0-9]{32}\.sqlite3', target.name)
                    or target.parent.resolve() != ROOT.parent):
                raise RuntimeError('Only an unused verifier-owned check_<uuid>.sqlite3 beside source is accepted.')
            for parent in target.parents:
                if parent.is_symlink():
                    raise RuntimeError('Database ancestor symlink is forbidden.')
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        elif backend != 'postgres':
            raise RuntimeError('Unsupported verification backend.')
    else:
        if backend != 'sqlite':
            raise RuntimeError('PostgreSQL requires the actual disposable verify database.')
        work = Path(tempfile.mkdtemp(prefix='bos-gate6-'))
        target = work / ('check_' + uuid.uuid4().hex + '.sqlite3')
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        os.environ['BOS_TEST_DB_NAME'] = str(target)
    # Always use a new media root, including when verify shared a media parent.
    media = work / 'private-media'
    media.mkdir(mode=0o700)
    os.environ.update(BOS_TEST_MEDIA=str(media), BOS_VERIFY_DB=backend,
        BOS_DATA_MODE='demo', DJANGO_SETTINGS_MODULE='verification_settings',
        PYTHONDONTWRITEBYTECODE='1')
    return work, {'requested_backend':backend, 'database_name':os.environ['BOS_TEST_DB_NAME'],
        'media_root':str(media), 'source_root':str(ROOT), 'verify_supplied':supplied,
        'database_existing_before_run':False, 'demo_seed_called':False}


class Scenario:
    def __init__(self, expected, report):
        self.e, self.report = expected, report
        self.checks, self.http_calls, self.confirmations = [], [], []
        self.sources, self.checkpoints = {}, {}
        self.first_immutable_rows = {}
        from django.apps import apps
        self.models = {m._meta.label:m for m in apps.get_models()
            if m._meta.app_label in DOMAIN_APPS and m._meta.label != 'operations.LoginAttempt'}

    def check(self, name, condition):
        if not condition:
            raise AssertionError(name)
        self.checks.append(name)

    def eq(self, name, actual, expected):
        self.check(name, actual == expected)

    def money(self, name, actual, expected):
        self.check(name, D(str(actual)) == D(str(expected)))

    def one(self, label, **filters):
        rows = self.models[label].objects.filter(**filters)
        self.eq('Exactly one source: '+label, rows.count(), 1)
        return rows.get()

    def http(self, client, method, path, payload=None, status=200):
        from django.conf import settings
        headers = {}
        if method != 'GET':
            headers['HTTP_X_CSRFTOKEN'] = client.cookies[settings.CSRF_COOKIE_NAME].value
        if method == 'GET':
            response = client.get(path)
        else:
            response = client.post(path, json.dumps(payload, ensure_ascii=False),
                content_type='application/json', **headers)
        self.http_calls.append({'method':method, 'path':path, 'status':response.status_code,
            'actor_id':client.session.get('_auth_user_id'),
            'response_sha256':sha(response.content) if not response.streaming else None})
        if response.status_code != status:
            # All fixture content is synthetic; avoid response bodies in console.
            raise AssertionError(f'{method} {path}: expected {status}, actual {response.status_code}; response_sha256={sha(response.content)}')
        if response.streaming:
            data = b''.join(response.streaming_content)
            response.close()
            return data
        return response.json() if 'application/json' in response.get('Content-Type','') else response.content

    def upload(self, client, doc, statement=False):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.conf import settings
        data = doc['utf8_text'].encode('utf-8')  # Literal LF: never unescape/normalize.
        self.eq('Frozen original byte length: '+doc['code'], len(data), doc['bytes'])
        self.eq('Frozen original SHA: '+doc['code'], sha(data), doc['sha256'])
        path = '/api/statements/sources/' if statement else '/api/operations/documents/upload/'
        response = client.post(path, {'file':SimpleUploadedFile(doc['filename'], data,
            content_type='text/csv' if statement else 'text/plain'),
            'code':doc['code'], 'revision':doc['revision'], 'title':doc['code']+' · синтетичне джерело'},
            HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        self.http_calls.append({'method':'POST', 'path':path, 'status':response.status_code,
            'actor_id':client.session.get('_auth_user_id'), 'response_sha256':sha(response.content)})
        self.eq('Actual private upload: '+doc['code'], response.status_code, 201)
        source = response.json()
        self.eq('Uploaded checksum: '+doc['code'], source['checksum'], doc['sha256'])
        self.eq('Uploaded status: '+doc['code'], source['status'], 'needs_review')
        approved = self.http(client, 'POST', f"/api/operations/documents/{source['id']}/review/",
            {'checksum':doc['sha256']})
        self.eq('Actual review approved: '+doc['code'], approved['status'], 'approved')
        raw = self.http(client, 'GET', f"/api/operations/documents/{source['id']}/download/")
        self.eq('Downloaded original bytes: '+doc['code'], raw, data)
        self.sources[doc['code']] = {'id':source['id'], 'sha256':sha(raw), 'bytes':len(raw)}
        return source

    def snapshot(self):
        result = {}
        for label, model in sorted(self.models.items()):
            rows = model._base_manager.order_by('pk')
            if label == 'operations.Configuration':
                rows = rows.exclude(key='erp_write')
            result[label] = list(rows.values())
        return json.loads(encode(result))

    def counts(self):
        return {label:model._base_manager.count() for label,model in self.models.items()}

    def row(self, obj):
        return json.loads(encode(type(obj)._base_manager.filter(pk=obj.pk).values().get()))

    def confirmed(self, key, payload, actor='ceo'):
        ordinal = len(self.confirmations)
        contract = self.e['confirmed_actions'][ordinal]
        self.eq('Confirmed action order: '+key,
            (key,payload['action'],actor), (contract['key'],contract['action'],contract['confirm_actor']))
        client = self.clients[actor]
        before = self.counts()
        before_preview = {label:rows for label,rows in self.snapshot().items() if label!='operations.ActionProposal'}
        preview = self.http(client, 'POST', '/api/erp/preview/' if payload['action'].startswith('erp_')
                            else '/api/operations/preview/', payload)
        self.check('New durable proposal: '+key, bool(preview.get('id')))
        self.eq('One proposal after preview: '+key,
            self.counts()['operations.ActionProposal']-before['operations.ActionProposal'], 1)
        self.eq('Preview preserves all other row counts: '+key,
            {k:v for k,v in self.counts().items() if k!='operations.ActionProposal'},
            {k:v for k,v in before.items() if k!='operations.ActionProposal'})
        self.eq('Preview preserves full business state: '+key,
            {label:rows for label,rows in self.snapshot().items() if label!='operations.ActionProposal'},before_preview)
        command = {'proposal_id':preview['id'], 'confirmed':True}
        receipt = self.http(client, 'POST', '/api/operations/confirm/', command)
        self.eq('First receipt succeeded: '+key, receipt['state'], 'succeeded')
        stable = self.snapshot()
        for label in IMMUTABLE_LEDGERS & set(stable):
            for row in stable[label]:
                # ActionProposal includes the current committed receipt; no
                # pending proposal is ever recorded as immutable history.
                if label=='operations.ActionProposal' and not row['receipt']:
                    continue
                key_field = self.models[label]._meta.pk.attname
                history_key = label + ':' + str(row[key_field])
                if history_key in self.first_immutable_rows:
                    self.eq('Prior immutable history survives '+history_key+' after '+key,
                            row,self.first_immutable_rows[history_key])
                else:
                    self.first_immutable_rows[history_key] = deepcopy(row)
        replay = self.http(client, 'POST', '/api/operations/confirm/', command)
        self.eq('Immediate same-ID literal receipt: '+key, replay, receipt)
        self.eq('Immediate replay full business snapshot: '+key, self.snapshot(), stable)
        self.confirmations.append({'key':key, 'action':payload['action'], 'actor':actor,
            'proposal_id':preview['id'], 'first_receipt':receipt,
            'first_business_sha256':sha(encode(stable).encode()),
            'immediate_receipt_equal':True, 'immediate_business_equal':True})
        return receipt

    def verify_sources(self):
        for doc in self.e['source_documents']:
            entry = self.sources[doc['code']]
            source = self.one('operations.Document', pk=entry['id'], code=doc['code'], revision=doc['revision'])
            self.eq('Current source status: '+doc['code'], source.status, doc['status'])
            self.eq('Current source access: '+doc['code'], source.access_level, doc['access_level'])
            self.eq('No legacy inline bytes: '+doc['code'], bytes(source.content), b'')
            self.check('Actual private original path: '+doc['code'], bool(source.original_file))
            raw = self.http(self.clients['ceo'], 'GET', f'/api/operations/documents/{source.pk}/download/')
            self.eq('Preserved actual source bytes: '+doc['code'], raw, doc['utf8_text'].encode('utf-8'))
            self.eq('Preserved source SHA: '+doc['code'], sha(raw), doc['sha256'])

    def execute(self):
        from django.db import connection
        from django.core.management import call_command
        self.check('Fresh database has no tables before migrate', not connection.introspection.table_names())
        call_command('migrate', verbosity=0, interactive=False)
        for label,count in self.counts().items():
            self.eq('No business seed after migrate: '+label, count, 0)
        fixture_path = ROOT / 'fixtures' / 'synthetic' / 'e2e_fixture.py'
        spec = importlib.util.spec_from_file_location('bos_gate6_reference_fixture', fixture_path)
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        # A narrow adapter lets fixture uploads reuse the same actual HTTP log.
        class HTTP:
            def __call__(_, *args, **kwargs): return self.http(*args, **kwargs)
            def upload(_, *args, **kwargs): return self.upload(*args, **kwargs)
        self.clients, self.identities, self.ids, bootstrap = fixture.bootstrap(self.e, HTTP(), self.check)
        self.report['bootstrap'] = bootstrap
        self.report['identity_aliases'] = deepcopy(self.ids)
        e, ids, ceo = self.e, self.ids, self.clients['ceo']
        baseline = self.counts()
        self.report['baseline_counts'] = baseline
        self.report['baseline_business_sha256'] = sha(encode(self.snapshot()).encode())
        req = e['requirement']
        self.http(ceo, 'POST', '/api/operations/requests/create/', {
            **{k:req[k] for k in ('code','part','revision','quantity','unit','currency','required_by')},
            'owner_id':ids[req['owner_alias']], 'document_id':ids[req['document_code']],
            'details':{'tax_basis':e['numeric_oracle']['tax_basis']}}, status=201)
        request = self.one('operations.ProcurementRequest', code=req['code'])
        quote = e['quote']
        self.http(ceo, 'POST', '/api/operations/quotes/create/', {
            'code':quote['code'], 'request_code':req['code'], 'supplier_id':ids[quote['supplier_alias']],
            'document_id':ids[quote['document_code']], 'terms':deepcopy(quote['terms'])}, status=201)
        quoted = self.one('operations.SupplierQuote', code=quote['code'])
        comparison = self.http(ceo, 'GET', '/api/operations/compare/?code='+req['code'])
        self.eq('One actual quote comparison', len(comparison['rows']), 1)
        self.money('Quote comparison exact total', comparison['rows'][0]['total'], quote['comparison_total'])
        self.eq('Quote comparison calculated arrival', comparison['rows'][0]['arrival'], quote['calculated_arrival'])
        self.report['comparison'] = comparison
        p = e['purchase']
        receipt = self.confirmed('purchase', {'action':'erp_purchase',
            **{k:p[k] for k in ('code','quantity','price','extras','currency','due_date','revision','supplier_confirmation')},
            'item_id':ids['item'], 'supplier_id':ids['supplier'], 'request_id':request.pk, 'quote_id':quoted.pk})
        purchase = self.one('erp.Purchase', pk=receipt['purchase_id'], code=p['code'])
        purchase_source = {'request':self.row(request), 'quote':self.row(quoted),
            'approval_snapshot':purchase.approval_snapshot, 'original_due':str(purchase.original_due),
            'documents':{code:self.row(self.one('operations.Document',pk=entry['id'])) for code,entry in self.sources.items()}}
        self.eq('Quote source actually bound', purchase.approval_snapshot['source'], p['approval_source'])
        self.eq('Calculated arrival before attestation', purchase.approval_snapshot['calculated_arrival'], quote['calculated_arrival'])
        self.money('Approved PO total', purchase.quantity*purchase.price+purchase.extras, p['total'])
        cert_id = ids['E2E-CERT-001']
        receipt = self.confirmed('receive', {'action':'erp_receive','purchase_id':purchase.pk,
            'code':'E2E-RCV-001','location_id':ids['E2E-WH-RECEIVE'],'quantity':'4.000',
            'documents':{'certificate':cert_id}})
        origin = self.one('erp.Lot', pk=receipt['lot_id'], code='E2E-RCV-001')
        received = self.one('erp.Movement', lot=origin, purchase=purchase, kind='receipt', reference=p['code'])
        receipt_original = self.row(received)
        ret = e['supplier_return']
        self.confirmed('supplier_return', {'action':'erp_return_supplier','operation_id':ret['operation_id'],
            'code':ret['code'],'reason':'Синтетична невідповідність однієї одиниці; повернення постачальнику.',
            'business_date':e['numeric_oracle']['as_of'],'receipt_id':received.pk,'quantity':ret['quantity']})
        origin.refresh_from_db()
        self.money('Only real three units remain for quality', origin.quantity, '3.000')
        self.confirmed('quality', {'action':'erp_quality','lot_id':origin.pk,'result':'approved',
            'inspector_id':ids['manager_employee'],'note':'Перевірено три фактичні одиниці та E2E-CERT-001.'})
        receipt = self.confirmed('transfer', {'action':'erp_transfer','lot_id':origin.pk,'quantity':'2.000',
            'location_id':ids['E2E-WH-SHIP'],'code':'E2E-XFER-001','reason':'Синтетична передача двох одиниць для відвантаження.'})
        transferred = self.one('erp.Lot', pk=receipt['lot_id'], code='E2E-XFER-001')
        sale = e['sales']
        receipt = self.confirmed('order', {'action':'erp_order','code':sale['order_code'],
            'customer_id':ids[sale['customer_alias']],'owner_id':ids[sale['owner_alias']],
            'due_date':sale['due_date'],'currency':sale['currency'],
            'lines':[{'item_id':ids['item'],'quantity':sale['quantity'],'price':sale['price']}]})
        order = self.one('erp.SalesOrder', pk=receipt['order_id'], code=sale['order_code'])
        line = self.one('erp.SalesLine', order=order, item_id=ids['item'])
        self.confirmed('confirm_order', {'action':'erp_confirm_order','order_id':order.pk})
        receipt = self.confirmed('reserve', {'action':'erp_reserve','lot_id':transferred.pk,
            'quantity':sale['quantity'],'line_id':line.pk})
        reservation = self.one('erp.Reservation', pk=receipt['reservation_id'], line=line, lot=transferred)
        self.money('Actual reservation before ship', reservation.quantity, '2.000')
        self.confirmed('ship', {'action':'erp_ship','line_id':line.pk,'lot_id':transferred.pk,
            'quantity':sale['quantity'],'reference':sale['shipment_reference']})
        shipment = self.one('erp.Movement', kind='shipment',lot=transferred,line=line,reference=sale['shipment_reference'])
        shipment_original = self.row(shipment)
        inv = e['invoice']
        receipt = self.confirmed('invoice', {'action':'erp_invoice','order_id':order.pk,
            'code':inv['code'],'due_date':inv['due_date']})
        invoice = self.one('operations.Invoice', pk=receipt['invoice_id'], code=inv['code'])
        link = self.one('erp.InvoiceLink', invoice=invoice, order=order)
        invoice_original = self.row(invoice)
        invoice_link_original = self.row(link)
        self.money('Invoice unpaid before import', invoice.paid, '0.00')
        doc = next(d for d in e['source_documents'] if d['creation_phase']=='statement_source')
        source = self.upload(ceo, doc, statement=True)
        st = e['statement']
        imported = self.confirmed('statement_import', {'action':'erp_statement_import',
            'document_id':source['id'],'source_sha256':doc['sha256'],
            'source_system':st['source_system'],'account_ref':st['account_ref'],
            'format':'bos_statement_csv_v1','parser_version':'1'})
        statement_import = self.one('finance.StatementImport', pk=imported['import_id'])
        statement_line = self.one('finance.StatementLine', pk=imported['lines'][0]['line_id'],
            source_system=st['source_system'],account_ref=st['account_ref'],external_id=st['external_id'])
        self.checkpoints['original_statement_line'] = self.row(statement_line)
        invoice.refresh_from_db()
        interim = st['after_import_before_reconcile']
        self.eq('Import alone creates one line', self.models['finance.StatementLine'].objects.count(), interim['line_count'])
        self.eq('Import alone creates no Transaction', self.models['finance.Transaction'].objects.count(), interim['transaction_count'])
        self.money('Import alone does not pay invoice', invoice.paid, interim['invoice_paid'])
        self.money('Import alone keeps receivable', invoice.amount-invoice.paid, interim['invoice_open'])
        self.eq('Import alone has no payment Event', self.models['erp.Event'].objects.filter(action='erp_payment').count(),0)
        reconciled = self.confirmed('statement_reconcile', {'action':'erp_statement_reconcile','line_id':str(statement_line.pk),
            'transaction':{'mode':st['transaction_mode'],'category':e['transaction']['category'],'description':e['transaction']['description']},
            'matching':{'kind':'manual','counterparty_id':ids['customer'],'counterparty_external_id':st['counterparty_external_id']},
            'reason':'Звірено зовнішній код клієнта з його карткою та рахунком.',
            'allocations':[{'allocation_key':st['allocation_key'],'mode':st['allocation_mode'],'invoice_id':invoice.pk,
                'amount':st['amount'],'currency':st['currency'],'invoice_match':'exact_reference',
                'reason':'У виписці зазначений повний номер рахунку E2E-INV-001.'}]})
        transaction = self.one('finance.Transaction', pk=reconciled['transaction_id'])
        task_contract = e['task']
        receipt = self.confirmed('task_create', {'action':'create_task','title':task_contract['title'],
            'assignee_id':ids[task_contract['assignee_alias']],'deadline':task_contract['deadline'],
            'priority':task_contract['priority_on_create'],'category':task_contract['category'],
            'order_id':order.pk,'request_code':task_contract['request_code']})
        task = self.one('tasks.Task', pk=receipt['task_id'])
        self.eq('Created Task active', task.status, task_contract['create_status'])
        task_money_before = {label:list(self.models[label]._base_manager.order_by('pk').values()) for label in
            ('erp.Lot','erp.Movement','erp.SalesLine','operations.Invoice','finance.Transaction','finance.StatementAllocation')}
        self.confirmed('task_complete', {'action':'update_task','task_id':task.pk,
            'status':'done','result':task_contract['result'],'reason':task_contract['completion_reason']}, actor='manager')
        self.eq('Manager Task completion has zero stock/payment effects', encode(task_money_before),
            encode({label:list(self.models[label]._base_manager.order_by('pk').values()) for label in task_money_before}))
        self.final_assertions(baseline, purchase, request, quoted, purchase_source, received, receipt_original,
            shipment, shipment_original, order, line, reservation, invoice, invoice_original, link,
            invoice_link_original, statement_import, statement_line, transaction, task)
        self.verify_sources()
        before_late = self.snapshot()
        before_sources = deepcopy(self.sources)
        for command in self.confirmations:
            replay = self.http(self.clients[command['actor']], 'POST', '/api/operations/confirm/',
                {'proposal_id':command['proposal_id'],'confirmed':True})
            self.eq('Late same-ID literal receipt: '+command['key'], replay, command['first_receipt'])
            self.eq('Late replay preserves complete business state: '+command['key'], self.snapshot(), before_late)
            command['late_receipt_equal'] = command['late_business_equal'] = True
        self.verify_sources()
        self.eq('Late replay preserves source identities and SHA', self.sources, before_sources)
        calls = sum(row['path']=='/api/operations/confirm/' for row in self.http_calls)
        self.eq('Exactly 42 actual confirm HTTP calls', calls, e['replay']['total_confirm_calls'])
        self.eq('Exactly 14 ordered intents', len(self.confirmations), e['replay']['new_proposals'])
        self.report.update(final_business_snapshot=before_late,
            final_business_sha256=sha(encode(before_late).encode()), source_bytes_proof=self.sources,
            confirmations=self.confirmations, confirm_HTTP_calls=calls, final_counts=self.counts(),
            checks=self.checks, passed=len(self.checks), http_calls=self.http_calls)
        self.report['first_immutable_rows'] = self.first_immutable_rows

    def final_assertions(self, baseline, purchase, request, quoted, purchase_source,
            received, receipt_original, shipment, shipment_original, order, line, reservation,
            invoice, invoice_original, link, invoice_link_original, statement_import,
            statement_line, transaction, task):
        e, ceo, manager = self.e, self.clients['ceo'], self.clients['manager']
        for obj in (purchase,request,quoted,received,shipment,order,line,reservation,invoice,link,
                    statement_import,statement_line,transaction,task):
            obj.refresh_from_db()
        current_counts = self.counts()
        for label, expected in e['expected_deltas_after_bootstrap'].items():
            self.eq('Frozen domain count delta: '+label, current_counts[label]-baseline[label], expected)
        for label in set(current_counts)-set(e['expected_deltas_after_bootstrap']):
            self.eq('No unplanned model rows: '+label, current_counts[label]-baseline[label],0)
        # Configuration may add the existing erp_write singleton during bootstrap
        # upload; its revision is the sole permitted business-snapshot exclusion.
        events = Counter(self.models['erp.Event'].objects.values_list('action',flat=True))
        audits = Counter(self.models['operations.AuditEvent'].objects.values_list('action',flat=True))
        self.eq('Exactly thirteen typed ERP Events', dict(events), e['event_actions'])
        self.eq('Exactly three typed AuditEvents', dict(audits), e['audit_actions'])
        preserved = {'request':self.row(request),'quote':self.row(quoted),
            'approval_snapshot':purchase.approval_snapshot,'original_due':str(purchase.original_due),
            'documents':{code:self.row(self.one('operations.Document',pk=self.sources[code]['id'])) for code in purchase_source['documents']}}
        self.eq('B01 source history and original documents unchanged', preserved, purchase_source)
        self.eq('Original receipt movement full row unchanged after return', self.row(received), receipt_original)
        self.eq('Original shipment movement full row unchanged after invoice/payment', self.row(shipment), shipment_original)
        self.eq('Original InvoiceLink and frozen lines unchanged', self.row(link), invoice_link_original)
        actual_invoice = self.row(invoice)
        self.eq('Invoice changed only paid', {k:v for k,v in actual_invoice.items() if k!='paid'},
                {k:v for k,v in invoice_original.items() if k!='paid'})
        self.eq('Invoice link one actual line', len(link.lines), 1)
        self.eq('Invoice link actual SalesLine ID', link.lines[0]['line_id'], line.pk)
        self.money('Invoice link quantity', link.lines[0]['quantity'], e['invoice']['lines'][0]['quantity'])
        self.money('Invoice link price', link.lines[0]['price'], e['invoice']['lines'][0]['price'])
        for key in ('quantity','price','extras','received'):
            self.money('PO final '+key, getattr(purchase,key), e['purchase'].get(key+'_final',e['purchase'].get(key)))
        self.eq('PO final base status', purchase.status, e['purchase']['base_status_final'])
        self.eq('PO agreed due date remains', str(purchase.due_date), e['purchase']['due_date'])
        self.eq('PO actual source FKs', (purchase.request_id,purchase.quote_id,purchase.item_id,purchase.supplier_id),
                (request.pk,quoted.pk,self.ids['item'],self.ids['supplier']))
        for expected in e['movements']:
            movement = self.one('erp.Movement', kind=expected['kind'],lot__code=expected['lot_code'],reference=expected['reference'])
            self.money('Movement quantity: '+expected['alias'], movement.quantity, expected['quantity'])
            self.money('Movement carrying cost: '+expected['alias'], movement.cost, expected['cost'])
            self.eq('Movement currency: '+expected['alias'], movement.lot.currency, expected['currency_via_lot'])
            self.eq('Movement purchase FK: '+expected['alias'], movement.purchase_id,
                    purchase.pk if expected['purchase_code'] else None)
            self.eq('Movement sales FK: '+expected['alias'], movement.line_id,
                    line.pk if expected['line_alias'] else None)
            self.report.setdefault('movement_aliases',{})[expected['alias']] = movement.pk
        for expected in e['lots_final']:
            lot = self.one('erp.Lot',code=expected['code'])
            self.eq('Lot actual item/source/location: '+lot.code,
                (lot.item_id,lot.location.code,lot.revision,lot.currency,lot.quality,lot.documents),
                (self.ids['item'],expected['location_code'],expected['revision'],expected['currency'],expected['quality'],
                 {'certificate':self.ids[expected['certificate_code']]}))
            self.money('Lot final quantity: '+lot.code, lot.quantity, expected['quantity'])
            self.money('Lot unit carrying cost: '+lot.code, lot.unit_cost, expected['unit_cost'])
            self.money('Lot independent raw value: '+lot.code, lot.quantity*lot.unit_cost, expected['raw_value'])
            movements = sum((m.quantity for m in self.models['erp.Movement'].objects.filter(lot=lot)),D(0))
            self.money('Movement conservation: '+lot.code, movements, lot.quantity)
            reserved = sum((r.quantity for r in self.models['erp.Reservation'].objects.filter(lot=lot)),D(0))
            self.money('Lot final reserve: '+lot.code,reserved,expected['reserved'])
            self.money('Lot final available: '+lot.code,lot.quantity-reserved,expected['available'])
            self.check('Nonnegative physical/reserved/available: '+lot.code,min(lot.quantity,reserved,lot.quantity-reserved)>=0)
        returned = self.one('erp.GoodsReturn',code=e['supplier_return']['code'],source=received)
        self.eq('Exact source return direction',returned.direction,e['supplier_return']['direction'])
        self.eq('Return links exact new movement',returned.result_id,self.report['movement_aliases']['supplier_return_movement'])
        for key in ('quantity','allocated_cost','source_quantity','source_cost'):
            self.money('Source-bound return '+key,getattr(returned,key),e['supplier_return'][key])
        claim = self.one('erp.SupplierClaim',returned_goods=returned,record_kind='pending')
        self.eq('Supplier claim amount remains unknown',claim.agreed_amount,e['supplier_return']['claim_agreed_amount'])
        self.eq('No confirmed supplier claim',self.models['erp.SupplierClaim'].objects.filter(record_kind='confirmation').count(),0)
        inspection = self.one('erp.Inspection',lot=received.lot,result='approved',inspector_id=self.ids['manager_employee'])
        self.eq('Sales order persisted confirmed',order.status,e['sales']['base_status_final'])
        self.eq('Sales order explicit customer/owner/currency',
            (order.customer_id,order.owner_id,order.currency),(self.ids['customer'],self.ids['manager_employee'],'EUR'))
        for key in ('quantity','price','shipped','invoiced'):
            self.money('Actual sales '+key,getattr(line,key),e['sales'][key])
        self.money('Consumed reservation row preserved',reservation.quantity,'0.000')
        self.eq('Invoice same explicit customer',invoice.customer_id,self.ids['customer'])
        self.money('Actual Invoice amount',invoice.amount,e['invoice']['amount'])
        self.money('Actual Invoice paid',invoice.paid,e['invoice']['paid'])
        self.eq('Statement first import FK',statement_line.first_import_id,statement_import.pk)
        binding_fields = {'transaction_id','bound_at','bound_by_id','binding_snapshot'}
        self.eq('Original statement fields preserved through reconciliation',
            {k:v for k,v in self.row(statement_line).items() if k not in binding_fields},
            {k:v for k,v in self.checkpoints['original_statement_line'].items() if k not in binding_fields})
        self.eq('Statement approved original source FK',statement_import.document_id,self.sources[e['statement']['document_code']]['id'])
        self.eq('Statement historical source SHA',statement_import.source_sha256,self.sources[e['statement']['document_code']]['sha256'])
        self.eq('Statement source actor is authenticated CEO',statement_import.actor_id,self.identities['ceo'].pk)
        self.eq('Statement OneToOne actual Transaction',statement_line.transaction_id,transaction.pk)
        for key in ('direction','currency','description','category','contract_id','branch_id','archived_at'):
            self.eq('Transaction source-controlled '+key,getattr(transaction,key),e['transaction'][key])
        self.money('Transaction exact amount',transaction.amount,e['transaction']['amount'])
        self.eq('Transaction actual booking date',str(transaction.date),e['transaction']['date'])
        self.eq('Transaction explicit customer mapping',transaction.counterparty_id,self.ids['E2E-CUSTOMER-001'])
        self.eq('Statement binding actor is authenticated CEO',statement_line.bound_by_id,self.identities['ceo'].pk)
        allocation = self.one('finance.StatementAllocation',line=statement_line,allocation_key=e['statement']['allocation_key'])
        self.eq('Allocation exact Invoice',allocation.invoice_id,invoice.pk)
        self.eq('Allocation actual CEO',allocation.actor_id,self.identities['ceo'].pk)
        self.money('Allocation amount',allocation.amount,e['statement']['allocated'])
        payment = self.one('erp.Event',pk=allocation.payment_event_id,action='erp_payment')
        self.eq('Frozen payment key namespace',payment.payload['reference'],e['statement']['proposed_payment_reference'])
        self.eq('Payment actual Invoice',payment.payload['invoice_id'],invoice.pk)
        self.money('Payment amount',payment.payload['amount'],e['statement']['amount'])
        intent = self.one('finance.FinancialIntent',transaction=transaction)
        audit = self.one('operations.AuditEvent',action='transaction.create')
        self.eq('Finance audit actual creation actor',audit.payload['actor_id'],self.identities['ceo'].pk)
        self.eq('Task FK legacy/result/deadline/status',
            (task.assignee_employee_id,task.assignee,task.sales_order_id,task.result,str(task.deadline),task.status,task.priority,task.archived_at),
            (self.ids['manager_employee'],e['task']['assignee_legacy'],order.pk,e['task']['result'],e['task']['deadline'],
             e['task']['final_status'],e['task']['priority_on_done'],None))
        history = self.http(manager,'GET',f'/api/tasks/{task.pk}/history/')
        self.eq('Task has two real history events',len(history['items']),2)
        by_transition = {row['transition']:row for row in history['items']}
        self.eq('CEO created Task history actor',by_transition['create']['actor']['id'],self.identities['ceo'].pk)
        self.eq('Manager completed Task history actor',by_transition['complete']['actor']['id'],self.identities['manager'].pk)
        self.eq('Literal manager completion result',by_transition['complete']['after']['result'],e['task']['result'])
        self.eq('Literal manager completion reason',by_transition['complete']['reason'],e['task']['completion_reason'])
        self.eq('Stable historical responsible FK',by_transition['create']['after']['assignee_id'],self.ids['manager_employee'])
        self.check('Task history preserves source code',e['task']['request_code'] in encode(history))
        self.report['task_history'] = history
        self.read_report(purchase,order,line,invoice,statement_import,statement_line,transaction,task,returned,claim)

    def read_report(self,purchase,order,line,invoice,statement_import,statement_line,transaction,task,returned,claim):
        ceo, manager, e = self.clients['ceo'], self.clients['manager'], self.e
        snapshot = self.http(ceo,'GET','/api/erp/snapshot/')
        comparison = self.http(ceo,'GET','/api/operations/compare/?code='+e['requirement']['code'])
        task_read = self.http(ceo,'GET',f'/api/tasks/{task.pk}/')
        statement_read = self.http(ceo,'GET',f'/api/statements/lines/{statement_line.pk}/')
        import_read = self.http(ceo,'GET',f'/api/statements/imports/{statement_import.pk}/')
        statement_summary = self.http(ceo,'GET','/api/statements/summary/?currency=EUR')
        cash_summary = self.http(ceo,'GET','/api/transactions/summary/?currency=EUR')
        def one(rows,key,value):
            matched=[row for row in rows if row[key]==value]
            self.eq('One read source '+key+'='+str(value),len(matched),1)
            return matched[0]
        costs = one(snapshot['costs'],'order_id',order.pk)
        po = one(snapshot['purchases'],'id',purchase.pk)
        sales = one(snapshot['lines'],'id',line.pk)
        inv = one(snapshot['invoices'],'invoice_id',invoice.pk)
        self.money('Read PO gross received stays four',po['received'],e['purchase']['received_final'])
        self.money('Read PO open quantity six',po['open_quantity'],e['purchase']['open_quantity_final'])
        self.money('Read PO cancelled zero',po['cancelled_quantity'],e['purchase']['cancelled_final'])
        self.money('Request remains fully allocated',comparison['request']['allocated_quantity'],e['purchase']['request_allocated_final'])
        self.money('Return does not reopen procurement allocation',comparison['request']['remaining_quantity'],e['purchase']['request_remaining_unallocated_final'])
        self.money('Read sales delivered fully',sales['open_quantity'],e['sales']['open_delivery'])
        self.money('Read sales cancelled zero',sales['cancelled_quantity'],e['sales']['cancelled'])
        for key in ('order_value','shipped_value','shipped_cost','gross_margin'):
            self.money('CEO source report '+key,costs[key],e['sales'][key])
        for key in ('amount','paid','effective_credit','net_amount','open','customer_credit'):
            self.money('CEO invoice report '+key,inv[key],e['invoice'][key])
        self.eq('Task read actual result recorded',task_read['result_recorded'],True)
        self.eq('Task read not overdue',task_read['is_overdue'],e['task']['is_overdue'])
        self.eq('Task read current assignee matches actual Employee',task_read['assignee_id'],self.ids['manager_employee'])
        self.eq('Task current source code',task_read['order_code'],order.code)
        self.eq('Import immutable first receipt',import_read['first_commit_receipt'],self.confirmations[10]['first_receipt'])
        self.eq('Line detail first original download',statement_read['first_source']['document_id'],statement_import.document_id)
        self.eq('Line detail exact original SHA',statement_read['first_source']['checksum'],statement_import.source_sha256)
        self.eq('Line detail links Transaction',statement_read['line']['transaction_id'],transaction.pk)
        self.eq('Line detail settlement status',statement_read['line']['status'],'reconciled')
        self.money('Line detail allocated',statement_read['line']['allocated'],e['statement']['allocated'])
        self.money('Line detail unallocated',statement_read['line']['unallocated'],e['statement']['unallocated'])
        stat = one(statement_summary['currencies'],'currency','EUR')
        cash = one(cash_summary['currencies'],'currency','EUR')
        self.eq('Cash honest balance kind',cash_summary['balance_kind'],'period_movement')
        for key,expected in (('in','4.68'),('out','0.00'),('net','4.68')):
            self.eq('Cash exact decimal string: '+key,cash[key],expected)
            self.eq('Statement imported exact string: '+key,stat['imported'][key],expected)
            self.eq('Statement recorded exact string: '+key,stat['recorded'][key],expected)
            self.eq('Statement no unposted '+key,stat['unposted'][key],'0.00')
        self.eq('Statement incoming fully allocated',stat['incoming'],{'allocated':'4.68','unallocated':'0.00'})
        lots = snapshot['lots']
        stock = sum((D(row['quantity']) for row in lots),D(0))
        stock_value = sum((D(row['quantity'])*D(row['unit_cost']) for row in lots),D(0))
        po_open_value = D(po['open_quantity'])*(D(po['price'])+D(po['extras'])/D(po['quantity']))
        self.money('Independent report stock quantity',stock,e['ceo_report']['stock_quantity'])
        self.money('Independent report stock value',stock_value,e['ceo_report']['stock_value'])
        self.money('Independent report PO open value',po_open_value,e['ceo_report']['open_po_value'])
        sources = [
            {'kind':'request','code':e['requirement']['code'],'url':'/api/operations/requests/'},
            {'kind':'quote','code':e['quote']['code'],'url':'/api/operations/compare/?code='+e['requirement']['code']},
            {'kind':'purchase','id':purchase.pk,'code':purchase.code,'url':'/api/erp/snapshot/','row_key':'purchases'},
            *[{'kind':row['kind'],'id':self.report['movement_aliases'][row['alias']],
                'code':row['lot_code'] if row['kind']=='receipt' else row['reference'],
                'url':'/api/erp/snapshot/','row_key':'movements'} for row in e['movements']],
            {'kind':'sales_order','id':order.pk,'code':order.code,'url':'/api/erp/snapshot/','row_key':'orders'},
            {'kind':'invoice','id':invoice.pk,'code':invoice.code,'url':'/api/erp/snapshot/','row_key':'invoices'},
            {'kind':'statement_source','id':statement_import.document_id,'code':e['statement']['document_code'],
                'url':statement_read['first_source']['download_url']},
            {'kind':'statement_line','id':str(statement_line.pk),'url':f'/api/statements/lines/{statement_line.pk}/'},
            {'kind':'transaction','id':transaction.pk,'url':f'/api/transactions/{transaction.pk}/'},
            {'kind':'task','id':task.pk,'url':f'/api/tasks/{task.pk}/history/'}]
        self.report['ceo_source_report'] = {
            'currency':'EUR','shipped_value':costs['shipped_value'],'shipped_cost':costs['shipped_cost'],
            'gross_difference':costs['gross_margin'],'paid':inv['paid'],'receivable':inv['open'],
            'stock_quantity':format(stock,'.3f'),'stock_value':format(stock_value,'.2f'),
            'po_open_quantity':po['open_quantity'],'po_open_value':format(po_open_value,'.2f'),
            'supplier_return_quantity':str(returned.quantity),'supplier_return_carrying_cost':str(returned.allocated_cost),
            'supplier_claim_confirmed_amount':claim.agreed_amount,'cash_in':cash['in'],'cash_out':cash['out'],
            'net_cash_movement':cash['net'],'bank_balance':None,'task_status':task_read['status'],
            'still_open':['PO remaining six units','supplier claim unconfirmed'],'sources':sources}
        self.report['actual_read_sources'] = {'erp_snapshot':snapshot,'statement_line':statement_read,
            'statement_import':import_read,'statement_summary':statement_summary,'cash_summary':cash_summary,'task':task_read}
        bank_doc = statement_import.document_id
        for path,status in [(f'/api/operations/documents/{bank_doc}/',404),
            (f'/api/operations/documents/{bank_doc}/download/',404),
            (f'/api/statements/lines/{statement_line.pk}/',403),
            (f'/api/statements/imports/{statement_import.pk}/',403),
            ('/api/statements/summary/',403),('/api/transactions/summary/',403),
            (f'/api/transactions/{transaction.pk}/',404)]:
            self.http(manager,'GET',path,status=status)
        canaries = [e['statement']['external_id'],e['statement']['account_ref'],e['statement']['document_code'],
            e['transaction']['description'],statement_import.source_sha256,str(statement_line.pk),str(statement_import.pk),
            e['statement']['proposed_payment_reference']]
        for path in ('/api/operations/documents/','/api/transactions/','/api/transactions.json',
                     '/api/operations/export/','/api/erp/export/','/api/erp/snapshot/',
                     f'/api/tasks/{task.pk}/',f'/api/tasks/{task.pk}/history/'):
            result = self.http(manager,'GET',path)
            text = encode(result)
            self.check('No private bank canary in manager read: '+path,all(secret not in text for secret in canaries))
        for doc in e['source_documents']:
            if doc['creation_phase']=='bootstrap':
                raw = self.http(manager,'GET',f"/api/operations/documents/{self.sources[doc['code']]['id']}/download/")
                self.eq('Manager reads permitted original: '+doc['code'],sha(raw),doc['sha256'])


def protected_hashes():
    roots = [ROOT]
    supplied = json.loads(os.environ.get('BOS_E2E_PROTECTED_ROOTS', '[]'))
    if not isinstance(supplied,list) or any(not isinstance(p,str) for p in supplied):
        raise RuntimeError('Protected roots must be an explicit JSON list of paths.')
    roots += [Path(p).resolve() for p in supplied]
    return {str(p):sha(p.read_bytes()) for root in roots for p in sorted(root.glob('*.sqlite3'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    report = {'schema':'bos.gate6.actual.v1','gate':6,'complete':False,
        'started_at':datetime.now(timezone.utc).isoformat(),
        'environment':{'system':platform.system(),'python':sys.version,'python_minor':list(sys.version_info[:2])},
        'scope':'One synthetic EUR gate6 only; not PostgreSQL/Windows/browser or all-eleven-gate acceptance.'}
    work, environment = reserve_environment()
    output = args.output.resolve() if args.output else work/'e2e-report.json'
    if output.exists():
        raise RuntimeError('Refusing to replace an existing report.')
    protected_before = protected_hashes()
    scenario = None
    try:
        report['environment'].update(environment)
        if os.environ.get('BOS_TEST_DEPENDENCIES'):
            sys.path.append(os.environ['BOS_TEST_DEPENDENCIES'])
        import django
        django.setup()
        from check_support import prove_database
        from django.db import connection
        prove_database()
        report['environment']['actual_vendor'] = connection.vendor
        with connection.cursor() as cursor:
            cursor.execute('SHOW server_version' if connection.vendor=='postgresql' else 'SELECT sqlite_version()')
            report['environment']['database_version'] = str(cursor.fetchone()[0])
        oracle_path = ROOT/'tests'/'e2e_expected.json'
        oracle_bytes = oracle_path.read_bytes()
        expected = json.loads(oracle_bytes)
        if expected['installation_provenance']['source_draft_sha256'] != DRAFT_SHA:
            raise AssertionError('Frozen oracle source SHA differs.')
        report['oracle_sha256'] = sha(oracle_bytes)
        report['oracle_source_draft_sha256'] = DRAFT_SHA
        from scripts.verify import source_digest
        report['source_sha256'] = source_digest()
        scenario = Scenario(expected,report)
        scenario.execute()
        report['complete'] = True
    except BaseException as exc:
        report['failure'] = {'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
        if scenario:
            report.update(checks=scenario.checks,passed=len(scenario.checks),http_calls=scenario.http_calls,
                confirmations=scenario.confirmations,source_bytes_proof=scenario.sources)
    finally:
        protected_after = protected_hashes()
        report.update(protected_source_databases_before=protected_before,protected_source_databases_after=protected_after,
            protected_source_databases_unchanged=protected_before==protected_after,
            completed_at=datetime.now(timezone.utc).isoformat())
        report['complete'] = report['complete'] and report['protected_source_databases_unchanged']
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(encode(report)+'\n',encoding='utf-8')
    public = {'gate':6,'complete':report['complete'],'passed':report.get('passed',0),
        'vendor':report['environment'].get('actual_vendor'),'confirm_HTTP_calls':report.get('confirm_HTTP_calls'),
        'source_databases_unchanged':report['protected_source_databases_unchanged'],
        'report':str(output),'report_sha256':sha(output.read_bytes())}
    if not report['complete']:
        public['failure'] = report.get('failure',{}).get('message','Source database SHA changed.')
    print(json.dumps(public,ensure_ascii=False))
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
