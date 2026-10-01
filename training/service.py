"""Lesson progress proves a stated answer or current source fact, never a click."""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from boss_project.policy import Policy
from erp.models import SalesOrder, SalesLine, Production, Purchase, Lot, Movement, Reservation
from operations.models import Invoice
from operations.service import Conflict
from .access import require_training
from .models import TrainingSession

CASE_IDS = ('BOS3-CASE-01', 'BOS3-CASE-02', 'BOS3-CASE-03')


def catalog():
    path = Path(settings.BASE_DIR) / 'frontend' / 'bos3_content.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    if value.get('fixture_id') != 'bos3-fasteners-uk-v1':
        raise ValueError('Версія навчального змісту не відповідає набору даних.')
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(',', ':'), default=str).encode()).hexdigest()


def identity(policy, marker, case_id):
    if case_id not in CASE_IDS or case_id not in marker['source_map']:
        raise ValueError('Навчальний кейс не знайдено.')
    return dict(user_id=policy.actor.user_id, role=policy.role,
                installation_id=marker['installation_id'], fixture_id=marker['id'],
                fixture_hash=marker['hash'], case_id=case_id)


def sources(policy, marker, case_id):
    refs = marker['source_map'][case_id]
    order = policy.queryset(SalesOrder).select_related('customer').get(pk=refs['order_id'])
    line = policy.queryset(SalesLine).get(pk=refs['line_id'], order=order)
    objects = dict(order=order, line=line)
    for key, model in [('production', Production), ('purchase', Purchase),
                       ('approved_lot', Lot), ('blocked_lot', Lot)]:
        if key + '_id' in refs:
            objects[key] = policy.queryset(model).get(pk=refs[key + '_id'])
    if 'invoice_id' in refs:
        if not policy.ceo:
            raise PermissionError('Фінансовий кейс доступний керівнику.')
        objects['invoice'] = Invoice.objects.get(pk=refs['invoice_id'], customer=order.customer,
                                                 invoicelink__order=order)
    return refs, objects


def number(value):
    return format(Decimal(str(value)), 'f')


def step(id, title, route, kind, observed, expected=None, passed=False, instruction=''):
    return dict(id=id, title=title, route={'section': route[0], 'sub': route[1]},
                kind=kind, observed=observed, expected=expected, passed=passed,
                instruction=instruction)


def crm_exists(session, policy):
    return bool(_crm_source_ids(session, policy))


def _crm_source_ids(session, policy):
    if session is None:
        return []
    try:
        apps.get_model('crm', 'CRMDeal')
    except LookupError:
        return []
    return list(policy.crm_deals().filter(training_session=session)
                .exclude(next_action='').values_list('pk', flat=True))


