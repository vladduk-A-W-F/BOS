"""Gate 10: a new local Edge profile and disposable synthetic BoS installation.

No existing browser, remote debugging endpoint, database or server is reused.
This is the viewport/accessibility matrix and one UAH preview/confirmation,
not the separate gate 6 end-to-end business acceptance scenario.
"""
import argparse
import base64
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
import traceback
from urllib.request import urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import verify
from scripts import ui_process_identity as process_owner

SCHEMA = 'bos.gate10.local.v1'
CHECKS = ('viewport_390', 'viewport_768', 'viewport_1440', 'native_zoom_200',
          'keyboard_escape', 'network_failure_recovery', 'uah_preview_confirm')
METRICS = '''() => ({width: innerWidth, height: innerHeight,
  dpr: devicePixelRatio, visual_scale: visualViewport.scale,
  css_zoom: getComputedStyle(document.body).zoom,
  scroll_width: document.documentElement.scrollWidth})'''
NEW_ORDER = 'Нове замовлення у цій точці'
SERVER_BOOTSTRAP = '''import sys
from scripts.ui_process_identity import child_handshake
child_handshake()
from django.core.management import execute_from_command_line
execute_from_command_line(['manage.py','runserver',sys.argv[1],'--noreload'])
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def database_hashes(root):
    return {p.name: digest(p) for p in root.glob('*.sqlite3')}


def validate_server_identity(value, nonce):
    return process_owner.validate_identity(value, nonce)['pid']


class OwnedServer:
    """Retain the actual server handle; Windows venv Python is a launcher."""
    def __init__(self, source, env, port, log, identity_path, proof=None):
        self.handle = None
        self.kernel = None
        self.launcher = None
        self.pid = None
        self.proof = proof if proof is not None else {}
        self.nonce = uuid.uuid4().hex
        self.identity_path = identity_path
        self.proof['ownership'] = 'pending child self-identity and parent held-handle verification'
        child_env = dict(env, BOS_UI_SERVER_IDENTITY=str(identity_path), BOS_UI_SERVER_NONCE=self.nonce,
                         BOS_UI_SERVER_PARENT=json.dumps(process_owner.current_identity()))
        try:
            self.launcher = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', '-c', SERVER_BOOTSTRAP,
                                              f'127.0.0.1:{port}'], cwd=source, env=child_env,
                                             stdout=log, stderr=subprocess.STDOUT,
                                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if process_owner.IS_WINDOWS:
                kernel = process_owner.kernel_api()
                self.proof['launcher_identity'] = process_owner.process_identity(kernel, self.launcher._handle,
                                                                                 self.launcher.pid)
            deadline = time.monotonic() + 10
            while not identity_path.exists():
                if self.launcher.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Own server did not report its actual child PID.')
                time.sleep(.05)
            value = self.acquire_identity()
            if self.poll() is not None:
                raise RuntimeError('Owned server exited before ownership release.')
            process_owner.atomic_json(identity_path.with_name(identity_path.stem + '-release.json'), value)
            self.proof['ownership_verified_before_application'] = True
        except BaseException:
            try:
                self.stop()
            except BaseException as cleanup_error:
                self.proof['cleanup_error_type'] = type(cleanup_error).__name__
            raise

    def acquire_identity(self):
        value = json.loads(self.identity_path.read_text(encoding='utf-8'))
        identity = process_owner.validate_identity(value, self.nonce,
                    expected_pid=None if process_owner.IS_WINDOWS else self.launcher.pid)
        if process_owner.IS_WINDOWS:
            self.kernel, self.handle = process_owner.open_verified_windows(identity)
        self.pid = identity['pid']
        self.proof.update(launcher_pid=self.launcher.pid, actual_server_pid=self.pid,
                          child_identity=identity, created_ticks=identity['created_ticks'],
                          ownership='self-reported child identity matched while exact process handle was held')
        return value

    def poll(self):
        if self.handle is not None:
            return 0 if process_owner.exited(self.kernel, self.handle) else None
        return self.launcher.poll()

    def stop(self):
        stopped = False
        try:
            if (self.handle is None and self.pid is None and self.launcher is not None
                    and self.identity_path.exists()):
                self.acquire_identity()
            if self.handle is not None:
                if not process_owner.exited(self.kernel, self.handle):
                    if not self.kernel.TerminateProcess(self.handle, 0):
                        raise RuntimeError('Owned child termination failed.')
                stopped = process_owner.exited(self.kernel, self.handle, 10000)
            elif self.launcher is not None and self.pid == self.launcher.pid:
                if self.launcher.poll() is None:
                    self.launcher.terminate()
                self.launcher.wait(timeout=10)
                stopped = True
        finally:
            if self.handle is not None:
                self.kernel.CloseHandle(self.handle)
                self.handle = None
            if self.launcher is not None:
                try:
                    self.launcher.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.launcher.terminate()
                    self.launcher.wait(timeout=5)
            self.proof['actual_server_exit_verified'] = stopped
            self.proof['launcher_exit_verified'] = self.launcher is not None and self.launcher.poll() is not None
        return stopped and self.proof['launcher_exit_verified']


@contextmanager
def owned_runtime(report):
    parent = Path(tempfile.gettempdir()).resolve()
    work = Path(tempfile.mkdtemp(prefix='boscheck-ui-', dir=parent)).resolve()
    try:
        yield str(work)
    finally:
        process = report.get('isolation', {}).get('server_process')
        safe = process is None or all(process.get(key) is True for key in
                                      ('actual_server_exit_verified', 'launcher_exit_verified'))
        if not safe:
            report['cleanup']['runtime_retained_reason'] = 'Actual child/launcher exit not both proved; owned runtime retained.'
        elif work.parent != parent or not work.name.startswith('boscheck-ui-'):
            raise RuntimeError('Owned runtime cleanup escaped its original absolute parent.')
        else:
            shutil.rmtree(work)


def edge_path():
    candidates = [os.environ.get('BOS_UI_EDGE_PATH')]
    for variable in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
        base = os.environ.get(variable)
        if base:
            candidates.append(str(Path(base) / 'Microsoft/Edge/Application/msedge.exe'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise RuntimeError('A local Microsoft Edge executable is required; set BOS_UI_EDGE_PATH. No browser will be downloaded.')


def order_facts(database, code):
    # Read-only oracle on our allocated SQLite file. Browser POSTs alone mutate it.
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
        return {
            'orders': connection.execute('SELECT count(*) FROM erp_salesorder').fetchone()[0],
            'events': connection.execute('SELECT count(*) FROM erp_event').fetchone()[0],
            'matches': connection.execute('SELECT id, currency, branch_id FROM erp_salesorder WHERE code=?', (code,)).fetchall(),
            'lines': connection.execute('SELECT l.quantity,l.price FROM erp_salesline l JOIN erp_salesorder o ON o.id=l.order_id WHERE o.code=?', (code,)).fetchall(),
        }


def validate_modal_focus(samples):
    """Native Edge can traverse its own chrome; page controls must stay inert."""
    assert samples and any(sample['inside'] for sample in samples), samples
    for index, sample in enumerate(samples):
        if sample['inside']:
            continue
        assert sample['tag'] == 'BODY' and sample['document_has_focus'] is False, samples
        assert index + 1 < len(samples) and samples[index + 1]['inside'], samples
        assert samples[index + 1]['document_has_focus'] is True, samples


def choose_named_option(locator, needle):
    """A missing parent must fail before evaluate_all can silently return []."""
    count = locator.count()
    assert count == 1, {'required_parent_count': 1, 'actual_parent_count': count, 'required_option': needle}
    choices = locator.locator('option').evaluate_all('(xs)=>xs.filter(x=>x.value).map(x=>({value:x.value,text:x.textContent}))')
    matches = [x for x in choices if needle in x['text']]
    assert len(matches) == 1, {'required_option': needle, 'actual_options': choices}
    locator.select_option(matches[0]['value'])
    return matches[0]


def run_browser(origin, profile, database, output, report):
    from playwright.sync_api import sync_playwright, expect

    browser = edge_path()
    report['browser'] = {'executable': str(browser), 'executable_sha256': digest(browser),
                         'profile': str(profile), 'headless': True, 'existing_profile': False}
    screenshots = []
    failures = []
    external = []

    def check(name, **detail):
        report['checks'].append({'id': name, 'passed': True, **detail})
        print('BOS_UI_CHECK ' + name, flush=True)

    with sync_playwright() as playwright:
        expect.set_options(timeout=15000)
        context = playwright.chromium.launch_persistent_context(
            str(profile), executable_path=str(browser), headless=True, no_viewport=True,
            args=['--window-size=1470,1000'], timeout=20000)
        try:
            report['browser']['version'] = context.browser.version
            def local_only(route):
                if route.request.url.startswith(origin + '/'):
                    route.continue_()
                else:
                    external.append(route.request.url)
                    route.abort()
            context.route('**/*', local_only)
            page = context.pages[0]
            # Session belongs to the process just launched above; never connect
            # to a remote/existing CDP endpoint. Playwright's screenshot clipping
            # misinterprets native-zoom CSS dimensions on this Edge version.
            capture = context.new_cdp_session(page)
            page.set_default_timeout(15000)
            page.on('pageerror', lambda error: failures.append(str(error)))

            def screenshot(name):
                path = output / (name + '.png')
                layout = capture.send('Page.getLayoutMetrics')
                payload = base64.b64decode(capture.send('Page.captureScreenshot',
                    {'format': 'png', 'fromSurface': True, 'captureBeyondViewport': False})['data'])
                dimensions = list(struct.unpack('>II', payload[16:24]))
                expected = [layout['layoutViewport'][key] for key in ('clientWidth', 'clientHeight')]
                assert dimensions == expected, (dimensions, expected)
                path.write_bytes(payload)
                report.setdefault('screenshot_metrics', []).append({'path': path.name,
                    'png_dimensions': dimensions, 'layout': layout,
                    'method': 'own browser raw surface; no clip, resize or image transformation'})
                screenshots.append(path.name)

            def ready():
                expect(page.get_by_role('heading', name='Філії та робочі точки', exact=True)).to_be_visible()
                expect(page.get_by_role('button', name=NEW_ORDER, exact=True)).to_be_visible()

            def select_record(locator, needle):
                # A wrapping native-select label includes its option text in
                # Playwright's label matcher; callers use its unique prefix.
                expect(locator).to_have_count(1)
                expect(locator).to_be_visible()
                return choose_named_option(locator, needle)

            def combo(scope, label):
                return scope.get_by_role('combobox', name=re.compile('^' + re.escape(label)))

            def open_home():
                navigation = page.get_by_label('Розділ системи', exact=True)
                if navigation.is_visible():
                    navigation.select_option('heli:')
                else:
                    page.get_by_role('button', name='Сьогодні', exact=True).click()
                ready()
                select_record(combo(page, 'Робоча точка'), 'Київ')

            def fit():
                value = page.evaluate(METRICS)
                if value['scroll_width'] > value['width'] + 1:
                    raise AssertionError(f'Page horizontal overflow: {value}')
                geometry = page.locator('dialog[open], .bos-workpoints').evaluate_all('''elements => elements.map(el=>{
                    const r=el.getBoundingClientRect(), style=getComputedStyle(el), saved=el.scrollTop;
                    el.scrollTop=el.scrollHeight; const bottom=el.scrollTop; el.scrollTop=saved;
                    return {kind:el.tagName,left:r.left,right:r.right,top:r.top,bottom:r.bottom,
                        width:el.clientWidth,scrollWidth:el.scrollWidth,height:el.clientHeight,
                        scrollHeight:el.scrollHeight,overflowY:style.overflowY,reachableScrollBottom:bottom};
                })''')
                for box in geometry:
                    assert box['left'] >= -1 and box['right'] <= value['width'] + 1, box
                    assert box['scrollWidth'] <= box['width'] + 1, box
                    if box['kind'] == 'DIALOG':
                        assert box['top'] >= -1 and box['bottom'] <= value['height'] + 1, box
                        if box['scrollHeight'] > box['height'] + 1:
                            assert box['overflowY'] in ('auto', 'scroll'), box
                            assert box['reachableScrollBottom'] >= box['scrollHeight'] - box['height'] - 1, box
                value['content_geometry'] = geometry
                return value

            page.goto(origin, wait_until='networkidle')
            expect(page.get_by_role('heading', name='Увійти до робочого простору')).to_be_visible()
            page.get_by_role('button', name='Відкрити навчальну компанію', exact=True).click()
            expect(page.get_by_text('Оберіть сферу діяльності підприємства', exact=True)).to_be_visible()
            page.get_by_text('Виробництво', exact=True).click()
            page.get_by_role('button', name='Розпочати роботу →', exact=True).click()
            open_home()
            report['identity'] = page.evaluate('''async () => {
                const r=await fetch('/api/auth/me/'); return {status:r.status, body:await r.json()};
            }''')
            if report['identity']['status'] != 200:
                raise AssertionError('Real demo login did not establish an authenticated identity.')

            # Native browser zoom changes DPR/layout width. CSS zoom, page-scale
            # emulation and pinch zoom are deliberately neither set nor accepted.
            before = fit()
            page.goto('edge://settings/appearance')
            zoom_before = page.evaluate('new Promise(r=>chrome.settingsPrivate.getDefaultZoom(r))')
            page.evaluate('''new Promise((resolve,reject)=>chrome.settingsPrivate.setDefaultZoom(2,
                ()=>chrome.runtime.lastError?reject(Error(chrome.runtime.lastError.message)):resolve()))''')
            zoom_after = page.evaluate('new Promise(r=>chrome.settingsPrivate.getDefaultZoom(r))')
            page.goto(origin, wait_until='networkidle')
            open_home()
            after = fit()
            assert zoom_before == 1 and zoom_after == 2
            assert abs(after['dpr'] / before['dpr'] - 2) < .02
            assert abs(before['width'] / after['width'] - 2) < .03
            assert after['visual_scale'] == 1 and after['css_zoom'] == '1'
            page.get_by_role('heading', name='Філії та робочі точки', exact=True).scroll_into_view_if_needed()
            screenshot('native-zoom-200')
            page.get_by_role('button', name=NEW_ORDER, exact=True).click()
            expect(page.locator('dialog[open]')).to_be_visible()
            fit()
            screenshot('native-zoom-200-dialog')
            page.keyboard.press('Escape')
            expect(page.locator('dialog[open]')).to_have_count(0)
            check('native_zoom_200', before=before, after=after,
                  browser_zoom_before=zoom_before, browser_zoom_after=zoom_after,
                  method='own Edge profile settingsPrivate default zoom')
            page.goto('edge://settings/appearance')
            page.evaluate('new Promise(r=>chrome.settingsPrivate.setDefaultZoom(1,r))')
            page.goto(origin, wait_until='networkidle')
            open_home()

            for width in (390, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 1000})
                ready()
                metric = fit()
                assert metric['width'] == width and metric['dpr'] == before['dpr']
                page.get_by_role('heading', name='Філії та робочі точки', exact=True).scroll_into_view_if_needed()
                screenshot(f'viewport-{width}')
                opener = page.get_by_role('button', name=NEW_ORDER, exact=True)
                opener.focus()
                page.keyboard.press('Enter')
                dialog = page.locator('dialog[open]')
                expect(dialog).to_be_visible()
                fit()
                screenshot(f'viewport-{width}-dialog')
                focus = []
                # Sequential native tabbing exercises the real modal focus trap.
                def tab_sample():
                    page.keyboard.press('Tab')
                    focus.append(page.evaluate('''() => ({inside:!!document.activeElement.closest('dialog[open]'),
                        document_has_focus:document.hasFocus(),
                        tag:document.activeElement.tagName, label:document.activeElement.getAttribute('aria-label')||document.activeElement.textContent.slice(0,80)})'''))
                    expect(dialog).to_be_visible()
                for _ in range(18):
                    tab_sample()
                if not focus[-1]['inside']:
                    tab_sample()
                validate_modal_focus(focus)
                page.keyboard.press('Escape')
                expect(dialog).to_have_count(0)
                expect(opener).to_be_focused()
                check(f'viewport_{width}', metrics=metric, dialog_keyboard_focus=focus)
            check('keyboard_escape', viewports=[390, 768, 1440],
                  activation='Enter', traversal='18 Tab presses; verify return from native browser chrome if needed',
                  no_outside_page_control_focus=True, escape_restores_opener=True)

            # Drop only this profile's workpoints request; retain the real app,
            # transport error, empty-state rendering and explicit recovery.
            def unavailable(route):
                route.abort('connectionfailed')
            context.route('**/api/erp/workpoints/', unavailable)
            try:
                page.get_by_role('button', name='Оновити робочі точки', exact=True).click()
                expect(page.get_by_role('alert').filter(has_text='Не вдалося перевірити дані робочих точок')).to_be_visible()
                expect(page.get_by_role('button', name=NEW_ORDER, exact=True)).to_have_count(0)
                screenshot('network-failure')
            finally:
                context.unroute('**/api/erp/workpoints/', unavailable)
            page.get_by_role('button', name='Оновити робочі точки', exact=True).click()
            ready()
            screenshot('network-recovered')
            check('network_failure_recovery', failed_route='/api/erp/workpoints/',
                  hidden_mutation_action=True, recovery='explicit refresh')

            code = 'UI-UAH-' + uuid.uuid4().hex[:12]
            initial = order_facts(database, code)
            branch = select_record(combo(page, 'Робоча точка'), 'Київ')
            page.get_by_role('button', name=NEW_ORDER, exact=True).click()
            dialog = page.locator('dialog[open]')
            dialog.get_by_label('Номер', exact=True).fill(code)
            customer = select_record(combo(dialog, 'Клієнт'), 'Український навчальний покупець')
            owner = select_record(combo(dialog, 'Відповідальний'), 'Київ')
            dialog.get_by_label('Бажана дата поставки', exact=True).fill('2026-12-31')
            expect(combo(dialog, 'Валюта')).to_have_value('UAH')
            dialog.get_by_role('button', name='Додати позицію', exact=True).click()
            item = select_record(dialog.get_by_label('Компонент або виріб', exact=True), 'UA-DEMO-PRODUCT')
            dialog.get_by_label('Кількість', exact=True).fill('2')
            dialog.get_by_label('Ціна одиниці', exact=True).fill('12.34')
            with page.expect_response(lambda r: r.url == origin + '/api/erp/preview/' and r.request.method == 'POST') as response:
                dialog.get_by_role('button', name='Перевірити операцію', exact=True).click()
            preview = response.value
            assert preview.status == 200, preview.text()
            proposal = preview.json()
            expect(dialog.get_by_text('Перевірку пройдено', exact=True)).to_be_visible()
            after_preview = order_facts(database, code)
            assert initial == after_preview, (initial, after_preview)
            assert proposal['payload']['currency'] == 'UAH'
            screenshot('uah-preview')
            with page.expect_response(lambda r: r.url == origin + '/api/operations/confirm/' and r.request.method == 'POST') as response:
                dialog.get_by_role('button', name='Погодити й виконати', exact=True).click()
            confirmation = response.value
            assert confirmation.status == 200, confirmation.text()
            expect(dialog).to_have_count(0)
            ready()
            expect(page.get_by_role('heading', name='Результат погодженої дії', exact=True)).to_be_visible()
            after_confirm = order_facts(database, code)
            assert after_confirm['orders'] == initial['orders'] + 1
            assert after_confirm['events'] == initial['events'] + 1
            assert len(after_confirm['matches']) == 1 and after_confirm['matches'][0][1] == 'UAH'
            assert after_confirm['matches'][0][2] == int(branch['value'])
            assert len(after_confirm['lines']) == 1
            quantity, price = map(lambda x: Decimal(str(x)), after_confirm['lines'][0])
            assert quantity == Decimal('2') and price == Decimal('12.34')
            screenshot('uah-confirmed')
            check('uah_preview_confirm', code=code, branch=branch, customer=customer, owner=owner, item=item,
                  before=initial, after_preview=after_preview, after_confirm=after_confirm,
                  total=str(quantity * price), currency='UAH',
                  preview_http_status=preview.status, confirm_http_status=confirmation.status)
            # Separate vertical-flow evidence; it does not replace the seven Gate 10 checks.
            from scripts.flow_browser_checks import run_flow_checks
            run_flow_checks(page, origin, database, output, report)
            assert not failures, failures
            assert not external, external
            report['page_errors'] = failures
            report['external_requests'] = external
        except Exception:
            try:
                screenshot('failure')
            except Exception as exc:
                report['failure_capture_error'] = str(exc)
            report['page_errors'] = failures
            report['external_requests'] = external
            raise
        finally:
            context.close()
            report['cleanup']['browser_closed'] = True
            report['screenshots'] = screenshots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'evidence/ui/ui-report.json')
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise RuntimeError('Refusing to overwrite an existing UI report; choose a fresh output directory.')
    if not __debug__ or os.environ.get('PYTHONOPTIMIZE', '') not in ('', '0'):
        raise RuntimeError('Assertions must be enabled.')
    source_sha = verify.source_digest()
    source_databases = database_hashes(ROOT)
    report = {'schema': SCHEMA, 'gate': 10, 'complete': False,
              'source_sha256': source_sha, 'started_at': datetime.now(timezone.utc).isoformat(),
              'checks': [], 'cleanup': {}, 'artifacts': [], 'screenshots': [],
              'scope': 'Local UI matrix and one UAH order preview/confirmation; not gate 6.'}
    server = None
    server_log = None
    work = None
    try:
        with owned_runtime(report) as folder:
            work = Path(folder).resolve()
            source = work / 'source'
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(
                '.git', '.venv', '.venv-ci', 'venv', '__pycache__', '*.pyc', '*.sqlite*', '*.db',
                '.env', '.env.*', 'evidence', 'output', 'upload', 'media', 'rehearsal-media', 'node_modules'))
            database = work / ('boscheck_' + uuid.uuid4().hex + '.sqlite3')
            media = work / 'media'
            media.mkdir()
            profile = work / 'edge-profile'
            profile.mkdir()
            env = os.environ.copy()
            env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', DJANGO_SETTINGS_MODULE='verification_settings',
                       BOS_VERIFY_DB='sqlite', BOS_DATA_MODE='demo', BOS_TEST_DB_NAME=str(database),
                       BOS_TEST_MEDIA=str(media), BOS_PROJECT_ROOT=str(source))
            report['isolation'] = {'runtime': str(work), 'source_copy': str(source), 'database': str(database),
                                   'media': str(media), 'database_initially_absent': not database.exists(),
                                   'vendor': 'sqlite', 'source_databases_before': source_databases}
            for command in ('migrate', 'seed_bos_demo', 'seed_erp_demo', 'seed_bos_workspace', 'seed_bos_ua'):
                result = subprocess.run([sys.executable, '-X', 'utf8', '-B', 'manage.py', command,
                                         *(['--noinput'] if command == 'migrate' else [])],
                                        cwd=source, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        encoding='utf-8', errors='replace', timeout=90)
                (output.parent / (command + '.log')).write_text(result.stdout, encoding='utf-8')
                if result.returncode:
                    raise RuntimeError(f'{command} failed with exit code {result.returncode}; see its log.')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            origin = f'http://127.0.0.1:{port}'
            report['isolation'].update(origin=origin, port=port)
            server_log = (output.parent / 'server.log').open('w', encoding='utf-8')
            try:
                report['isolation']['server_process'] = {}
                server = OwnedServer(source, env, port, server_log, work / 'server-identity.json',
                                     report['isolation']['server_process'])
                report['isolation']['server_pid'] = server.pid
                deadline = time.monotonic() + 25
                while True:
                    if server.poll() is not None:
                        raise RuntimeError('Own Django server exited before it became ready.')
                    try:
                        with urlopen(origin + '/api/runtime/status/', timeout=1) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError('Own Django server did not become ready in 25 seconds.')
                    time.sleep(.15)
                (output.parent / 'runtime.json').write_text(json.dumps(report['isolation'], indent=2), encoding='utf-8')
                print('BOS_UI_LOCAL_URL ' + origin, flush=True)
                run_browser(origin, profile, database, output.parent, report)
            finally:
                report['cleanup']['server_stopped'] = server is not None and server.stop()
                server_log.close()
        report['cleanup']['runtime_removed'] = not work.exists()
        report['complete'] = {x['id'] for x in report['checks'] if x['passed']} == set(CHECKS)
    except BaseException as exc:
        report['error'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
        print(traceback.format_exc(), file=sys.stderr, flush=True)
    finally:
        if work is not None:
            report['cleanup']['runtime_removed'] = not work.exists()
        report['source_databases_unchanged'] = source_databases == database_hashes(ROOT)
        report['source_unchanged'] = source_sha == verify.source_digest()
        report['complete'] = (report['complete'] and report['source_databases_unchanged'] and report['source_unchanged']
                              and all(report['cleanup'].get(key) is True for key in
                                      ('browser_closed', 'server_stopped', 'runtime_removed')))
        for path in sorted(output.parent.iterdir()):
            if path.is_file() and path != output:
                report['artifacts'].append({'path': path.name, 'sha256': digest(path), 'bytes': path.stat().st_size})
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'gate': 10, 'report': str(output), 'report_sha256': digest(output),
                          'complete': report['complete'], 'source_sha256': source_sha}), flush=True)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
