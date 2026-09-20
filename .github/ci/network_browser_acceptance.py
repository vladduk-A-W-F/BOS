"""NETWORK-BROWSER: bounded real Chrome acceptance in a new hosted CI stand.

No browser install, full E2E suite, real records, production activation, or
blocked local/CDN route. Only this candidate's new network UI is exercised.
"""
import argparse
import csv
from decimal import Decimal as D
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def digest():
    spec = importlib.util.spec_from_file_location('network_verifier', ROOT / 'scripts/verify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.source_digest()


def finalize(output):
    output.mkdir(parents=True, exist_ok=True)
    if not (output / 'report.json').exists():
        write(output / 'report.json', {'status': 'BLOCKED_BEFORE_HARNESS', 'accepted_scoped': False,
            'browser_run': False, 'technical_ready': False, 'pilot_allowed': False})
    report = json.loads((output / 'report.json').read_text())
    print('BOS_NETWORK_BROWSER_RESULT ' + json.dumps({key: report.get(key) for key in
        ('status', 'accepted_scoped', 'browser_run', 'candidate_sha', 'runtime_sha256', 'chrome_version',
         'source_unchanged', 'source_databases_unchanged', 'disposable_data_removed', 'errors', 'checks', 'limitations')}, ensure_ascii=False))
    write(output / 'sha256-index.json', {p.relative_to(output).as_posix():
        {'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size}
        for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'sha256-index.json'})


def fixture():
    """Fresh demo seed plus owned, deterministic acceptance-only boundary rows."""
    from django.core.management import call_command
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Group, Permission
    from erp.models import Item, Location, Lot
    from employees.models import Employee
    from operations.models import Document
    from erp.service import dispatch, write_lock
    from django.db import transaction
    call_command('migrate', interactive=False, verbosity=1)
    call_command('seed_network_demo', dataset='workday', verbosity=1)
    accounts = {}
    for role in ('ceo', 'manager', 'observer'):
        password = secrets.token_urlsafe(24)
        user = get_user_model().objects.create_user(username='network-browser-' + role, password=password)
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        permissions = ['view_document', 'download_document']
        if role != 'observer':
            permissions.append('export_workspace')
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='operations',
            content_type__model='document', codename__in=permissions))
        accounts[role] = (user.username, password)
    source = Location.objects.order_by('id').first()
    destination = Location.objects.exclude(branch_id=source.branch_id).order_by('id').first()
    owner = Employee.objects.order_by('id').first()
    with transaction.atomic():
        write_lock()
        item = Item.objects.create(code='BROWSER-UAH', name='Синтетичний виріб для приймання', currency='UAH')
        opened = dispatch({'action': 'erp_opening', 'code': 'BROWSER-STOCK', 'item_id': item.pk,
            'location_id': source.pk, 'quantity': '10.000', 'unit_cost': '25.00',
            'currency': 'UAH', 'revision': 'A', 'reason': 'Synthetic browser fixture'}, role='ceo')
        dispatch({'action': 'erp_quality', 'lot_id': opened['lot_id'], 'result': 'approved',
            'inspector_id': owner.pk, 'note': 'Synthetic browser fixture'}, role='ceo')
        euro = Item.objects.create(code='BROWSER-EUR', name='Історичний EUR приклад', currency='EUR')
        dispatch({'action': 'erp_opening', 'code': 'BROWSER-EUR-LOT', 'item_id': euro.pk,
            'location_id': source.pk, 'quantity': '2.000', 'unit_cost': '7.50',
            'currency': 'EUR', 'revision': 'A', 'reason': 'Synthetic EUR preservation'}, role='ceo')
        raw = b'PRIVATE SYNTHETIC CEO DOCUMENT\n'
        doc = Document.objects.create(code='BROWSER-CEO-ONLY', revision='A', title='Синтетичний закритий документ',
            filename='synthetic-private.txt', content=raw, size=len(raw), checksum=sha(raw),
            text=raw.decode(), sections=[{'source': 'fixture', 'text': raw.decode()}],
            access_level='ceo', status='approved')
        hidden = Item.objects.create(code='BROWSER-PRIVATE', name='Синтетичний приватний виріб', document=doc)
        Lot.objects.create(code='BROWSER-PRIVATE-LOT', item=hidden, location=source, revision='A',
            quantity='1.000', unit_cost='13.00', currency='UAH', quality='approved')
    return accounts, {'source_id': source.pk, 'destination_id': destination.pk,
        'branch_id': source.branch_id, 'lot_id': opened['lot_id'], 'owner_id': owner.pk,
        'private_document_id': doc.pk, 'private_document_code': doc.code}