def observations(policy, marker, case_id, session):
    refs, obj = sources(policy, marker, case_id)
    order, line = obj['order'], obj['line']
    common_ids = {'order': ['erp.salesorder', order.pk],
                  'line': ['erp.salesline', line.pk],
                  'customer_ref': ['finance.counterparty', order.customer_id]}

    def consistent_rows(rows, pk_key):
        seen = {}
        for row in rows:
            pk = row[pk_key]
            if type(pk) is not int or pk <= 0:
                raise Conflict('Некоректне джерело навчального кроку.')
            snapshot = json.dumps(row, sort_keys=True, ensure_ascii=True,
                                  separators=(',', ':'), default=str)
            if pk in seen and seen[pk] != snapshot:
                raise Conflict('Суперечливе джерело навчального кроку.')
            seen[pk] = snapshot

    facts = {'client': order.customer.name, 'order_code': order.code,
             'order_quantity': number(line.quantity), 'due_date': str(order.due_date),
             'currency': order.currency, 'scenario_date': marker['as_of']}
    links = [{'kind': 'order', 'id': order.pk, 'code': order.code,
              'route': {'section': 'erp', 'sub': 'sales'}}]
    rows, direct_ids = [], {}
    if case_id == CASE_IDS[0]:
        job, purchase = obj['production'], obj['purchase']
        initial = refs['initial']
        # The opening shortage is a declared immutable fixture fact, not today's stock.
        shortage = initial['washer_shortage']
        facts.update(initial)
        facts.update(produced=number(job.produced), received=number(purchase.received),
                     purchase_code=purchase.code, production_code=job.code)
        rows = [
            step('order', 'Перевірте потребу клієнта', ('erp', 'sales'), 'answer',
                 {'order': order.code, 'quantity': number(line.quantity)}, number(line.quantity),
                 instruction='Скільки комплектів замовив клієнт?'),
            step('supply', 'Зіставте початкове забезпечення', ('erp', 'stock'), 'answer',
                 {'fixture': marker['hash'], 'initial': initial}, str(shortage),
                 instruction='Скільки шайб бракувало на початку історії?'),
            step('receipt', 'Прийміть навчальне постачання', ('erp', 'purchase'), 'operation',
                 {'purchase': purchase.code, 'received': number(purchase.received),
                  'quantity': number(purchase.quantity)}, passed=purchase.received >= purchase.quantity,
                 instruction='Відкрийте закупівлю, перевірте preview і підтвердьте приймання. Далі потрібні допуск якості та забезпечення виробництва.'),
            step('production', 'Випустіть монтажні комплекти', ('erp', 'production'), 'operation',
                 {'production': job.code, 'produced': number(job.produced), 'status': job.status},
                 passed=job.status == 'done' and job.produced == job.quantity,
                 instruction='Допустіть партію, забезпечте дільницю, зарезервуйте компоненти, запустіть і завершіть комплектацію через чинні дії ERP.'),
        ]
        direct_ids = {'receipt': {'purchase': ['erp.purchase', purchase.pk]},
                      'production': {'production': ['erp.production', job.pk]}}
        links.extend([{'kind': 'purchase', 'id': purchase.pk, 'code': purchase.code,
                       'route': {'section': 'erp', 'sub': 'purchase'}},
                      {'kind': 'production', 'id': job.pk, 'code': job.code,
                       'route': {'section': 'erp', 'sub': 'production'}}])
    elif case_id == CASE_IDS[1]:
        approved, blocked = obj['approved_lot'], obj['blocked_lot']
        reservations = list(policy.queryset(Reservation).filter(line=line, lot=approved))
        consistent_rows([{'pk': r.pk, 'line_id': r.line_id, 'lot_id': r.lot_id,
                          'quantity': r.quantity} for r in reservations], 'pk')
        reserved = sum((r.quantity for r in reservations), Decimal(0))
        shipments = list(policy.queryset(Movement).filter(line=line, kind='shipment').order_by('pk').values('pk', 'lot_id', 'quantity'))
        consistent_rows(shipments, 'pk')
        shipped = sum((abs(x['quantity']) for x in shipments), Decimal(0))
        only_approved = bool(shipments) and all(x['lot_id'] == approved.pk for x in shipments)
        facts.update(approved_lot=approved.code, approved_quantity=number(approved.quantity),
                     blocked_lot=blocked.code, blocked_quantity=number(blocked.quantity),
                     reserved=number(reserved), shipped=number(line.shipped))
        allocated = blocked.quality == 'blocked' and (reserved >= line.quantity or
                    (only_approved and shipped == line.quantity))
        rows = [
            step('order', 'Перевірте кількість замовлення', ('erp', 'sales'), 'answer',
                 {'order': order.code, 'quantity': number(line.quantity)}, number(line.quantity),
                 instruction='Скільки комплектів потрібно відвантажити?'),
            step('quality', 'Відокремте заблоковану партію', ('erp', 'quality'), 'answer',
                 {'lot': blocked.code, 'quantity': number(blocked.quantity), 'quality': blocked.quality},
                 number(blocked.quantity), instruction='Скільки комплектів залишаються заблокованими?'),
            step('reservation', 'Забезпечте відбір дозволеної партії', ('erp', 'stock'), 'operation',
                 {'approved_lot': approved.pk, 'allocation_verified': allocated, 'blocked': blocked.quality},
                 passed=allocated,
                 instruction='Зарезервуйте для замовлення лише допущену партію. Уже виконану правильну відвантажувальну операцію теж буде враховано.'),
            step('shipment', 'Підтвердьте правильне відвантаження', ('erp', 'sales'), 'operation',
                 {'movements': shipments, 'shipped': number(line.shipped), 'blocked_quantity': number(blocked.quantity)},
                 passed=only_approved and shipped == line.quantity and line.shipped == line.quantity
                        and blocked.quality == 'blocked'
                        and blocked.quantity == Decimal(str(refs['initial']['blocked_quantity'])),
                 instruction='Перевірте джерело партії у preview і підтвердьте відвантаження. Створіть окреме завдання щодо документа заблокованої партії.'),
        ]
        lots = {'approved_lot': ['erp.lot', approved.pk],
                'blocked_lot': ['erp.lot', blocked.pk]}
        shipment_ids = [['erp.movement', row['pk']] for row in shipments]
        direct_ids = {
            'quality': {'blocked_lot': lots['blocked_lot']},
            'reservation': {**lots,
                            'reservations': [['erp.reservation', r.pk] for r in reservations]},
            'shipment': {**lots, 'shipments': shipment_ids},
        }
        links.extend([{'kind': 'lot', 'id': row.pk, 'code': row.code,
                       'route': {'section': 'erp', 'sub': 'quality'}} for row in (approved, blocked)])
    else:
        invoice = obj['invoice']
        balance = invoice.amount - invoice.paid
        facts.update(invoice_code=invoice.code, amount=number(invoice.amount),
                     paid=number(invoice.paid), balance=number(balance), due_date=str(invoice.due_date))
        from tasks.models import Task
        tasks = list(policy.tasks().filter(sales_order=order, archived_at__isnull=True)
                      .exclude(assignee_employee=None).exclude(deadline=None)
                      .values('id', 'assignee_employee_id', 'deadline', 'title'))
        consistent_rows(tasks, 'id')
        rows = [
            step('invoice', 'Звірте рахунок і вже отриману оплату', ('erp', 'costs'), 'answer',
                 {'invoice': invoice.code, 'amount': number(invoice.amount), 'paid': number(invoice.paid)},
                 number(balance), instruction='Яка сума залишається відкритою? Не проводьте існуючу оплату повторно.'),
            step('followup', 'Призначте наступну дію', ('hr', 'tasks'), 'operation',
                 {'tasks': tasks, 'balance': number(balance)}, passed=bool(tasks),
                 instruction='Створіть пов’язане із замовленням завдання з відповідальним, строком і зрозумілим очікуваним результатом. Воно не погашає борг.'),
        ]
        direct_ids = {
            'invoice': {'invoice': ['operations.invoice', invoice.pk]},
            'followup': {'invoice': ['operations.invoice', invoice.pk],
                         'tasks': [['tasks.task', row['id']] for row in tasks],
                         'assignee_refs': [[row['id'], ['employees.employee', row['assignee_employee_id']]]
                                           for row in tasks]},
        }
        links.append({'kind': 'invoice', 'id': invoice.pk, 'code': invoice.code,
                      'route': {'section': 'erp', 'sub': 'costs'}})
    deal_ids = _crm_source_ids(session, policy)
    found = bool(deal_ids)
    rows.append(step('crm', 'Збережіть наступний контакт у CRM', ('crm', ''), 'crm',
                      {'record_exists': found}, passed=found,
                      instruction='Відкрийте чернетку CRM, перевірте її та підтвердьте створення картки. Експорт файлу не створює запису.'))
    direct_ids['crm'] = {'deals': [['crm.crmdeal', pk] for pk in deal_ids]}
    for row in rows:
        row['_source_ids'] = {**common_ids, **direct_ids.get(row['id'], {})}
    if policy.role == 'observer':
        for row in rows:
            if row['kind'] != 'answer':
                row.update(kind='answer', expected=number(line.quantity), passed=False,
                           instruction='Режим читання: перевірте джерело і вкажіть кількість замовлення. Це навчальна відповідь, а не проведення операції.')
    return facts, links, rows


