"""Real HTTPS acceptance for a newly created synthetic installation only.

The owning check_install process supplies the TLS trust, credentials and ports.
No database path or server process is accepted or modified here.
"""
import hashlib
import http.client
from http.cookies import SimpleCookie
import json
import secrets
import time
from urllib.parse import urlsplit


def exercise_https(*, origin, http_port, context, password, canary_values, private_snapshot, checks):
    https_port = urlsplit(origin).port or 443
    cookies = {}
    def request(method, path, body=None, *, extra=None, csrf=True, plain=False, remember=True):
        headers = {'Host': f'localhost:{http_port if plain else https_port}'}
        if cookies:
            headers['Cookie'] = '; '.join(k + '=' + v for k, v in cookies.items())
        if method not in ('GET', 'HEAD'):
            headers['Origin'] = origin
            if csrf and cookies.get('csrftoken'):
                headers['X-CSRFToken'] = cookies['csrftoken']
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        headers.update(extra or {})
        conn = (http.client.HTTPConnection('127.0.0.1', http_port, timeout=8) if plain else
                http.client.HTTPSConnection('localhost', https_port, context=context, timeout=8))
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            data, received = response.read(), response.getheaders()
            if remember:
                for name, value in received:
                    if name.lower() == 'set-cookie':
                        parsed = SimpleCookie(value)
                        for morsel in parsed.values():
                            if morsel.value and morsel.value not in canary_values:
                                canary_values.append(morsel.value)
                        cookies.update({k: v.value for k, v in parsed.items()})
            return response.status, data, dict(received), received
        finally:
            conn.close()
    deadline = time.monotonic() + 10
    while True:
        try:
            status, body, headers, raw = request('GET', '/api/auth/csrf/')
            break
        except (ConnectionError, OSError):
            if time.monotonic() > deadline:
                raise
            time.sleep(.1)
    assert status == 200, (status, body)
    checks.append({'case': 'verified_TLS_and_secure_csrf_cookie', 'status': status,
                   'secure_cookie': any(n.lower() == 'set-cookie' and 'Secure' in v for n, v in raw)})
    assert checks[-1]['secure_cookie']
    scenarios = [
        ('liveness', 'GET', '/health/live/', None, {}, False, 200),
        ('readiness', 'GET', '/health/ready/', None, {}, False, 200),
        ('health_post_refused', 'POST', '/health/ready/', None, {}, False, 405),
        ('demo_endpoint_disabled', 'POST', '/api/auth/demo/', {}, {}, False, 404),
        ('anonymous_api', 'GET', '/api/tasks/', None, {}, False, 401),
        ('private_media', 'GET', '/media/private_CANARY_FILE.txt', None, {}, False, 404),
        ('wrong_host', 'GET', '/', None, {'Host': 'hostile.invalid'}, False, 421),
        ('forwarded_spoof_stripped', 'GET', '/api/auth/csrf/', None,
         {'X-Forwarded-For': '10.0.0.1, 10.0.0.2', 'X-Forwarded-Proto': 'http,https',
          'X-Forwarded-Host': 'hostile.invalid', 'Forwarded': 'for=10.0.0.1;proto=http'}, False, 200),
        ('canonical_http_redirect', 'GET', '/api/auth/csrf/', None, {}, True, 308),
        ('http_wrong_host', 'GET', '/', None, {'Host': 'hostile.invalid'}, True, 421),
        ('csrf_required', 'POST', '/api/auth/login/', {'username': 'tls-ceo', 'password': password}, {}, False, 403),
    ]
    for label, method, path, payload, extra, plain, expected in scenarios:
        status, body, headers, raw = request(method, path, payload, extra=extra, plain=plain, csrf=False)
        assert status == expected, (label, status, body[:150])
        if label == 'canonical_http_redirect':
            assert headers['Location'] == origin + path
        checks.append({'case': label, 'status': status})
    status, body, headers, raw = request('POST', '/api/auth/login/', {'username': 'tls-ceo', 'password': password})
    assert status == 200, (status, body)
    session = next(SimpleCookie(v) for n, v in raw if n.lower() == 'set-cookie' and 'bos_session_' in v)
    morsel = next(iter(session.values()))
    assert morsel['secure'] and morsel['httponly'] and morsel['samesite'] == 'Lax'
    checks.append({'case': 'genuine_login_secure_httponly_lax', 'status': status})
    status, body, _, _ = request('GET', '/api/tasks/')
    assert status == 200, (status, body)
    checks.append({'case': 'authenticated_api', 'status': status})
    status, body, _, _ = request('GET', '/api/runtime/status/')
    runtime = json.loads(body)
    assert status == 200 and runtime['mode'] == 'server' and runtime['data_mode'] == 'working'
    checks.append({'case': 'actual_server_version_mode', 'status': status, 'version': runtime['version']})
    status, body, _, _ = request('GET', '/')
    assert status == 200 and b'app.js' in body and runtime['version'].encode() in body
    checks.append({'case': 'frontend_shell', 'status': status})
    status, body, _, _ = request('GET', '/assets/app.js')
    assert status == 200 and len(body) > 1000
    checks.append({'case': 'frontend_asset', 'status': status})
    status, body, _, _ = request('POST', '/api/auth/logout/', {}, extra={'Origin': 'https://hostile.invalid'})
    assert status == 403, (status, body)
    checks.append({'case': 'foreign_origin_valid_cookie_refused', 'status': status})
    marker = 'BOS_CANARY_PRIVATE_PAYLOAD_' + secrets.token_hex(8)
    canary_values.append(marker)
    boundary = 'BoSBoundary' + secrets.token_hex(8)
    original = (marker + '\nСинтетична специфікація HTTPS').encode()
    chunks = []
    for k, value in {'code': 'TLS-DOC', 'revision': 'A', 'title': 'Специфікація HTTPS'}.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{value}\r\n'.encode())
    chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{marker}.txt"\r\nContent-Type: text/plain\r\n\r\n'.encode() + original + b'\r\n')
    chunks.append(f'--{boundary}--\r\n'.encode())
    status, body, _, _ = request('POST', '/api/operations/documents/upload/?marker=' + marker,
        b''.join(chunks), extra={'Content-Type': 'multipart/form-data; boundary=' + boundary, 'Authorization': 'Bearer ' + marker})
    assert status == 201, (status, body)
    doc = json.loads(body)
    checks.append({'case': 'HTTPS_private_upload', 'status': status})
    status, body, _, _ = request('GET', f'/api/operations/documents/{doc["id"]}/download/')
    assert status == 200 and body == original
    checks.append({'case': 'download_exact_original', 'status': status, 'sha256': hashlib.sha256(body).hexdigest()})
    status, body, _, _ = request('POST', f'/api/operations/documents/{doc["id"]}/review/', {'checksum': doc['checksum']})
    assert status == 200, (status, body)
    checks.append({'case': 'review_original', 'status': status})
    before_private = private_snapshot()
    status, before_documents, _, _ = request('GET', '/api/operations/documents/')
    assert status == 200
    oversize = {'case': 'oversized_request_413_no_partial_document', 'passed': False, 'status': None}
    try:
        status, body, _, _ = request('POST', '/api/operations/documents/upload/', b'x' * (13 * 1024 * 1024),
            extra={'Content-Type': 'application/octet-stream'})
        oversize.update(status=status, passed=status == 413)
    except (OSError, http.client.HTTPException) as error:
        # Retain the exact failing oracle and continue other independent facts.
        # A reset/timeout/502 never substitutes for a received HTTP 413.
        oversize['error_type'] = type(error).__name__
    status, after_documents, _, _ = request('GET', '/api/operations/documents/')
    assert status == 200 and before_documents == after_documents
    assert private_snapshot() == before_private, 'oversized upload must not leave a private orphan'
    oversize['documents_and_private_bytes_unchanged'] = True
    checks.append(oversize)
    status, body, _, _ = request('GET', '/static/admin/css/base.css')
    assert status == 200 and b'body' in body
    checks.append({'case': 'collected_admin_static', 'status': status})
    status, body, _, _ = request('POST', '/api/auth/logout/', {})
    assert status == 200
    status, body, _, _ = request('GET', '/api/tasks/')
    assert status == 401
    checks.append({'case': 'logout_revokes_session', 'status': status})
    # Native technical administration uses a separate genuine form/CSRF login.
    from urllib.parse import urlencode
    cookies.clear()
    status, body, _, _ = request('GET', '/admin/login/')
    assert status == 200 and cookies.get('csrftoken')
    form = urlencode({'username': 'tls-admin', 'password': password, 'next': '/admin/'})
    status, _, _, _ = request('POST', '/admin/login/', form, csrf=False,
        extra={'Content-Type': 'application/x-www-form-urlencoded'})
    assert status == 403
    checks.append({'case': 'admin_csrf_required', 'status': status})
    status, _, _, _ = request('POST', '/admin/login/', form,
        extra={'Content-Type': 'application/x-www-form-urlencoded'})
    assert status == 302
    status, body, _, _ = request('GET', '/admin/')
    assert status == 200
    checks.append({'case': 'genuine_native_admin_login', 'status': status})
    status, _, _, _ = request('GET', '/api/tasks/')
    assert status == 403
    checks.append({'case': 'technical_admin_not_business_role', 'status': status})
    time.sleep(.1)
    return checks
