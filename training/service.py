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
    if session is None:
        return False
    try:
        model = apps.get_model('crm', 'CRMDeal')
    except LookupError:
        return False
    return policy.crm_deals().filter(training_session=session).exclude(next_action='').exists()


def observations(policy, marker, case_id, session):
    refs, obj = sources(policy, marker, case_id)
    order, line = obj['order'], obj['line']
    facts = {'client': order.customer.name, 'order_code': order.code,
             'order_quantity': number(line.quantity), 'due_date': str(order.due_date),
             'currency': order.currency, 'scenario_date': marker['as_of']}
    links = [{'kind': 'order', 'id': order.pk, 'code': order.code,
              'route': {'section': 'erp', 'sub': 'sales'}}]
    rows = []
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
        links.extend([{'kind': 'purchase', 'id': purchase.pk, 'code': purchase.code,
                       'route': {'section': 'erp', 'sub': 'purchase'}},
                      {'kind': 'production', 'id': job.pk, 'code': job.code,
                       'route': {'section': 'erp', 'sub': 'production'}}])
    elif case_id == CASE_IDS[1]:
        approved, blocked = obj['approved_lot'], obj['blocked_lot']
        reserved = sum((r.quantity for r in policy.queryset(Reservation).filter(line=line, lot=approved)), Decimal(0))
        shipments = list(policy.queryset(Movement).filter(line=line, kind='shipment').order_by('pk').values('pk', 'lot_id', 'quantity'))
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
        rows = [
            step('invoice', 'Звірте рахунок і вже отриману оплату', ('erp', 'costs'), 'answer',
                 {'invoice': invoice.code, 'amount': number(invoice.amount), 'paid': number(invoice.paid)},
                 number(balance), instruction='Яка сума залишається відкритою? Не проводьте існуючу оплату повторно.'),
            step('followup', 'Призначте наступну дію', ('hr', 'tasks'), 'operation',
                 {'tasks': tasks, 'balance': number(balance)}, passed=bool(tasks),
                 instruction='Створіть пов’язане із замовленням завдання з відповідальним, строком і зрозумілим очікуваним результатом. Воно не погашає борг.'),
        ]
        links.append({'kind': 'invoice', 'id': invoice.pk, 'code': invoice.code,
                      'route': {'section': 'erp', 'sub': 'costs'}})
    found = crm_exists(session, policy)
    rows.append(step('crm', 'Збережіть наступний контакт у CRM', ('crm', ''), 'crm',
                     {'record_exists': found}, passed=found,
                     instruction='Відкрийте чернетку CRM, перевірте її та підтвердьте створення картки. Експорт файлу не створює запису.'))
    if policy.role == 'observer':
        for row in rows:
            if row['kind'] != 'answer':
                row.update(kind='answer', expected=number(line.quantity), passed=False,
                           instruction='Режим читання: перевірте джерело і вкажіть кількість замовлення. Це навчальна відповідь, а не проведення операції.')
    return facts, links, rows


def session_state(policy, marker, case_id, session=None):
    key = identity(policy, marker, case_id)
    if session is None:
        session = TrainingSession.objects.filter(**key).first()
    facts, links, observed = observations(policy, marker, case_id, session)
    completed = session.progress if session else {}
    steps, unlocked, changed = [], True, False
    for row in observed:
        stamp = digest({'observed': row['observed'], 'answer': row['expected'],
                        'access': policy.access_revision(), 'fixture': marker['hash']})
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
                current_step=session.current_step if session else steps[0]['id'],
                learning_mode='read_only' if policy.role == 'observer' else 'practice',
                facts=facts, sources=links, steps=steps,
                tour_state=session.tour_state if session else {},
                fixture={'id': marker['id'], 'hash': marker['hash'], 'as_of': marker['as_of']})


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
        if session.status == 'paused':
            session.status = 'in_progress'
            session.save(update_fields=['status', 'updated_at'])
        return session_state(policy, marker, case_id, session)
    session = TrainingSession.objects.select_for_update().get(**key)
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
            _, _, raw = observations(policy, marker, case_id, session)
            row = next(x for x in raw if x['id'] == selected['id'])
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
            stamp = digest({'observed': row['observed'], 'answer': row['expected'],
                            'access': policy.access_revision(), 'fixture': marker['hash']})
            session.progress = {**session.progress, selected['id']: {'stamp': stamp}}
        session.current_step = selected['id']
        session.status = 'in_progress'
    else:
        raise ValueError('Невідома навчальна дія.')
    session.save()
    result = session_state(policy, marker, case_id, session)
    if result['status'] != session.status:
        session.status = result['status']
        session.save(update_fields=['status', 'updated_at'])
    return result
