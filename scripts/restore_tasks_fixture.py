"""C01 gate 7 candidate: actual HTTPS task history/identity/archive preservation."""
from datetime import date, timedelta
import hashlib
import json


def read(client, url):
    status, body = client.request('GET', url)
    assert status == 200, (url, status, body[:300])
    return json.loads(body)


def command(client, payload, records):
    status, body = client.request('POST', '/api/operations/preview/', payload)
    assert status == 200, (payload['action'], status, body[:400])
    proposal = json.loads(body)
    assert proposal['id'] and proposal['impact']
    confirm = {'proposal_id': proposal['id'], 'confirmed': True}
    status, body = client.request('POST', '/api/operations/confirm/', confirm)
    assert status == 200, (payload['action'], status, body[:400])
    receipt = json.loads(body)
    assert receipt['state'] == 'succeeded' and receipt['task_id'] and receipt['audit_id']
    status, body = client.request('POST', '/api/operations/confirm/', confirm)
    assert status == 200 and json.loads(body) == receipt
    records.append({'proposal_id': proposal['id'], 'action': payload['action'], 'receipt': receipt})
    return receipt


def state(client, ids):
    return {str(task_id): {
        'detail': read(client, f'/api/tasks/{task_id}/'),
        'history': read(client, f'/api/tasks/{task_id}/history/?limit=50'),
    } for task_id in ids}


def populate(client, import_receipt, seed):
    as_of = read(client, '/api/erp/snapshot/')['as_of']
    due = str(date.fromisoformat(as_of) + timedelta(days=7))
    past = str(date.fromisoformat(as_of) - timedelta(days=1))
    order = next(row['target_id'] for row in import_receipt['mappings']
                 if row['entity'] == 'sales_order' and row['external_id'] == 'sale-eur')
    records = []
    legacy = seed['legacy_task_ids']
    for task_id in legacy:
        before = read(client, f'/api/tasks/{task_id}/')
        assert before['assignee_id'] is None and before['order_id'] is None
        assert before['result'] is None and before['archived_at'] is None
    created = command(client, {'action': 'create_task', 'title': 'Звірити відновлене замовлення',
        'assignee_id': seed['employee_id'], 'deadline': due, 'order_id': order,
        'category': 'Відновлення', 'priority': 'high'}, records)
    task_id = created['task_id']
    command(client, {'action': 'update_task', 'task_id': task_id,
        'assignee_id': seed['second_employee_id'], 'deadline': past,
        'reason': 'Явно перепризначено контроль джерела і строк'}, records)
    changed = read(client, f'/api/tasks/{task_id}/')
    assert changed['assignee'] == '' and changed['assignee_id'] == seed['second_employee_id']
    assert changed['order_id'] == order and changed['is_overdue'] is True
    result_text = 'Звірено джерело замовлення.\nКількості й документи збережені.'
    command(client, {'action': 'update_task', 'task_id': task_id, 'status': 'done',
        'result': result_text, 'reason': 'Результат зафіксовано відповідальним'}, records)
    completed = read(client, f'/api/tasks/{task_id}/')
    assert completed['status'] == 'done' and completed['result'] == result_text
    assert completed['result_recorded'] is True and completed['priority'] is None
    assert completed['is_overdue'] is False
    command(client, {'action': 'update_task', 'task_id': task_id, 'archived': True,
        'reason': 'Завершений контроль перенесено до архіву'}, records)
    archived = read(client, f'/api/tasks/{task_id}/')
    assert archived['archived'] is True and archived['archived_at']
    for key in ('status','result','assignee','assignee_id','order_id','deadline','priority'):
        assert archived[key] == completed[key], key
    second = command(client, {'action': 'create_task', 'title': 'Повторний контроль після відновлення',
        'assignee_id': seed['employee_id'], 'deadline': due, 'order_id': order}, records)
    command(client, {'action': 'update_task', 'task_id': second['task_id'],
        'deadline': past, 'reason': 'Записано фактичний строк контрольного доручення'}, records)
    ids = [*legacy, task_id, second['task_id']]
    saved = state(client, ids)
    assert saved[str(second['task_id'])]['detail']['is_overdue'] is True
    for task_id in legacy:
        assert saved[str(task_id)]['detail']['result'] is None
        assert saved[str(task_id)]['detail']['assignee_id'] is None
    assert len(saved[str(created['task_id'])]['history']['items']) == 4
    assert len(saved[str(second['task_id'])]['history']['items']) == 2
    assert all(row['history']['next_cursor'] is None for row in saved.values())
    active = read(client, '/api/tasks/')
    archive = read(client, '/api/tasks/?archived=true')
    assert isinstance(active, list) and isinstance(archive, list)
    assert created['task_id'] not in {row['id'] for row in active}
    assert {row['id'] for row in archive} == {created['task_id']}
    return {'ids': ids, 'records': records, 'state': saved, 'active': active, 'archive': archive,
        'state_sha256': hashlib.sha256(json.dumps(saved, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}


def verify_restored(client, expected):
    assert state(client, expected['ids']) == expected['state']
    assert read(client, '/api/tasks/') == expected['active']
    assert read(client, '/api/tasks/?archived=true') == expected['archive']
    for record in expected['records']:
        status = read(client, '/api/operations/task-proposals/' + record['proposal_id'] + '/')
        assert status['state'] == 'succeeded' and status['receipt'] == record['receipt']
        assert status['proposal_id'] == record['proposal_id'] and status['action'] == record['action']
        assert status['same_session'] is False
        code, body = client.request('POST', '/api/operations/confirm/',
            {'proposal_id': record['proposal_id'], 'confirmed': True})
        assert code == 403, (code, body[:200])
    assert state(client, expected['ids']) == expected['state']
    return {'tasks': len(expected['ids']), 'task_proposals': len(expected['records']),
        'state_sha256': expected['state_sha256'], 'history_preserved': True,
        'new_session_read_receipts': True, 'old_session_execution_refused': True,
        'new_business_effects': 0}
