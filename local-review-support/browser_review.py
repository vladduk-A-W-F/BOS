"""Verify this persistent synthetic instance with normal owner login, then close only the check browser."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from review_secrets import ROOT, runtime_root, read_secrets
from review_control import support_manifest

ORIGIN = 'http://127.0.0.1:8876'


def main():
    global ROOT
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, default=ROOT)
    ROOT = runtime_root(parser.parse_args().runtime_root)
    sys.path.insert(0, str(ROOT / 'source'))
    from scripts.check_ui import edge_path
    from scripts.verify import source_digest
    from playwright.sync_api import expect, sync_playwright
    prepared = json.loads((ROOT / 'prepared.json').read_text(encoding='utf-8'))
    if source_digest() != prepared['source_sha256']:
        raise RuntimeError('Persistent review source differs from accepted snapshot.')
    if support_manifest() != prepared['support']:
        raise RuntimeError('Review support differs from its prepared manifest.')
    output = ROOT / 'evidence'
    report_path = output / 'browser-review.json'
    if report_path.exists():
        raise RuntimeError('Review evidence already exists; refusing to overwrite it.')
    os.environ['TEMP'] = str(ROOT / 'temp')
    os.environ['TMP'] = str(ROOT / 'temp')
    identity = read_secrets(ROOT)
    errors = []
    screenshots = []
    with tempfile.TemporaryDirectory(prefix='review-browser-', dir=ROOT / 'temp') as profile:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch_persistent_context(
                profile, executable_path=str(edge_path()), headless=True,
                viewport={'width': 1440, 'height': 1000})
            try:
                page = browser.pages[0]
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(ORIGIN, wait_until='networkidle')
                expect(page.get_by_role('heading', name='Увійти до робочого простору')).to_be_visible()
                expect(page.get_by_role('button', name='Відкрити навчальну компанію', exact=True)).to_have_count(0)
                page.get_by_label('Логін', exact=True).fill(identity['username'])
                page.get_by_label('Пароль', exact=True).fill(identity['password'])
                with page.expect_response(lambda response: response.url == ORIGIN + '/api/auth/login/') as login:
                    page.get_by_role('button', name='Увійти', exact=True).click()
                assert login.value.status == 200
                expect(page.get_by_text('Оберіть сферу діяльності підприємства', exact=True)).to_be_visible()
                page.get_by_text('Виробництво', exact=True).click()
                page.get_by_role('button', name='Розпочати роботу →', exact=True).click()
                navigation = page.get_by_label('Розділ системи', exact=True)
                if navigation.is_visible():
                    navigation.select_option('heli:')
                else:
                    page.get_by_role('button', name='Сьогодні', exact=True).click()
                heading = page.get_by_role('heading', name='Філії та робочі точки', exact=True)
                expect(heading).to_be_visible()
                expect(page.get_by_role('button', name='Нове замовлення у цій точці', exact=True)).to_be_visible()
                point = page.get_by_role('combobox', name=re.compile('^Робоча точка'))
                expect(point).to_have_count(1)
                options = point.locator('option').evaluate_all('(xs)=>xs.map(x=>({value:x.value,text:x.textContent}))')
                kyiv = [value for value in options if 'Київ' in value['text']]
                assert len(kyiv) == 1
                point.select_option(kyiv[0]['value'])
                status = page.evaluate('''async()=>{
                  const response=await fetch('/api/operations/status/');
                  return {status:response.status,body:await response.json()};
                }''')
                assert status['status'] == 200 and status['body']['role'] == 'ceo'
                assert status['body']['mode'] == 'working' and status['body']['ai_configured'] is False
                for width in (1440, 390):
                    page.set_viewport_size({'width': width, 'height': 1000})
                    heading.scroll_into_view_if_needed()
                    path = output / ('review-' + str(width) + '.png')
                    page.screenshot(path=str(path))
                    screenshots.append({'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                        'bytes': path.stat().st_size})
                assert not errors, errors
                report = {'url': ORIGIN, 'source_sha256': prepared['source_sha256'],
                          'checked_at': datetime.now(timezone.utc).isoformat(), 'login_status': 200,
                          'identity': status, 'synthetic': True, 'normal_password_login': True,
                          'demo_login_button_absent': True, 'selected_workpoint': kyiv[0],
                          'screenshots': screenshots, 'page_errors': errors,
                          'scope': 'Persistent review visibility and normal owner login; not acceptance gates'}
            finally:
                browser.close()
    report['check_browser_closed'] = True
    report['check_browser_profile_removed'] = not Path(profile).exists()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Persistent review UI verified: ' + ORIGIN)


if __name__ == '__main__':
    main()