def _expected_stamps(marker, case_id, rows, access_revision):
    if not rows:
        return {}
    step_order = {
        CASE_IDS[0]: ('order', 'supply', 'receipt', 'production', 'crm'),
        CASE_IDS[1]: ('order', 'quality', 'reservation', 'shipment', 'crm'),
        CASE_IDS[2]: ('invoice', 'followup', 'crm'),
    }
    if case_id not in step_order or tuple(row['id'] for row in rows) != step_order[case_id]:
        raise Conflict('Некоректний порядок навчальних кроків.')
    common = {'order': 'erp.salesorder', 'line': 'erp.salesline',
              'customer_ref': 'finance.counterparty'}
    scalar = {**common, 'purchase': 'erp.purchase', 'production': 'erp.production',
              'approved_lot': 'erp.lot', 'blocked_lot': 'erp.lot',
              'invoice': 'operations.invoice'}
    collections = {'reservations': 'erp.reservation', 'shipments': 'erp.movement',
                   'tasks': 'tasks.task', 'deals': 'crm.crmdeal'}
    additions = {
        CASE_IDS[0]: {'receipt': {'purchase'}, 'production': {'production'},
                      'crm': {'deals'}},
        CASE_IDS[1]: {'quality': {'blocked_lot'},
                      'reservation': {'approved_lot', 'blocked_lot', 'reservations'},
                      'shipment': {'approved_lot', 'blocked_lot', 'shipments'},
                      'crm': {'deals'}},
        CASE_IDS[2]: {'invoice': {'invoice'},
                      'followup': {'invoice', 'tasks', 'assignee_refs'},
                      'crm': {'deals'}},
    }

    def positive_pk(value):
        if type(value) is not int or value <= 0:
            raise Conflict('Некоректна ідентичність джерела навчання.')
        return value

    def identity_pair(value, label):
        if not isinstance(value, list) or len(value) != 2 or value[0] != label:
            raise Conflict('Некоректна ідентичність джерела навчання.')
        return [label, positive_pk(value[1])]

    def canonical_collection(values, label):
        if not isinstance(values, list):
            raise Conflict('Некоректна множина джерел навчання.')
        unique = {}
        for value in values:
            pair = identity_pair(value, label)
            unique[pair[1]] = pair
        return [unique[pk] for pk in sorted(unique)]

    def canonical_assignees(values):
        if not isinstance(values, list):
            raise Conflict('Некоректна множина відповідальних.')
        unique = {}
        for value in values:
            if not isinstance(value, list) or len(value) != 2:
                raise Conflict('Некоректна множина відповідальних.')
            task_pk = positive_pk(value[0])
            pair = identity_pair(value[1], 'employees.employee')
            if task_pk in unique and unique[task_pk] != [task_pk, pair]:
                raise Conflict('Суперечлива ідентичність відповідального.')
            unique[task_pk] = [task_pk, pair]
        return [unique[pk] for pk in sorted(unique)]

    def canonical_observed(row):
        observed = row['observed']
        if not isinstance(observed, dict):
            raise Conflict('Некоректне спостереження навчального кроку.')
        result = dict(observed)
        list_key = ('tasks' if case_id == CASE_IDS[2] and row['id'] == 'followup' else
                    'movements' if case_id == CASE_IDS[1] and row['id'] == 'shipment' else None)
        if list_key is not None:
            values = observed[list_key]
            if not isinstance(values, list):
                raise Conflict('Некоректне спостереження навчального кроку.')
            pk_key = 'id' if list_key == 'tasks' else 'pk'
            unique = {}
            for value in values:
                if not isinstance(value, dict):
                    raise Conflict('Некоректне спостереження навчального кроку.')
                pk = positive_pk(value[pk_key])
                snapshot = json.dumps(value, sort_keys=True, ensure_ascii=True,
                                      separators=(',', ':'), default=str)
                if pk in unique and unique[pk][0] != snapshot:
                    raise Conflict('Суперечливе спостереження навчального кроку.')
                unique[pk] = (snapshot, value)
            result[list_key] = [dict(unique[pk][1]) for pk in sorted(unique)]
        return result

    expected, prior = {}, None
    for row in rows:
        source_ids = row.get('_source_ids')
        required = set(common) | additions[case_id].get(row['id'], set())
        if not isinstance(source_ids, dict) or set(source_ids) != required:
            raise Conflict('Неповна ідентичність джерела навчання.')
        identities = {}
        for slot, value in source_ids.items():
            if slot in scalar:
                identities[slot] = identity_pair(value, scalar[slot])
            elif slot in collections:
                identities[slot] = canonical_collection(value, collections[slot])
            elif slot == 'assignee_refs':
                identities[slot] = canonical_assignees(value)
            else:
                raise Conflict('Некоректна ідентичність джерела навчання.')
        observed = canonical_observed(row)
        if row['id'] == 'followup':
            task_pks = [value[1] for value in identities['tasks']]
            assignee_pks = [value[0] for value in identities['assignee_refs']]
            if task_pks != assignee_pks or task_pks != [value['id'] for value in observed['tasks']]:
                raise Conflict('Неузгоджені джерела доручення.')
        if row['id'] == 'shipment':
            movement_pks = [value[1] for value in identities['shipments']]
            if movement_pks != [value['pk'] for value in observed['movements']]:
                raise Conflict('Неузгоджені джерела відвантаження.')
        stamp = digest({'observed': observed, 'answer': row['expected'],
                        'access': access_revision, 'fixture': marker['hash'],
                        '_source_stamp': 'bos.training.source-pk.v1',
                        'case': case_id, 'step': row['id'], 'kind': row['kind'],
                        'passed': row['passed'], 'identities': identities, 'prior': prior})
        expected[row['id']] = stamp
        prior = stamp
    return expected