class Acceptance:
    def __init__(self, browser, output, report, base, accounts, facts):
        self.browser, self.output, self.report = browser, output, report
        self.base, self.accounts, self.facts = base, accounts, facts
        self.page = None

    def check(self, name, condition, **evidence):
        self.report['checks'].append({'name': name, 'passed': bool(condition), **evidence})
        if not condition:
            raise AssertionError(name)

    def record(self, response):
        url = urlsplit(response.url)
        if url.netloc == urlsplit(self.base).netloc:
            self.report['http'].append({'path': url.path, 'query': url.query, 'status': response.status,
                'method': response.request.method})

    def login(self, role):
        from playwright.sync_api import expect
        context = self.browser.new_context(viewport={'width': 1440, 'height': 900}, locale='uk-UA',
            timezone_id='Europe/Kyiv', reduced_motion='reduce')
        page = context.new_page()
        page.set_default_timeout(15000)
        page.on('response', self.record)
        page.on('pageerror', lambda error: self.report['page_errors'].append(str(error)))
        page.on('console', lambda message: self.report['console'].append({'type': message.type, 'text': message.text}))
        self.page = page
        page.goto(self.base, wait_until='domcontentloaded')
        page.get_by_label('Логін', exact=True).fill(self.accounts[role][0])
        page.get_by_label('Пароль', exact=True).fill(self.accounts[role][1])
        page.get_by_role('button', name='Увійти', exact=True).click()
        expect(page.locator('.bos-navbar')).to_be_visible()
        page.get_by_role('button', name='ERP', exact=True).click()
        # ERP selects network as its first submenu; close the navigation flyout.
        page.get_by_role('button', name='Мережа та операції', exact=True).click()
        self.ready()
        return context

    def ready(self):
        self.page.get_by_role('status').filter(has_text='Завантаження мережі та операцій').wait_for(state='hidden')
        self.page.locator('.network-kpis').wait_for(state='visible')
        self.check('network has no visible load error', self.page.locator('.network-workspace [role=alert]').count() == 0)

    def snapshot(self, query='currency=UAH'):
        response = self.page.context.request.get(self.base + '/api/erp/network/?' + query)
        self.check('network HTTP response is 200', response.status == 200, query=query)
        data = response.json()
        self.report['snapshots'].append({'query': query, 'body': data})
        return data

    def post(self, path, payload):
        # Actual browser fetch uses the application's existing CSRF wrapper.
        return self.page.evaluate("""async ([path, payload]) => {
            const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
            return {status:r.status,body:await r.json()};
        }""", [path, payload])

    def group(self, label):
        self.page.locator('.network-groups').get_by_role('button', name=label, exact=True).click()

    def table(self, label):
        self.group('Операції')
        self.page.locator('.network-tabs').get_by_role('button', name=re.compile('^' + re.escape(label) + r'\s+\d+$')).click()

    def row(self, code):
        return self.page.locator('.network-workspace tbody tr').filter(has=self.page.get_by_text(code, exact=True))

    def fill(self, fields):
        dialog = self.page.locator('dialog[open]').last
        for label, value in fields.items():
            control = dialog.get_by_label(label, exact=True)
            if control.evaluate('(el)=>el.tagName') == 'SELECT':
                control.select_option(str(value))
            else:
                control.fill(str(value))
        return dialog

    def preview(self, fields):
        dialog = self.fill(fields)
        with self.page.expect_response(lambda r: r.url.endswith('/api/erp/preview/') and r.request.method == 'POST') as pending:
            dialog.get_by_role('button', name='Перевірити операцію', exact=True).click()
        response = pending.value
        self.check('UI preview succeeds', response.status == 200)
        proposal = response.json()
        self.report['proposals'].append({'id': proposal['id'], 'action': proposal['payload']['action']})
        dialog.get_by_role('button', name='Погодити й виконати', exact=True).wait_for(state='visible')
        return proposal

    def confirm(self):
        with self.page.expect_response(lambda r: r.url.endswith('/api/operations/confirm/') and r.request.method == 'POST') as pending:
            self.page.locator('dialog[open]').last.get_by_role('button', name='Погодити й виконати', exact=True).click()
        response = pending.value
        self.check('UI confirmation succeeds', response.status == 200)
        self.page.locator('dialog[open]').wait_for(state='hidden')
        self.ready()
        self.report['receipts'].append(response.json())
        return response.json()

    def shot(self, name):
        self.page.screenshot(path=str(self.output / (name + '.png')), full_page=True)

    def desktop(self):
        from playwright.sync_api import expect
        page = self.page
        initial = self.snapshot()
        self.check('all four work groups exist', page.locator('.network-groups button').count() == 4)
        self.check('Ukraine geographical regions rendered', page.locator('.network-regions path').count() >= 24)
        self.check('map contains real point pins', page.locator('.network-pin').count() >= 7)
        self.shot('desktop-overview-1440')
        for group in ('Операції', 'Документи й звірки', 'Контроль строків'):
            self.group(group)
            self.shot('desktop-' + {'Операції': 'operations', 'Документи й звірки': 'documents', 'Контроль строків': 'workflow'}[group])
        self.check('synthetic workflow does not claim acceleration', initial['workflow']['comparison']['available'] is False)
        self.check('workflow is populated', initial['workflow']['metrics']['request_count'] > 0)
        self.group('Огляд')
        with page.expect_response(lambda r: '/api/erp/network/?' in r.url and 'branch_id=' in r.url):
            page.get_by_label('Філія', exact=True).select_option(str(self.facts['branch_id']))
        self.ready()
        with page.expect_response(lambda r: '/api/erp/network/?' in r.url and 'location_id=' in r.url):
            page.get_by_label('Робоча точка', exact=True).select_option(str(self.facts['source_id']))
        self.ready()
        query = 'currency=UAH&branch_id=' + str(self.facts['branch_id']) + '&location_id=' + str(self.facts['source_id'])
        filtered = self.snapshot(query)
        self.check('point filter exact', [x['id'] for x in filtered['rows']['points']] == [self.facts['source_id']])
        self.check('UAH value reconciles visible lots', D(filtered['metrics']['inventory_value']) == sum((D(x['value']) for x in filtered['rows']['lots']), D(0)))
        self.check('filtered map has one selected pin', page.locator('.network-pin').count() == 1 and page.locator('.network-pin.selected').count() == 1)
        self.table('Склад')
        self.check('filtered table rows equal snapshot', page.locator('.network-workspace tbody tr').count() == len(filtered['rows']['lots']))
        link = page.get_by_role('link', name='Експорт цього реєстру · CSV', exact=True)
        csv_response = page.context.request.get(self.base + link.get_attribute('href'))
        self.check('CSV export succeeds', csv_response.status == 200)
        exported = list(csv.DictReader(io.StringIO(csv_response.body().decode('utf-8-sig')), delimiter=';'))
        self.check('CSV rows match table IDs, currency and value',
            [(int(r['id']), r['currency'], D(r['value'])) for r in exported] ==
            [(r['id'], r['currency'], D(r['value'])) for r in filtered['rows']['lots']])
        page.locator('.network-options summary').click()
        self.check('converter initially off', not page.get_by_label('Показати довідковий еквівалент').is_checked())
        page.get_by_label('Показати довідковий еквівалент').check()
        rate = page.get_by_label('Гривень за 1 EUR', exact=True)
        for invalid in ('0', '-1'):
            rate.fill(invalid)
            self.check('invalid converter rate rejected: ' + invalid, page.locator('.network-converted').count() == 0)
        rate.fill('40')
        expect(page.locator('.network-converted')).to_be_visible()
        expected = page.evaluate("v => new Intl.NumberFormat('uk-UA',{style:'currency',currency:'EUR',maximumFractionDigits:2}).format(Number(v)/40)", filtered['metrics']['inventory_value'])
        self.check('reference conversion arithmetic', page.locator('.network-converted strong').first.inner_text() == expected)
        self.check('converter does not mutate accounting', self.snapshot(query)['metrics'] == filtered['metrics'])
        with page.expect_response(lambda r: '/api/erp/network/?' in r.url and 'currency=EUR' in r.url):
            page.get_by_label('Валюта наявних записів', exact=True).select_option('EUR')
        self.ready()
        eur = self.snapshot(query.replace('UAH', 'EUR'))
        self.check('EUR preserved separately', eur['metrics']['inventory_value'] == '15.00' and all(r['currency'] == 'EUR' for r in eur['rows']['lots']))
        with page.expect_response(lambda r: '/api/erp/network/?' in r.url and 'currency=UAH' in r.url):
            page.get_by_label('Валюта наявних записів', exact=True).select_option('UAH')
        self.ready()
        with page.expect_response(lambda r: '/api/erp/network/?' in r.url and 'branch_id' not in r.url):
            page.get_by_label('Філія', exact=True).select_option('')
        self.ready()
        self.group('Документи й звірки')
        document_button = page.get_by_role('button', name='Відкрити документ', exact=True).first
        document_button.focus()
        document_button.press('Enter')
        expect(page.locator('dialog[open]')).to_be_visible()
        expect(page.get_by_role('link', name='Завантажити джерело', exact=True)).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.locator('dialog[open]')).to_have_count(0)
        self.check('document dialog keyboard returns focus', document_button.evaluate('(el)=>document.activeElement===el'))

    def movement(self):
        page = self.page
        self.table('Склад')
        self.row('BROWSER-STOCK').get_by_role('button', name='Відправити', exact=True).click()
        fields = {'Кількість': '3.000', 'Точка призначення': self.facts['destination_id'],
            'Номер переміщення': 'BROWSER-TRANSFER', 'Підстава': 'Синтетичне поповнення точки'}
        before = self.snapshot()
        self.preview(fields)
        self.check('preview leaves business rows unchanged', self.snapshot()['rows'] == before['rows'])
        page.locator('dialog[open]').get_by_role('button', name='Закрити', exact=True).click()
        self.check('cancel leaves business rows unchanged', self.snapshot()['rows'] == before['rows'])
        self.row('BROWSER-STOCK').get_by_role('button', name='Відправити', exact=True).click()
        proposal = self.preview(fields)
        receipt = self.confirm()
        replay = self.post('/api/operations/confirm/', {'proposal_id': proposal['id'], 'confirmed': True})
        self.check('same proposal replays original receipt', replay['status'] == 200 and replay['body'] == receipt)
        after = self.snapshot()
        stock = next(x for x in after['rows']['lots'] if x['id'] == self.facts['lot_id'])
        self.check('dispatch decrements source once', D(stock['quantity']) == D('7'))
        self.table('У дорозі')
        self.row('BROWSER-TRANSFER').get_by_role('button', name='Прийняти у точці', exact=True).click()
        self.preview({'Код прийнятої партії': 'BROWSER-RECEIPT', 'Підстава приймання': 'Синтетична перевірена доставка'})
        result = self.confirm()
        received = next(x for x in self.snapshot()['rows']['lots'] if x['id'] == result['lot_id'])
        self.check('receipt is separate pending quality lot', received['quality'] == 'pending' and D(received['quantity']) == 3 and received['location_id'] == self.facts['destination_id'])
        self.table('Склад')
        self.row('BROWSER-RECEIPT').get_by_role('button', name='Перевірити якість', exact=True).click()
        self.preview({'Рішення': 'approved', 'Перевірив': self.facts['owner_id'], 'Підстава / результати вимірювань': 'Синтетична перевірка якості'})
        self.confirm()
        checked = next(x for x in self.snapshot()['rows']['lots'] if x['id'] == result['lot_id'])
        self.check('quality is a separate confirmed operation', checked['quality'] == 'approved')

    def retention(self):
        page = self.page
        original = next(r for r in self.snapshot()['rows']['invoices'] if D(r['collectible']) > 100 and D(r['retained']) == 0)
        self.table('Рахунки')
        self.row(original['code']).get_by_role('button', name='Утримання', exact=True).click()
        self.preview({'Сума утримання у валюті рахунку': '50.00', 'Номер утримання': 'BROWSER-HOLD', 'Умови / підстава утримання': 'Синтетичне гарантійне утримання'})
        self.confirm()
        held = next(r for r in self.snapshot()['rows']['invoices'] if r['invoice_id'] == original['invoice_id'])
        self.check('hold preserves receivable', D(held['receivable']) == D(original['receivable']) and D(held['retained']) == 50)
        self.table('Рахунки')
        self.row(original['code']).get_by_role('button', name='Оплата', exact=True).click()
        self.preview({'Сума у валюті рахунку': held['collectible'], 'Унікальний номер підтвердження оплати': 'BROWSER-PAY-AVAILABLE'})
        self.confirm()
        self.table('Утримання')
        self.row('BROWSER-HOLD').get_by_role('button', name='Зняти утримання', exact=True).click()
        self.preview({'Підстава зняття': 'Синтетичне завершення гарантії'})
        self.confirm()
        released = next(r for r in self.snapshot()['rows']['invoices'] if r['invoice_id'] == original['invoice_id'])
        self.check('release is not payment', D(released['receivable']) == 50 and D(released['collectible']) == 50 and D(released['retained']) == 0)
        self.table('Рахунки')
        self.row(original['code']).get_by_role('button', name='Оплата', exact=True).click()
        self.preview({'Сума у валюті рахунку': '50.00', 'Унікальний номер підтвердження оплати': 'BROWSER-PAY-RELEASED'})
        self.confirm()
        paid = next(r for r in self.snapshot()['rows']['invoices'] if r['invoice_id'] == original['invoice_id'])
        self.check('remaining payment settles invoice', D(paid['receivable']) == 0)

    def mobile(self):
        for width, height in ((390, 844), (320, 740)):
            self.page.set_viewport_size({'width': width, 'height': height})
            for label, slug in (('Огляд', 'overview'), ('Операції', 'operations'), ('Документи й звірки', 'documents'), ('Контроль строків', 'workflow')):
                self.group(label)
                if label == 'Операції':
                    self.table('Склад')
                self.page.locator('.network-heading').scroll_into_view_if_needed()
                geometry = self.page.evaluate("""() => {const e=document.querySelector('.network-workspace');const r=e.getBoundingClientRect();return {width:innerWidth,left:r.left,right:r.right,rootScroll:document.documentElement.scrollWidth,bodyScroll:document.body.scrollWidth};}""")
                self.check('mobile container within viewport ' + str(width) + ' ' + slug,
                    geometry['left'] >= -1 and geometry['right'] <= width + 1 and geometry['rootScroll'] <= width + 1, geometry=geometry)
                self.shot('mobile-' + str(width) + '-' + slug)
            self.table('Склад')
            scroll = self.page.locator('.network-workspace .erp-table').evaluate('(el)=>{el.scrollLeft=el.scrollWidth;return {left:el.scrollLeft,scroll:el.scrollWidth,client:el.clientWidth};}')
            self.check('mobile table allows horizontal scroll ' + str(width), scroll['scroll'] <= scroll['client'] or scroll['left'] > 0, geometry=scroll)
        self.page.set_viewport_size({'width': 1440, 'height': 900})

    def access(self, role):
        data = self.snapshot()
        self.check(role + ' cannot see private CEO document', all(x['id'] != self.facts['private_document_id'] for x in data['documents']))
        self.check(role + ' has no financial totals', all(k not in data['metrics'] for k in ('inventory_value', 'retained', 'receivable', 'collectible')))
        self.check(role + ' cannot see private stock', all(x['code'] != 'BROWSER-PRIVATE-LOT' for x in data['rows']['lots']))
        private = self.page.context.request.get(self.base + '/api/operations/documents/' + str(self.facts['private_document_id']) + '/download/')
        self.check(role + ' direct private document denied', private.status in (403, 404))
        denied = self.post('/api/erp/preview/', {'action': 'erp_hold_payment', 'invoice_id': 1, 'amount': '1.00', 'code': 'DENIED', 'reason': 'Synthetic denial check'})
        self.check(role + ' direct finance action denied', denied['status'] == 403)
        if role == 'observer':
            exported = self.page.context.request.get(self.base + '/api/erp/network/export/?currency=UAH&table=lots')
            self.check('observer direct export denied', exported.status == 403)
            self.table('Склад')
            self.check('observer no transfer button', self.page.get_by_role('button', name='Відправити', exact=True).count() == 0)
        self.group('Документи й звірки')
        self.shot(role + '-documents-1440')


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'runner-started.json').exists():
        raise RuntimeError('Refuse repeated invocation in this output directory')
    write(output / 'runner-started.json', {'started_at': time.time()})
    report = {'scope': 'NETWORK-BROWSER new feature only', 'status': 'NOT_RUN', 'accepted_scoped': False,
        'browser_run': False, 'full_suite': False, 'historical_e2e_rerun': False, 'A11_blocked_routes_retried': False,
        'technical_ready': False, 'pilot_allowed': False, 'checks': [], 'http': [], 'snapshots': [],
        'proposals': [], 'receipts': [], 'page_errors': [], 'console': [], 'errors': [],
        'visual_review': 'PENDING_INDEPENDENT_SCREENSHOT_REVIEW',
        'limitations': ['Bounded network feature acceptance only; historical gates remain open',
            'No live permission-revocation race, typed stale UI recovery, or lost confirm response injection',
            'Workflow stages are read; RFQ/quote/purchase create flows not exercised in this browser scope',
            'Converter reload persistence and JSON export equivalence not exercised',
            'CEO-only document uses synthetic legacy BLOB fixture for denial checks',
            'No full accessibility/screen-reader audit, Windows, or production acceptance']}
    report['harness_sha256'] = sha(Path(__file__).read_bytes())
    process = None
    work = None
    source_before = None
    try:
        if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_RUN_ATTEMPT') != '1':
            raise RuntimeError('Only first attempt on the newly authorized GitHub runner is allowed')
        candidate = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        if (os.environ.get('GITHUB_EVENT_NAME') != 'push' or os.environ.get('GITHUB_REF_NAME') != 'feat/network-operations-20260920' or os.environ.get('GITHUB_REPOSITORY') != 'vladduk-A-W-F/BOS'):
            raise RuntimeError('Unexpected runner event, branch, or repository')
        if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT, text=True).strip():
            raise RuntimeError('Clean exact checkout required')
        runner_temp = Path(os.environ['RUNNER_TEMP']).resolve()
        if output.resolve() == ROOT or not output.resolve().is_relative_to(runner_temp):
            raise RuntimeError('Evidence must be outside source under RUNNER_TEMP')
        if candidate != os.environ['BOS_NETWORK_CANDIDATE_SHA']:
            raise RuntimeError('Candidate SHA mismatch')
        source_before = digest()
        report.update(candidate_sha=candidate, runtime_sha256=source_before,
            source_database_canaries={str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in ROOT.rglob('*.sqlite3')})
        if source_before != os.environ['BOS_NETWORK_RUNTIME_SHA256']:
            raise RuntimeError('Reviewed runtime source digest mismatch')
        chrome = shutil.which('google-chrome') or shutil.which('google-chrome-stable')
        if not chrome:
            raise RuntimeError('Preinstalled Chrome unavailable; no install/download fallback')
        report['chrome_version'] = subprocess.check_output([chrome, '--version'], text=True).strip()
        report['chrome_path'] = chrome
        work = Path(tempfile.mkdtemp(prefix='bos-network-browser-', dir=os.environ['RUNNER_TEMP']))
        media = work / 'media'
        media.mkdir(mode=0o700)
        os.environ.update(BOS_TEST_DB_NAME=str(work / 'check_network.sqlite3'), BOS_TEST_MEDIA=str(media),
            BOS_VERIFY_DB='sqlite', BOS_DATA_MODE='demo', DJANGO_SETTINGS_MODULE='verification_settings',
            PYTHONDONTWRITEBYTECODE='1')
        import django
        django.setup()
        accounts, facts = fixture()
        report['fixture'] = facts
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = 'http://127.0.0.1:' + str(port)
        with (output / 'server.log').open('wb') as server_log:
            process = subprocess.Popen([sys.executable, '-B', 'manage.py', 'runserver', '127.0.0.1:' + str(port),
                '--noreload', '--settings=verification_settings'], cwd=ROOT, stdout=server_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 25
            while True:
                if process.poll() is not None:
                    raise RuntimeError('Disposable Django server exited before readiness')
                try:
                    with urlopen(base + '/api/auth/csrf/', timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    if time.monotonic() > deadline:
                        raise RuntimeError('Disposable server readiness timeout; no relaunch')
                    time.sleep(.2)
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=chrome, headless=True)
                report['browser_run'] = True
                check = Acceptance(browser, output, report, base, accounts, facts)
                try:
                    context = check.login('ceo')
                    check.desktop()
                    check.movement()
                    check.retention()
                    check.mobile()
                    context.close()
                    for role in ('manager', 'observer'):
                        context = check.login(role)
                        check.access(role)
                        context.close()
                    check.check('no uncaught JavaScript errors', not report['page_errors'])
                    report['accepted_scoped'] = True
                except Exception:
                    if check.page and not check.page.is_closed():
                        check.shot('failure-current-viewport')
                    raise
                finally:
                    browser.close()
    except Exception as exc:
        report['errors'].append(type(exc).__name__ + ': ' + str(exc))
        (output / 'exception.log').write_text(traceback.format_exc())
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if work is not None:
            from django.db import connections
            connections.close_all()
            shutil.rmtree(work)
            report['disposable_data_removed'] = not work.exists()
        report['source_unchanged'] = source_before is not None and digest() == source_before
        report['source_databases_unchanged'] = report.get('source_database_canaries') == {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in ROOT.rglob('*.sqlite3')}
        report['accepted_scoped'] = bool(report['accepted_scoped'] and report['source_unchanged'] and report['source_databases_unchanged'] and not report['errors'])
        report['status'] = 'PASS_SCOPED' if report['accepted_scoped'] else 'FAIL_OR_BLOCKED'
        write(output / 'report.json', report)
        finalize(output)
    return 0 if report['accepted_scoped'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--finalize-only', action='store_true')
    arguments = parser.parse_args()
    if arguments.finalize_only:
        finalize(arguments.output)
    else:
        sys.exit(run(arguments.output))
