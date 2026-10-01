"""Read projections and deliberately small, policy-checked CRM receipts."""
import hashlib
import json

from django.core.exceptions import ObjectDoesNotExist

from boss_project.policy import Policy
from training.service import case03_handoff_ready
from .models import CRMDeal


CASE_DEFAULTS = {
    'BOS3-CASE-01': {
        'title': 'Узгодити строк для комплектів М10',
        'next_action': 'Підтвердити строк після надходження 120 шайб M10.',
        'stage': 'supply',
    },
    'BOS3-CASE-02': {
        'title': 'Відвантажити 250 комплектів без заблокованої партії',
        'next_action': 'Підтвердити резерв лише з допущеної партії та відвантаження.',
        'stage': 'fulfillment',
    },
    'BOS3-CASE-03': {
        'title': 'Контроль залишку оплати за рахунком',
        'next_action': 'Узгодити наступний контакт щодо залишку 6 400 грн.',
        'stage': 'collection',
    },
}


def _name(row):
    return None if row is None else row.full_name


def deal_row(row, *, include_activities=False):
    data = {
        'id': row.pk,
        'case_id': row.case_id,
        'title': row.title,
        'stage': row.stage,
        'next_action': row.next_action,
        'counterparty': {'id': row.counterparty_id, 'name': row.counterparty.name},
        'owner': {'id': row.owner_id, 'name': row.owner.full_name},
        'order': None if row.sales_order_id is None else {'id': row.sales_order_id, 'code': row.sales_order.code},
        'invoice': None if row.invoice_id is None else {'id': row.invoice_id, 'code': row.invoice.code},
        'contact': {'name': row.contact_name, 'role': row.contact_role, 'email': row.contact_email},
        'created_at': row.created_at.isoformat(),
        'updated_at': row.updated_at.isoformat(),
    }
    if include_activities:
        data['activities'] = [activity_row(activity) for activity in row.activities.select_related('owner').all()]
    return data


def activity_row(row):
    return {
        'id': row.pk, 'kind': row.kind, 'summary': row.summary, 'status': row.status,
        'due_date': None if row.due_date is None else row.due_date.isoformat(),
        'owner': {'id': row.owner_id, 'name': row.owner.full_name},
        'created_at': row.created_at.isoformat(), 'updated_at': row.updated_at.isoformat(),
    }


def rows(policy):
    return [deal_row(row) for row in policy.crm_deals().select_related('counterparty', 'sales_order', 'invoice', 'owner')]


def detail(policy, deal_id):
    row = policy.crm_deals().select_related('counterparty', 'sales_order', 'invoice', 'owner').get(pk=deal_id)
    return deal_row(row, include_activities=True)


def _training_session(policy, public_id):
    from training.access import require_training
    from training.models import TrainingSession
    marker = require_training(policy)
    session = TrainingSession.objects.get(public_id=public_id)
    if (session.user_id != policy.actor.user_id or session.role != policy.role or
            session.installation_id != marker.get('installation_id') or
            session.fixture_id != marker.get('id') or session.fixture_hash != marker.get('hash')):
        raise PermissionError('Навчальна сесія не належить поточному доступу.')
    if session.status not in ('in_progress', 'paused', 'needs_recheck', 'completed'):
        raise PermissionError('Для CRM-передачі потрібна активна навчальна сесія.')
    return marker, session


def draft(policy, public_id, requested_case=None):
    marker, session = _training_session(policy, public_id)
    case_id = requested_case or session.case_id
    if case_id != session.case_id or case_id not in CASE_DEFAULTS:
        raise PermissionError('Недоступний навчальний кейс.')
    source = marker.get('source_map', {}).get(case_id)
    if not isinstance(source, dict):
        raise PermissionError('Сервер не підтвердив джерела цього кейсу.')
    from .commands import _case_sources, _handoff_hash
    refs = _case_sources(policy, marker, session, case_id)
    if not policy.ceo and refs['owner'].pk != policy.actor.employee_id:
        raise PermissionError('CRM-передача доступна лише призначеному менеджеру.')
    stable_hash = _handoff_hash(marker, session, case_id, refs)
    existing = policy.crm_deals().filter(training_session=session, case_id=case_id,
        stable_handoff_hash=stable_hash).select_related('counterparty', 'sales_order', 'invoice', 'owner').first()
    if existing:
        return {'schema': 'crm.handoff-draft.v1', 'synthetic': True, 'existing': True,
                'deal': deal_row(existing, include_activities=True)}
    if session.status == 'completed':
        raise PermissionError('Завершена навчальна сесія не може створити нову CRM-передачу.')
    if case_id == 'BOS3-CASE-03' and not case03_handoff_ready(
            policy, marker, session, refs['order'].pk,
            refs['invoice'].pk if refs['invoice'] is not None else None):
        raise ValueError('Спочатку перевірте попередній крок.')
    defaults = CASE_DEFAULTS[case_id]
    payload = {
        'action': 'crm_handoff', 'training_session_id': str(session.public_id), 'case_id': case_id,
        'stable_handoff_hash': stable_hash, 'counterparty_id': refs['counterparty'].pk,
        'owner_id': refs['owner'].pk, 'order_id': refs['order'].pk,
        'title': defaults['title'], 'next_action': defaults['next_action'], 'stage': defaults['stage'],
        'contact_name': '', 'contact_role': '', 'contact_email': '',
    }
    if refs['invoice'] is not None:
        payload['invoice_id'] = refs['invoice'].pk
    return {
        'schema': 'crm.handoff-draft.v1', 'synthetic': True, 'existing': False,
        'payload': payload,
        'sources': {
            'counterparty': {'id': refs['counterparty'].pk, 'name': refs['counterparty'].name},
            'order': {'id': refs['order'].pk, 'code': refs['order'].code},
            'invoice': None if refs['invoice'] is None else {'id': refs['invoice'].pk, 'code': refs['invoice'].code},
            'owner': {'id': refs['owner'].pk, 'name': refs['owner'].full_name},
        },
    }


def receipt(policy, value):
    """Stored proposals can outlive permissions; re-check current object scope."""
    allowed = {'schema', 'state', 'action', 'replayed', 'deal_id', 'activity_id', 'audit_id', 'stage'}
    result = {key: value[key] for key in allowed if key in value}
    deal_id = value.get('deal_id')
    if deal_id is not None:
        try:
            deal = policy.crm_deals().get(pk=deal_id)
        except ObjectDoesNotExist:
            raise PermissionError('CRM-квитанція більше недоступна.')
        result['deal_id'] = deal.pk
        result['source_refs'] = {'counterparty_id': deal.counterparty_id, 'order_id': deal.sales_order_id,
                                 'invoice_id': deal.invoice_id, 'case_id': deal.case_id}
    if value.get('activity_id') is not None:
        policy.crm_activities().get(pk=value['activity_id'])
        result['activity_id'] = value['activity_id']
    return result
