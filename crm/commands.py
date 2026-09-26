"""CRM commands use the same proposal/confirm boundary as ERP and tasks.

The CRM is intentionally narrow: it links an already verified training case to
existing records; it does not manufacture customers, orders, invoices or money.
"""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import re
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from boss_project.data_rules import portable_tree, text_value
from boss_project.identity import actor
from boss_project.policy import Policy
from employees.models import Employee
from erp.models import InvoiceLink, SalesOrder
from operations.models import ActionProposal, AuditEvent, Invoice
from finance.models import Counterparty
from tasks.commands import ConfirmConflict

from .models import CRMActivity, CRMDeal


ACTIONS = {'crm_handoff', 'crm_deal_update', 'crm_activity_update'}
CASE_IDS = {'BOS3-CASE-01', 'BOS3-CASE-02', 'BOS3-CASE-03'}
STAGE_NEXT = {
    'qualification': {'supply'},
    'supply': {'fulfillment'},
    'fulfillment': {'collection'},
    'collection': {'won', 'lost'},
    'won': set(),
    'lost': set(),
}
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.invalid$')


def _positive(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError('Потрібен фактичний позитивний ID: ' + name)
    return value


def _text(data, key, *, minimum=0, maximum=500, required=False):
    if key not in data:
        if required:
            raise ValueError('Потрібне поле: ' + key)
        return
    value = data[key]
    if not isinstance(value, str):
        raise ValueError('Текстове поле має бути рядком: ' + key)
    value = value.strip()
    if not minimum <= len(value) <= maximum:
        raise ValueError(f'Поле {key}: {minimum}–{maximum} символів.')
    data[key] = value


def _uuid(value, name):
    if not isinstance(value, str):
        raise ValueError('Потрібен UUID навчальної сесії.')
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError('Некоректний UUID: ' + name) from exc


def _date(value, name):
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError('Потрібна дата YYYY-MM-DD: ' + name)
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as exc:
        raise ValueError('Потрібна дата YYYY-MM-DD: ' + name) from exc


def clean(payload):
    if not isinstance(payload, dict) or payload.get('action') not in ACTIONS:
        raise ValueError('Невідома CRM-дія.')
    portable_tree(payload)
    data = deepcopy(payload)
    action = data['action']
    if action == 'crm_handoff':
        required = {'action', 'training_session_id', 'case_id', 'stable_handoff_hash', 'counterparty_id',
                    'owner_id', 'title', 'next_action', 'stage'}
        allowed = required | {'order_id', 'invoice_id', 'contact_name', 'contact_role', 'contact_email'}
        if set(data) - allowed or not required <= set(data):
            raise ValueError('Перевірте поля CRM-передачі.')
        data['training_session_id'] = _uuid(data['training_session_id'], 'training_session_id')
        if data['case_id'] not in CASE_IDS:
            raise ValueError('Невідомий навчальний кейс.')
        if not isinstance(data['stable_handoff_hash'], str) or not re.fullmatch(r'[0-9a-f]{64}', data['stable_handoff_hash']):
            raise ValueError('Некоректний стабільний ключ передачі.')
        for key in ('counterparty_id', 'owner_id'):
            _positive(data[key], key)
        for key in ('order_id', 'invoice_id'):
            if key in data:
                _positive(data[key], key)
        _text(data, 'title', minimum=3, maximum=200, required=True)
        _text(data, 'next_action', minimum=3, maximum=500, required=True)
        if data['stage'] not in STAGE_NEXT:
            raise ValueError('Некоректний етап CRM.')
        for key, maximum in (('contact_name', 120), ('contact_role', 120)):
            _text(data, key, maximum=maximum)
        if 'contact_email' in data:
            _text(data, 'contact_email', maximum=254)
            if data['contact_email'] and not EMAIL_RE.fullmatch(data['contact_email']):
                raise ValueError('Навчальний email має завершуватися на .invalid.')
        return data
    if action == 'crm_deal_update':
        required = {'action', 'deal_id', 'reason'}
        mutable = {'owner_id', 'title', 'next_action', 'stage', 'contact_name', 'contact_role', 'contact_email'}
        if set(data) - (required | mutable) or not required <= set(data) or not set(data).intersection(mutable):
            raise ValueError('Потрібна причина та щонайменше одна зміна CRM-угоди.')
        _positive(data['deal_id'], 'deal_id')
        _text(data, 'reason', minimum=3, maximum=1000, required=True)
        if 'owner_id' in data:
            _positive(data['owner_id'], 'owner_id')
        _text(data, 'title', minimum=3, maximum=200)
        _text(data, 'next_action', minimum=3, maximum=500)
        for key, maximum in (('contact_name', 120), ('contact_role', 120)):
            _text(data, key, maximum=maximum)
        if 'contact_email' in data:
            _text(data, 'contact_email', maximum=254)
            if data['contact_email'] and not EMAIL_RE.fullmatch(data['contact_email']):
                raise ValueError('Навчальний email має завершуватися на .invalid.')
        if 'stage' in data and data['stage'] not in STAGE_NEXT:
            raise ValueError('Некоректний етап CRM.')
        return data
    # Activity creates and updates share one command, with an explicit reason on update.
    creating = 'activity_id' not in data
    required = {'action', 'deal_id', 'owner_id', 'kind', 'summary', 'status'} if creating else {'action', 'activity_id', 'reason'}
    mutable = {'deal_id', 'owner_id', 'kind', 'summary', 'due_date', 'status'}
    if set(data) - (required | mutable) or not required <= set(data):
        raise ValueError('Перевірте поля CRM-активності.')
    if not creating and not set(data).intersection(mutable):
        raise ValueError('Потрібна щонайменше одна зміна CRM-активності.')
    if 'activity_id' in data:
        _positive(data['activity_id'], 'activity_id')
    for key in ('deal_id', 'owner_id'):
        if key in data:
            _positive(data[key], key)
    if 'kind' in data and data['kind'] not in dict(CRMActivity.KINDS):
        raise ValueError('Некоректний тип CRM-активності.')
    _text(data, 'summary', minimum=3, maximum=1000)
    if 'status' in data and data['status'] not in dict(CRMActivity.STATUSES):
        raise ValueError('Некоректний статус CRM-активності.')
    if 'due_date' in data:
        _date(data['due_date'], 'due_date')
    if not creating:
        _text(data, 'reason', minimum=3, maximum=1000, required=True)
    return data


def _marker(policy):
    from training.access import require_training
    marker = require_training(policy)
    required = {'id', 'hash', 'synthetic', 'installation_id', 'source_map', 'owner_user_id'}
    if not isinstance(marker, dict) or not required <= set(marker) or marker.get('synthetic') is not True:
        raise PermissionError('Навчальний fixture не підтверджено сервером.')
    return marker


def _session(policy, public_id, marker, *, lock=False, allow_completed=False):
    from training.models import TrainingSession
    rows = TrainingSession.objects
    if lock:
        rows = rows.select_for_update()
    session = rows.get(public_id=public_id)
    if (session.user_id != policy.actor.user_id or session.role != policy.role or
            session.installation_id != marker['installation_id'] or session.fixture_id != marker['id'] or
            session.fixture_hash != marker['hash']):
        raise PermissionError('Навчальна сесія не належить поточному доступу.')
    allowed = {'in_progress', 'paused', 'needs_recheck'}
    if allow_completed:
        allowed.add('completed')
    if session.status not in allowed:
        raise PermissionError('Для CRM-передачі потрібна активна навчальна сесія.')
    return session


def _case_sources(policy, marker, session, case_id, *, lock=False):
    if session.case_id != case_id:
        raise PermissionError('Кейс не відповідає навчальній сесії.')
    source = marker['source_map'].get(case_id)
    if not isinstance(source, dict):
        raise PermissionError('Сервер не підтвердив джерела цього кейсу.')
    for name in ('customer_id', 'owner_id', 'order_id'):
        if type(source.get(name)) is not int or source[name] <= 0:
            raise PermissionError('Неповна карта джерел навчального кейсу.')
    order_rows = SalesOrder.objects
    customer_rows = Counterparty.objects
    employee_rows = Employee.objects
    invoice_rows = Invoice.objects
    if lock:
        order_rows = order_rows.select_for_update()
        customer_rows = customer_rows.select_for_update()
        employee_rows = employee_rows.select_for_update()
        invoice_rows = invoice_rows.select_for_update()
    customer = customer_rows.get(pk=source['customer_id'], is_active=True)
    owner = employee_rows.get(pk=source['owner_id'], archived_at__isnull=True)
    order = order_rows.get(pk=source['order_id'], customer_id=customer.pk)
    policy.queryset(SalesOrder).get(pk=order.pk)
    invoice = None
    if source.get('invoice_id') is not None:
        invoice = invoice_rows.get(pk=source['invoice_id'], customer_id=customer.pk)
        if not InvoiceLink.objects.filter(invoice_id=invoice.pk, order_id=order.pk).exists():
            raise PermissionError('Рахунок не пов’язаний з доступним замовленням.')
        policy.check_reference('invoice_id', invoice.pk)
    return {'counterparty': customer, 'owner': owner, 'order': order, 'invoice': invoice}


def _handoff_hash(marker, session, case_id, refs):
    data = {'fixture': marker['id'], 'fixture_hash': marker['hash'], 'installation': marker['installation_id'],
            'session': str(session.public_id), 'case': case_id,
            'counterparty_id': refs['counterparty'].pk, 'owner_id': refs['owner'].pk,
            'order_id': refs['order'].pk, 'invoice_id': refs['invoice'].pk if refs['invoice'] else None}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _deal(policy, deal_id, *, lock=False):
    rows = policy.crm_deals().select_related('training_session', 'counterparty', 'sales_order', 'invoice', 'owner')
    if lock:
        rows = rows.select_for_update()
    return rows.get(pk=deal_id)


def _activity(policy, activity_id, *, lock=False):
    rows = policy.crm_activities().select_related('deal', 'owner')
    if lock:
        rows = rows.select_for_update()
    return rows.get(pk=activity_id)


def _state_deal(row):
    return {
        'deal_id': row.pk, 'case_id': row.case_id, 'counterparty_id': row.counterparty_id,
        'order_id': row.sales_order_id, 'invoice_id': row.invoice_id, 'owner_id': row.owner_id,
        'title': row.title, 'next_action': row.next_action, 'stage': row.stage,
        'contact_name': row.contact_name, 'contact_role': row.contact_role,
        'contact_email': row.contact_email,
    }


def _state_activity(row):
    return {'activity_id': row.pk, 'deal_id': row.deal_id, 'owner_id': row.owner_id,
            'kind': row.kind, 'summary': row.summary,
            'due_date': None if row.due_date is None else row.due_date.isoformat(), 'status': row.status}


def _changes(before, after, kind, labels):
    return [{'kind': kind, 'id': before.get('deal_id') or before.get('activity_id'), 'field': key,
             'label': labels.get(key, key), 'before': before.get(key), 'after': after.get(key)}
            for key in after if key in before and before[key] != after[key]]


def prepare(request, payload):
    data = clean(payload)
    policy = Policy(request)
    marker = _marker(policy)
    if policy.role == 'observer':
        raise PermissionError('Спостерігач не може змінювати CRM-записи.')
    if data['action'] == 'crm_handoff':
        session = _session(policy, data['training_session_id'], marker, lock=True, allow_completed=True)
        refs = _case_sources(policy, marker, session, data['case_id'], lock=True)
        if not policy.ceo and refs['owner'].pk != policy.actor.employee_id:
            raise PermissionError('Менеджер може створити CRM-передачу лише для призначеного джерела.')
        expected_hash = _handoff_hash(marker, session, data['case_id'], refs)
        if data['stable_handoff_hash'] != expected_hash:
            raise PermissionError('CRM-передача не відповідає поточному навчальному кейсу.')
        expected_ids = {'counterparty_id': refs['counterparty'].pk, 'owner_id': refs['owner'].pk,
                        'order_id': refs['order'].pk}
        if refs['invoice'] is not None:
            expected_ids['invoice_id'] = refs['invoice'].pk
        for key, value in expected_ids.items():
            if data.get(key) != value:
                raise PermissionError('CRM-передача містить недоступне джерело: ' + key)
        if refs['invoice'] is None and 'invoice_id' in data:
            raise PermissionError('Цей кейс не містить рахунку для CRM-передачі.')
        existing = CRMDeal.objects.select_for_update().filter(training_session=session, case_id=data['case_id'],
            stable_handoff_hash=expected_hash).select_related('counterparty', 'sales_order', 'invoice', 'owner').first()
        if existing:
            return {'existing': existing, 'changed': False, 'operation': 'existing_handoff'}
        if session.status == 'completed':
            raise PermissionError('Завершена навчальна сесія може лише повернути наявну CRM-передачу.')
        row = CRMDeal(training_session=session, case_id=data['case_id'], stable_handoff_hash=expected_hash,
            counterparty=refs['counterparty'], owner=refs['owner'], sales_order=refs['order'], invoice=refs['invoice'],
            title=data['title'], next_action=data['next_action'], stage=data['stage'],
            contact_name=data.get('contact_name', ''), contact_role=data.get('contact_role', ''),
            contact_email=data.get('contact_email', ''))
        return {'object': row, 'before': None, 'after': _state_deal(row), 'changed': True,
                'operation': 'create_handoff', 'source_refs': expected_ids}
    if data['action'] == 'crm_deal_update':
        row = _deal(policy, data['deal_id'], lock=True)
        if not policy.can_manage_crm_deal(row):
            raise PermissionError('Змінювати можна лише власну або призначену CRM-угоду.')
        before = _state_deal(row)
        copy = deepcopy(row)
        for key in ('owner_id', 'title', 'next_action', 'contact_name', 'contact_role', 'contact_email'):
            if key in data:
                if key == 'owner_id':
                    Employee.objects.select_for_update().get(pk=data[key], archived_at__isnull=True)
                    copy.owner_id = data[key]
                else:
                    setattr(copy, key, data[key])
        if 'stage' in data:
            if data['stage'] != row.stage and data['stage'] not in STAGE_NEXT[row.stage]:
                raise ValueError('Етап можна змінити лише за визначеним маршрутом CRM.')
            copy.stage = data['stage']
        after = _state_deal(copy)
        return {'object': copy, 'before': before, 'after': after, 'changed': before != after,
                'operation': 'update_deal', 'source_refs': _deal_refs(row)}
    if 'activity_id' in data:
        row = _activity(policy, data['activity_id'], lock=True)
        if not policy.can_manage_crm_deal(row.deal):
            raise PermissionError('Змінювати можна лише активність доступної CRM-угоди.')
        before = _state_activity(row)
        copy = deepcopy(row)
        for key in ('deal_id', 'owner_id', 'kind', 'summary', 'status'):
            if key in data:
                if key == 'deal_id':
                    target = _deal(policy, data[key], lock=True)
                    if not policy.can_manage_crm_deal(target):
                        raise PermissionError('Нова CRM-угода недоступна.')
                if key == 'owner_id':
                    Employee.objects.select_for_update().get(pk=data[key], archived_at__isnull=True)
                setattr(copy, key, data[key])
        if 'due_date' in data:
            copy.due_date = date.fromisoformat(data['due_date']) if data['due_date'] else None
        after = _state_activity(copy)
        return {'object': copy, 'before': before, 'after': after, 'changed': before != after,
                'operation': 'update_activity', 'source_refs': _deal_refs(row.deal)}
    deal = _deal(policy, data['deal_id'], lock=True)
    if not policy.can_manage_crm_deal(deal):
        raise PermissionError('Створювати активності можна лише для доступної CRM-угоди.')
    Employee.objects.select_for_update().get(pk=data['owner_id'], archived_at__isnull=True)
    row = CRMActivity(deal=deal, owner_id=data['owner_id'], kind=data['kind'], summary=data['summary'],
                      due_date=date.fromisoformat(data['due_date']) if data.get('due_date') else None,
                      status=data['status'])
    return {'object': row, 'before': None, 'after': _state_activity(row), 'changed': True,
            'operation': 'create_activity', 'source_refs': _deal_refs(deal)}


def _deal_refs(deal):
    return {'counterparty_id': deal.counterparty_id, 'order_id': deal.sales_order_id,
            'invoice_id': deal.invoice_id, 'owner_id': deal.owner_id, 'case_id': deal.case_id}


def fingerprint(payload):
    data = clean(payload)
    # The request identity is intentionally not accepted from client payload.
    state = {'payload': data,
             'deals': list(CRMDeal.objects.order_by('pk').values()),
             'activities': list(CRMActivity.objects.order_by('pk').values()),
             'employees': list(Employee.objects.order_by('pk').values('id', 'archived_at', 'full_name')),
             'orders': list(SalesOrder.objects.order_by('pk').values()),
             'invoices': list(Invoice.objects.order_by('pk').values()),
             'invoice_links': list(InvoiceLink.objects.order_by('pk').values()),
             'counterparties': list(Counterparty.objects.order_by('pk').values('id', 'is_active', 'type', 'name'))}
    return hashlib.sha256(json.dumps(state, cls=DjangoJSONEncoder, ensure_ascii=False,
                                    sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def preview(request, payload):
    from erp.service import write_lock
    data = clean(payload)
    with transaction.atomic():
        write_lock()
        plan = prepare(request, data)
        stamp = fingerprint(data)
        transaction.set_rollback(True)
    if not plan['changed']:
        existing = plan.get('existing')
        if existing is None:
            row = plan['object']
            identifier = {'deal_id': row.pk} if isinstance(row, CRMDeal) else {'activity_id': row.pk, 'deal_id': row.deal_id}
            return {'state': 'no_change', 'id': None, 'payload': data, 'expires_at': None,
                    'effect': {'entity': 'crm_deal' if isinstance(row, CRMDeal) else 'crm_activity',
                               **identifier, 'note': 'Зміни CRM не потрібні.'}, 'impact': []}
        return {'state': 'existing', 'id': None, 'payload': data, 'expires_at': None,
                'effect': {'entity': 'crm_deal', 'deal_id': existing.pk,
                           'note': 'CRM-передачу вже створено для цього навчального кейсу.'}, 'impact': []}
    principal = actor(request)
    if not request.session.session_key:
        request.session.create()
    proposal = ActionProposal.objects.create(user_id=principal.user_id, session_key=request.session.session_key,
        role=principal.role, payload=data, fingerprint=stamp,
        expires_at=timezone.now() + timedelta(minutes=10))
    return {'id': str(proposal.pk), 'payload': data, 'expires_at': proposal.expires_at.isoformat(),
            'effect': {'entity': 'crm_deal' if data['action'] != 'crm_activity_update' else 'crm_activity',
                       'operation': plan['operation']},
            'impact': _changes(plan['before'] or {}, plan['after'],
                               'crm_deals' if data['action'] != 'crm_activity_update' else 'crm_activities',
                               {'stage': 'Етап', 'next_action': 'Наступна дія', 'owner_id': 'Відповідальний',
                                'summary': 'Зміст', 'status': 'Статус', 'due_date': 'Строк'})}


def apply(request, proposal):
    from erp.service import write_lock
    write_lock()
    proposal.refresh_from_db()
    data = clean(proposal.payload)
    policy = Policy(request)
    if proposal.receipt:
        return proposal.receipt
    plan = prepare(request, data)
    if not plan['changed']:
        existing = plan.get('existing')
        if existing is not None:
            receipt = {'schema': 'crm.deal-receipt.v1', 'state': 'succeeded', 'action': data['action'],
                       'replayed': True, 'deal_id': existing.pk, 'source_refs': _deal_refs(existing)}
        else:
            row = plan['object']
            result_id = {'deal_id': row.pk} if isinstance(row, CRMDeal) else {'activity_id': row.pk, 'deal_id': row.deal_id}
            receipt = {'schema': 'crm.deal-receipt.v1', 'state': 'succeeded', 'action': data['action'],
                       'no_change': True, 'source_refs': plan['source_refs'], **result_id}
        proposal.receipt = receipt
        proposal.save(update_fields=['receipt'])
        return receipt
    if proposal.expires_at < timezone.now():
        raise ConfirmConflict('proposal_expired', 'Строк погодження минув. Підготуйте новий перегляд.')
    if proposal.fingerprint != fingerprint(data):
        raise ConfirmConflict('proposal_stale', 'Дані CRM змінилися. Підготуйте новий перегляд.')
    if not ActionProposal.objects.filter(pk=proposal.pk, receipt__isnull=True).update(receipt={'state': 'running'}):
        raise ConfirmConflict('write_conflict', 'CRM-дія вже виконується. Оновіть перегляд.')
    row = plan['object']
    row.save()
    if isinstance(row, CRMDeal):
        result_id = {'deal_id': row.pk}
        entity = 'crm_deal'
    else:
        result_id = {'activity_id': row.pk, 'deal_id': row.deal_id}
        entity = 'crm_activity'
    audit = AuditEvent.objects.create(action=data['action'], payload={
        'schema': 'crm.audit.v1', 'entity': entity, 'action': data['action'],
        'actor_id': policy.actor.user_id, 'actor_role': policy.role, 'reason': data.get('reason', 'Створено погоджену CRM-дію.'),
        'before': plan['before'], 'after': plan['after'], 'source_refs': plan['source_refs'], **result_id,
    })
    receipt = {'schema': 'crm.deal-receipt.v1', 'state': 'succeeded', 'action': data['action'],
               'audit_id': str(audit.pk), 'source_refs': plan['source_refs'], **result_id}
    if isinstance(row, CRMDeal):
        receipt['stage'] = row.stage
    proposal.receipt = receipt
    proposal.save(update_fields=['receipt'])
    return receipt
