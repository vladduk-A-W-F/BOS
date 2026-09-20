"""One bounded SQLite N2 observation; not gate3, full acceptance, or an E2E suite."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import sys
import time
import traceback
from uuid import uuid4

TASK_DIR = Path(__file__).resolve().parent
SOURCE = TASK_DIR / 'source'
OWNED = TASK_DIR / 'owned'
OWNED.mkdir(exist_ok=True)
DB = OWNED / ('check_' + uuid4().hex + '.sqlite3')
assert not DB.exists()
os.environ.update(DJANGO_SETTINGS_MODULE='verification_settings', BOS_VERIFY_DB='sqlite',
                  BOS_TEST_DB_NAME=str(DB), BOS_TEST_MEDIA=str(OWNED / 'media'),
                  BOS_PROJECT_ROOT=str(SOURCE), BOS_DATA_MODE='demo',
                  PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', ANTHROPIC_API_KEY='')
sys.path.insert(0, str(SOURCE))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    default=str, separators=(',', ':')).encode()).hexdigest()


started = time.perf_counter()
report = {'schema': 'bos.n2.scoped-diagnostic.v1', 'started_at': datetime.now(timezone.utc).isoformat(),
          'complete': False, 'scope': 'One small SQLite fixture, ten fingerprint calls, two users with disjoint pending ERP proposals. No full/gate3/E2E or external API.',
          'source_root': str(SOURCE), 'database': str(DB), 'http': []}
code = 1
try:
    import django
    django.setup()
    from django.core.management import call_command
    from django.conf import settings
    from django.db import connection
    from django.test import Client
    from scripts.verify import source_digest
    from scripts.check_support import login_test_client
    from erp import service
    from erp.models import Item, Location, Lot, Movement, Event
    from operations.models import ActionProposal, Configuration

    source_before = source_digest()
    report['source_sha256'] = source_before
    call_command('migrate', verbosity=0)
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA database_list')
        actual = cursor.fetchall()
        cursor.execute('SELECT sqlite_version()')
        sqlite_version = cursor.fetchone()[0]
    assert connection.vendor == 'sqlite' and Path(next(row[2] for row in actual if row[1] == 'main')) == DB
    report['environment'] = {'python': sys.version, 'django': django.get_version(),
                             'vendor': connection.vendor, 'sqlite_version': sqlite_version,
                             'actual_database': str(DB), 'media': str(settings.MEDIA_ROOT)}
    Configuration.objects.create(key='erp_write', value={'revision': 0})
    Configuration.objects.create(key='dataset', value={'as_of': '2026-09-20'})

    class TracedClient(Client):
        def request(self, **request):
            response = super().request(**request)
            report['http'].append({'actor': self.actor_label, 'method': request.get('REQUEST_METHOD'),
                                   'path': request.get('PATH_INFO'), 'status': response.status_code,
                                   'response_sha256': hashlib.sha256(response.content).hexdigest()})
            return response

    clients = {}
    graphs = {}
    users = {}
    for label in ('A', 'B'):
        client = TracedClient(enforce_csrf_checks=True, raise_request_exception=False)
        client.actor_label = label
        user = login_test_client(client, 'ceo')
        clients[label] = client
        users[label] = {'id': user.pk, 'role': 'ceo',
                        'session_sha256': hashlib.sha256(client.session.session_key.encode()).hexdigest(),
                        'authenticated_user_id': client.session.get('_auth_user_id')}
        item = Item.objects.create(code='N2-ITEM-' + label, name='Synthetic N2 item ' + label,
                                   kind='material', method='buy', unit='шт.', revision='A', currency='EUR')
        location = Location.objects.create(code='N2-LOC-' + label, name='Synthetic N2 location ' + label)
        lot = Lot.objects.create(code='N2-LOT-' + label, item=item, location=location, quantity=Decimal('10'),
                                 quality='approved', revision='A', unit_cost=Decimal('2'), currency='EUR')
        movement = Movement.objects.create(lot=lot, quantity=Decimal('10'), kind='opening',
                                           reference=lot.code, cost=Decimal('20'))
        graphs[label] = {'item_id': item.pk, 'location_id': location.pk, 'lot_id': lot.pk,
                         'opening_movement_id': movement.pk}
    assert users['A']['id'] != users['B']['id']
    assert users['A']['session_sha256'] != users['B']['session_sha256']
    assert all(graphs['A'][key] != graphs['B'][key] for key in graphs['A'])
    report['users'] = users
    report['disjoint_source_references'] = graphs
    report['bootstrap_seconds'] = time.perf_counter() - started

    def graph_state(label):
        ids = graphs[label]
        return {'lot': Lot.objects.filter(pk=ids['lot_id']).values().get(),
                'item': Item.objects.filter(pk=ids['item_id']).values().get(),
                'location': Location.objects.filter(pk=ids['location_id']).values().get(),
                'movements': list(Movement.objects.filter(lot_id=ids['lot_id']).order_by('id').values())}

    def state():
        graph_values = {label: graph_state(label) for label in graphs}
        return {'fingerprint': service.fingerprint(),
                'graph_hashes': {label: digest(value) for label, value in graph_values.items()},
                'lot_quantities': {label: str(value['lot']['quantity']) for label, value in graph_values.items()},
                'movement_count': Movement.objects.count(), 'event_count': Event.objects.count(),
                'mutex_revision': Configuration.objects.get(key='erp_write').value,
                'mutex_revision_sha256': digest(Configuration.objects.get(key='erp_write').value)}

    measurements = []
    for sample in range(10):
        sql_records = []
        def observer(execute, sql, params, many, context):
            before = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                sql_records.append({'seconds': time.perf_counter() - before,
                                    'verb': sql.lstrip().split()[0],
                                    'tables': re.findall(r'FROM\s+"([^"]+)"', sql)})
        before = time.perf_counter()
        with connection.execute_wrapper(observer):
            token = service.fingerprint()
        measurements.append({'sample': sample + 1, 'wall_seconds': time.perf_counter() - before,
                             'sql_seconds': sum(x['seconds'] for x in sql_records),
                             'query_count': len(sql_records), 'fingerprint': token,
                             'queries': sql_records})
    assert len({m['fingerprint'] for m in measurements}) == 1
    durations = sorted(m['wall_seconds'] for m in measurements)
    report['fingerprint_measurements'] = measurements
    report['fingerprint_summary'] = {'calls': 10, 'query_counts': [m['query_count'] for m in measurements],
                                     'min_seconds': min(durations), 'median_seconds': statistics.median(durations),
                                     'max_seconds': max(durations), 'mean_seconds': statistics.mean(durations),
                                     'empirical_p90_seconds': durations[8], 'fixture_rows': {
                                         'items': Item.objects.count(), 'locations': Location.objects.count(),
                                         'lots': Lot.objects.count(), 'movements': Movement.objects.count()}}
    report['before_previews'] = state()

    def post(label, path, payload):
        client = clients[label]
        response = client.post(path, payload, content_type='application/json',
                               HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
        body = response.json()
        report['http'][-1].update(payload=payload, body=body, csrf_enforced=True,
                                  session_sha256=users[label]['session_sha256'])
        print(json.dumps({'HTTP': report['http'][-1]}, ensure_ascii=False, default=str), flush=True)
        return response.status_code, body

    proposals = {}
    for label, delta in [('A', '-1'), ('B', '-2')]:
        status, body = post(label, '/api/erp/preview/', {'action': 'erp_adjust',
                            'lot_id': graphs[label]['lot_id'], 'delta': delta,
                            'reason': 'Synthetic N2 disjoint lot ' + label})
        assert status == 200, (status, body)
        proposals[label] = body['id']
    report['proposals'] = {label: {'id': identity, 'fingerprint': ActionProposal.objects.get(pk=identity).fingerprint,
                                   'user_id': ActionProposal.objects.get(pk=identity).user_id}
                            for label, identity in proposals.items()}
    assert all(report['proposals'][label]['user_id'] == users[label]['id'] for label in users)
    assert report['proposals']['A']['fingerprint'] == report['proposals']['B']['fingerprint']
    report['after_previews'] = state()
    assert report['after_previews'] == report['before_previews']
    status_b, body_b = post('B', '/api/operations/confirm/', {'proposal_id': proposals['B'], 'confirmed': True})
    report['after_b_confirm'] = state()
    status_a, body_a = post('A', '/api/operations/confirm/', {'proposal_id': proposals['A'], 'confirmed': True})
    report['after_a_confirm'] = state()
    before = report['before_previews']; after_b = report['after_b_confirm']; after_a = report['after_a_confirm']
    observations = {'first_b_status': status_b, 'second_a_status': status_a,
                    'a_source_graph_unchanged_by_b': before['graph_hashes']['A'] == after_b['graph_hashes']['A'],
                    'b_source_graph_changed': before['graph_hashes']['B'] != after_b['graph_hashes']['B'],
                    'global_fingerprint_changed': before['fingerprint'] != after_b['fingerprint'],
                    'rejected_a_preserves_business_and_mutex_state': after_a == after_b,
                    'a_receipt_still_empty': ActionProposal.objects.get(pk=proposals['A']).receipt is None,
                    'b_receipt_persisted': ActionProposal.objects.get(pk=proposals['B']).receipt is not None}
    report['observations'] = observations
    assert status_b == 200 and status_a == 409, observations
    assert all(value is True for key, value in observations.items() if key not in ('first_b_status', 'second_a_status'))
    assert after_b['lot_quantities'] == {'A': '10.000', 'B': '8.000'}
    assert after_b['movement_count'] == before['movement_count'] + 1
    assert after_b['event_count'] == before['event_count'] + 1
    report['source_unchanged'] = source_before == source_digest()
    assert report['source_unchanged']
    report['complete'] = True
    code = 0
except BaseException as exc:
    report['failure'] = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
    print(traceback.format_exc(), flush=True)
finally:
    report['elapsed_seconds'] = time.perf_counter() - started
    report['exit_code'] = code
    (TASK_DIR / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    print(json.dumps({'scope': report['scope'], 'complete': report['complete'], 'exit_code': code,
                      'seconds': report['elapsed_seconds'], 'observations': report.get('observations'),
                      'fingerprint_summary': report.get('fingerprint_summary')}, ensure_ascii=False), flush=True)
raise SystemExit(code)