def normalized_current_step(steps, current_step):
    selected = next((row for row in steps if row['id'] == current_step
                     and row['status'] != 'locked'), None)
    if selected is not None:
        return selected['id']
    available = next((row for row in steps if row['status'] in ('available', 'needs_recheck')), None)
    if available is not None:
        return available['id']
    if steps and all(row['status'] == 'completed' for row in steps):
        return steps[0]['id']
    return None


def _project_observation(policy, marker, case_id, session, observation, expected_stamps):
    facts, links, observed = observation
    completed = session.progress if session else {}
    steps, unlocked, changed = [], True, False
    for row in observed:
        stamp = expected_stamps[row['id']]
        previous = completed.get(row['id'])
        valid = bool(previous and previous.get('stamp') == stamp
                     and (row['kind'] == 'answer' or row['passed']))
        changed = changed or bool(previous and not valid)
        status = 'completed' if valid else ('available' if unlocked else 'locked')
        if previous and not valid:
            status = 'needs_recheck' if unlocked else 'locked'
        steps.append({k: row[k] for k in ('id', 'title', 'route', 'kind', 'instruction')})
        steps[-1].update(status=status, evidence={'passed': valid, 'observed': row['observed']},
                         question=row['instruction'] if row['kind'] == 'answer' else None,
                         answer_fields=[{'key': 'value', 'label': 'Ваша відповідь', 'type': 'number'}]
                         if row['kind'] == 'answer' else [])
        unlocked = unlocked and valid
    status = ('not_started' if session is None else 'completed' if unlocked else
              'needs_recheck' if changed else 'paused' if session.status == 'paused' else 'in_progress')
    return dict(case_id=case_id, available=True, status=status,
                session_id=str(session.public_id) if session else None,
                current_step=normalized_current_step(steps, session.current_step if session else None),
                learning_mode='read_only' if policy.role == 'observer' else 'practice',
                facts=facts, sources=links, steps=steps,
                 tour_state=session.tour_state if session else {},
                 fixture={'id': marker['id'], 'hash': marker['hash'], 'as_of': marker['as_of']})


def session_state(policy, marker, case_id, session=None):
    key = identity(policy, marker, case_id)
    if session is None:
        session = TrainingSession.objects.filter(**key).first()
    observation = observations(policy, marker, case_id, session)
    rows = observation[2]
    stamps = _expected_stamps(marker, case_id, rows,
                              policy.access_revision() if rows else None)
    return _project_observation(policy, marker, case_id, session, observation, stamps)


def case03_handoff_ready(policy, marker, session, expected_order_id, expected_invoice_id):
    if expected_order_id is None or expected_invoice_id is None:
        return False
    case_id = CASE_IDS[2]
    observation = observations(policy, marker, case_id, session)
    rows = observation[2]
    if (sum(row['id'] == 'invoice' for row in rows) != 1 or
            sum(row['id'] == 'followup' for row in rows) != 1):
        return False
    invoice = next(row for row in rows if row['id'] == 'invoice')
    followup = next(row for row in rows if row['id'] == 'followup')
    if (invoice.get('_source_ids', {}).get('order') != ['erp.salesorder', expected_order_id] or
            invoice.get('_source_ids', {}).get('invoice') != ['operations.invoice', expected_invoice_id] or
            followup.get('_source_ids', {}).get('order') != ['erp.salesorder', expected_order_id] or
            followup.get('_source_ids', {}).get('invoice') != ['operations.invoice', expected_invoice_id]):
        return False
    stamps = _expected_stamps(marker, case_id, rows, policy.access_revision())
    projected = _project_observation(policy, marker, case_id, session, observation, stamps)
    steps = projected['steps']
    if (sum(row['id'] == 'invoice' for row in steps) != 1 or
            sum(row['id'] == 'followup' for row in steps) != 1):
        return False
    if (followup['kind'] != 'operation' or followup['passed'] is not True or
            not followup['observed']['tasks']):
        return False
    progress = session.progress or {}
    for step_id in ('invoice', 'followup'):
        row = next(row for row in steps if row['id'] == step_id)
        if (row['status'] != 'completed' or row['evidence']['passed'] is not True or
                progress.get(step_id, {}).get('stamp') != stamps[step_id]):
            return False
    return True


def content(request):
    policy = Policy(request)
    registry = catalog()
    try:
        marker = require_training(policy)
    except PermissionError:
        return {'available': False, 'reason': 'training_not_configured', 'content': registry, 'cases': []}
    cases = []
    for case_id in CASE_IDS:
        if case_id == CASE_IDS[2] and not policy.ceo:
            cases.append({'case_id': case_id, 'available': False, 'reason': 'finance_role', 'status': 'unavailable'})
        else:
            try:
                cases.append(session_state(policy, marker, case_id))
            except (ObjectDoesNotExist, PermissionError):
                cases.append({'case_id': case_id, 'available': False,
                              'reason': 'source_access', 'status': 'unavailable'})
    return {'available': True, 'content': registry, 'cases': cases,
            'fixture': {k: marker[k] for k in ('id', 'hash', 'installation_id', 'as_of')}}


@transaction.atomic
def change(request, case_id, action, data):
    from erp.service import write_lock
    write_lock()
    policy = Policy(request)
    marker = require_training(policy)
    key = identity(policy, marker, case_id)
    sources(policy, marker, case_id)
    if action == 'start':
        if data:
            raise ValueError('Зайві поля навчального запиту.')
        session, _ = TrainingSession.objects.get_or_create(**key)
        update_fields = []
        if session.status == 'paused':
            session.status = 'in_progress'
            update_fields.append('status')
        state = session_state(policy, marker, case_id, session)
        current_step = state['current_step'] or ''
        if session.current_step != current_step:
            session.current_step = current_step
            update_fields.append('current_step')
        if update_fields:
            session.save(update_fields=[*update_fields, 'updated_at'])
        return state
    session = TrainingSession.objects.select_for_update().get(**key)
    if action == 'check':
        observation = observations(policy, marker, case_id, session)
        rows = observation[2]
        stamps = _expected_stamps(marker, case_id, rows,
                                  policy.access_revision() if rows else None)
        state = _project_observation(policy, marker, case_id, session, observation, stamps)
    else:
        state = session_state(policy, marker, case_id, session)
    if action == 'pause':
        if data:
            raise ValueError('Зайві поля навчального запиту.')
        session.status = 'paused' if state['status'] != 'completed' else 'completed'
    elif action == 'tour':
        if set(data) != {'status'} or data['status'] not in ('skipped', 'completed'):
            raise ValueError('Оберіть завершення або пропуск огляду.')
        session.tour_state = {'status': data['status']}
    elif action in ('navigate', 'check'):
        if set(data) - ({'step_id', 'answers'} if action == 'check' else {'step_id'}):
            raise ValueError('Зайві поля навчального запиту.')
        selected = next((x for x in state['steps'] if x['id'] == data.get('step_id')), None)
        if selected is None or selected['status'] == 'locked':
            raise ValueError('Спочатку перевірте попередній крок.')
        if action == 'check':
            row = next(x for x in rows if x['id'] == selected['id'])
            if row['kind'] == 'answer':
                answers = data.get('answers', {})
                if not isinstance(answers, dict) or set(answers) != {'value'}:
                    raise ValueError('Вкажіть вашу відповідь.')
                value = answers['value']
                if isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 30:
                    raise ValueError('Вкажіть число.')
                try:
                    parsed = Decimal(str(value).replace(',', '.'))
                    correct = parsed.is_finite() and parsed == Decimal(row['expected'])
                except InvalidOperation:
                    correct = False
                if not correct:
                    raise ValueError('Відповідь не збігається з фактами. Перевірте джерело ще раз.')
            elif not row['passed']:
                raise Conflict('Очікуваний результат ще не підтверджено у джерелах.')
            session.progress = {**session.progress, selected['id']: {'stamp': stamps[selected['id']]}}
        session.current_step = selected['id']
        session.status = 'in_progress'
    else:
        raise ValueError('Невідома навчальна дія.')
    session.save()
    result = (_project_observation(policy, marker, case_id, session, observation, stamps)
              if action == 'check' else session_state(policy, marker, case_id, session))
    if result['status'] != session.status:
        session.status = result['status']
        session.save(update_fields=['status', 'updated_at'])
    return result
