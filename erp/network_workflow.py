"""Read-only, permission-scoped documents and procurement movement projection.

This is an observation of persisted records, never a simulated productivity claim.
Every join starts from Policy-visible rows. Hidden relations do not contribute to
labels, counts, timing samples, document groups, or financial information.
"""
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from statistics import median

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from operations.service import as_of
from .models import Item, Location, Lot, Movement, Purchase


STAGES = {
    'review': 'Перевірка вимоги', 'sourcing': 'Пошук пропозицій',
    'quoted': 'Порівняння пропозицій', 'ordered': 'Замовлено',
    'receiving': 'Частково отримано', 'received': 'Потребу отримано',
}
TYPE_LABELS = {'requirement': 'Вимога', 'supplier_quote': 'Пропозиція постачальника',
               'technical': 'Технічна документація', 'lot_record': 'Документ партії',
               'contract': 'Документ договору', 'other': 'Інший документ'}


def _iso(value):
    return value.isoformat() if value is not None else None


def _hours(start, end):
    if start is None or end is None or end < start:
        return None
    return round((end - start).total_seconds() / 3600, 4)


def _median(values):
    return round(median(values), 4) if values else None


def _filter_id(value, label):
    if value in (None, '', 'all'):
        return None
    if value == 'unassigned':
        return value
    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
        raise ValueError(label + ': потрібен додатний ID.')
    return int(value)


def _filters(params):
    branch = _filter_id(params.get('branch_id'), 'Філія')
    point = _filter_id(params.get('location_id'), 'Точка')
    currency = params.get('currency') or None
    if currency == 'all':
        currency = None
    if currency not in (None, 'UAH', 'EUR', 'USD'):
        raise ValueError('Невідома валюта.')
    return branch, point, currency


def _comparison(samples, now):
    """Two equal, adjacent 28-day completion cohorts; report association only."""
    split, start = now - timedelta(days=28), now - timedelta(days=56)
    before = [h for at, h in samples if start <= at < split]
    after = [h for at, h in samples if split <= at <= now]
    baseline, recent = _median(before), _median(after)
    ready = len(before) >= 3 and len(after) >= 3 and baseline is not None and baseline > 0
    return {
        'available': ready, 'window_days': 28, 'minimum_samples_per_window': 3,
        'metric': 'request_to_receipt_hours',
        'baseline': {'start': _iso(start), 'end': _iso(split), 'sample_size': len(before), 'median_hours': baseline},
        'recent': {'start': _iso(split), 'end': _iso(now), 'sample_size': len(after), 'median_hours': recent},
        'change_percent': round((baseline - recent) / baseline * 100, 2) if ready else None,
        'reason': ('Спостережувана зміна тривалості; не доказ впливу автоматизації.' if ready
                   else 'Потрібно щонайменше 3 завершені вимоги з достовірним часом у кожному 28-денному вікні та додатна базова тривалість.'),
    }


def build(policy, params=None):
    """Return documents/workflow for the same branch, location, currency scope.

    A request without a destination is not assigned to its owner's branch.
    Requests may occur in several point views if their visible purchases do.
    Timings under geographic filtering describe only the selected visible path.
    """
    params = params or {}
    branch, point, currency = _filters(params)
    now, today = timezone.now(), as_of()
    geographic = branch is not None or point is not None
    locations = policy.queryset(Location)
    if branch == 'unassigned':
        locations = locations.filter(branch__isnull=True)
    elif branch is not None:
        locations = locations.filter(branch_id=branch)
    if point == 'unassigned':
        locations = locations.none()
    elif point is not None:
        locations = locations.filter(pk=point)
    location_ids = set(locations.values_list('pk', flat=True))

    purchases_qs = policy.queryset(Purchase)
    lots_qs = policy.queryset(Lot).select_related('item')
    if currency:
        purchases_qs = purchases_qs.filter(currency=currency)
        lots_qs = lots_qs.filter(currency=currency)
    if geographic:
        destination = Q(destination_id__in=location_ids)
        if point == 'unassigned' or (branch == 'unassigned' and point is None):
            destination |= Q(destination__isnull=True)
        purchases_qs = purchases_qs.filter(destination)
        lots_qs = lots_qs.filter(location_id__in=location_ids)
    purchases = list(purchases_qs.order_by('pk'))
    lots = list(lots_qs.order_by('pk'))

    requests_qs = policy.requests().select_related('owner', 'document')
    if currency:
        requests_qs = requests_qs.filter(currency=currency)
    if geographic:
        request_ids = {p.request_id for p in purchases if p.request_id}
        # Only CEO can establish that no purchase exists at all. An ordinary
        # user must not learn the existence or absence of a hidden purchase.
        if policy.ceo and (point == 'unassigned' or (branch == 'unassigned' and point is None)):
            request_ids.update(requests_qs.exclude(pk__in=Purchase.objects.exclude(request=None).values('request_id')).values_list('pk', flat=True))
        requests_qs = requests_qs.filter(pk__in=request_ids)
    requests = list(requests_qs.order_by('required_by', 'pk'))
    request_ids = {r.pk for r in requests}
    quotes = list(policy.quotes().filter(request_id__in=request_ids).order_by('pk'))
    purchase_ids = {p.pk for p in purchases}
    receipts = list(policy.queryset(Movement).filter(purchase_id__in=purchase_ids, kind='receipt', quantity__gt=0).order_by('created_at', 'pk'))
    # Historical receipt at another point is outside a selected point's view.
    if geographic:
        receipts = [r for r in receipts if r.lot.location_id in location_ids]
    quotes_by_request, purchases_by_request, receipts_by_purchase = defaultdict(list), defaultdict(list), defaultdict(list)
    for q in quotes:
        quotes_by_request[q.request_id].append(q)
    for p in purchases:
        purchases_by_request[p.request_id].append(p)
    for receipt in receipts:
        receipts_by_purchase[receipt.purchase_id].append(receipt)

    rows, completed_samples, purchase_samples = [], [], []
    for r in requests:
        qs, ps = quotes_by_request[r.pk], purchases_by_request[r.pk]
        rs = sorted((m for p in ps for m in receipts_by_purchase[p.pk]), key=lambda m: (m.created_at, m.pk))
        # Physical receipts are the evidence of a completed path; PO.received
        # alone (including imported open balances) cannot invent an event time.
        received_quantity = sum((m.quantity for m in rs), Decimal(0))
        fulfilled = received_quantity >= r.quantity
        stage = ('received' if fulfilled else 'receiving' if rs else 'ordered' if ps
                 else 'quoted' if qs else 'review' if r.document.status not in ('approved', 'supplier_quote') else 'sourcing')
        first_quote = min((q.created_at for q in qs if q.created_at is not None), default=None)
        first_purchase = min((p.created_at for p in ps if p.created_at is not None), default=None)
        first_receipt = rs[0].created_at if rs else None
        fulfilled_at, running = None, Decimal(0)
        for receipt in rs:
            running += receipt.quantity
            if running >= r.quantity:
                fulfilled_at = receipt.created_at
                break
        # Every purchase contributing to completion needs a real creation
        # timestamp and consistent temporal ordering. Unknown history stays NULL.
        timing_valid = r.created_at is not None and r.created_at <= now
        timing_valid = timing_valid and all(p.created_at is not None and r.created_at <= p.created_at <= now for p in ps)
        timing_valid = timing_valid and all(q.created_at is not None and r.created_at <= q.created_at <= now for q in qs)
        visible_quotes = {q.pk: q for q in qs}
        timing_valid = timing_valid and all(
            p.quote_id is None or (p.quote_id in visible_quotes
                and visible_quotes[p.quote_id].created_at is not None
                and visible_quotes[p.quote_id].created_at <= p.created_at)
            for p in ps)
        timing_valid = timing_valid and all(m.created_at <= now and next(p for p in ps if p.pk == m.purchase_id).created_at is not None and next(p for p in ps if p.pk == m.purchase_id).created_at <= m.created_at for m in rs)
        duration = _hours(r.created_at, fulfilled_at) if fulfilled and timing_valid else None
        if duration is not None:
            completed_samples.append((fulfilled_at, duration))
        lead_times = []
        for p in ps:
            pr = receipts_by_purchase[p.pk]
            elapsed = _hours(p.created_at, pr[0].created_at) if pr and pr[0].created_at <= now else None
            if elapsed is not None:
                lead_times.append(elapsed)
                purchase_samples.append(elapsed)
        def step(key, label, objects, at):
            return {'stage': key, 'label': label, 'count': len(objects),
                    'refs': [{'id': x.pk, 'code': getattr(x, 'code', None) or x.reference} for x in objects], 'at': _iso(at)}
        next_label = {'review': 'Перевірити вихідний документ', 'sourcing': 'Додати пропозицію',
                      'quoted': 'Порівняти пропозиції', 'ordered': 'Відкрити приймання',
                      'receiving': 'Прийняти залишок', 'received': 'Переглянути історію'}[stage]
        rows.append({
            'id': r.pk, 'code': r.code, 'part': r.part, 'status': r.status,
            'owner_name': r.owner.full_name, 'required_by': _iso(r.required_by), 'currency': r.currency,
            'stage': stage, 'stage_label': STAGES[stage], 'quote_count': len(qs), 'purchase_count': len(ps),
            'document_id': r.document_id, 'created_at': _iso(r.created_at),
            'age_days': round(_hours(r.created_at, now) / 24, 2) if _hours(r.created_at, now) is not None else None,
            'processing_hours': duration, 'first_quote_hours': _hours(r.created_at, first_quote),
            'first_purchase_hours': _hours(r.created_at, first_purchase),
            'median_purchase_to_first_receipt_hours': _median(lead_times),
            'completed_at': _iso(fulfilled_at), 'overdue': r.required_by < today and not fulfilled,
            'scope': 'visible_selected_path',
            'timing_status': 'observed' if duration is not None else 'incomplete_or_unknown',
            'next_action': {'section': 'finance', 'sub': 'procurement', 'label': next_label},
            'steps': [step('request', 'Вимога', [r], r.created_at), step('quote', 'Пропозиції', qs, first_quote),
                      step('purchase', 'Закупівлі', ps, first_purchase), step('receipt', 'Приймання', rs, first_receipt)],
        })

    documents = list(policy.documents().order_by('code', 'pk'))
    doc_ids = {d.pk for d in documents}
    items_qs = policy.queryset(Item)
    if currency:
        items_qs = items_qs.filter(currency=currency)
    if geographic:
        items_qs = items_qs.filter(pk__in={p.item_id for p in purchases} | {lot.item_id for lot in lots})
    items = list(items_qs.order_by('pk'))
    links = defaultdict(lambda: {'requests': [], 'quotes': [], 'items': [], 'lots': []})
    for kind, objects in (('requests', requests), ('quotes', quotes), ('items', items)):
        for obj in objects:
            if obj.document_id in doc_ids:
                links[obj.document_id][kind].append({'kind': kind, 'id': obj.pk, 'code': obj.code})
    for lot in lots:
        for doc_id in set(lot.documents.values()):
            if doc_id in doc_ids:
                links[doc_id]['lots'].append({'kind': 'lots', 'id': lot.pk, 'code': lot.code})
    contract_ids = set(policy.contracts().values_list('pk', flat=True))
    document_rows = []
    for doc in documents:
        groups = [group for values in links[doc.pk].values() for group in values]
        if (geographic or currency) and not groups:
            continue
        counts = {kind: len(values) for kind, values in links[doc.pk].items()}
        kinds = [name for name, count in (('requirement', counts['requests']), ('supplier_quote', counts['quotes']),
                                        ('technical', counts['items']), ('lot_record', counts['lots'])) if count]
        if doc.contract_id in contract_ids:
            kinds.append('contract')
        if not kinds:
            kinds.append('other')
        document_rows.append({
            'id': doc.pk, 'code': doc.code, 'title': doc.title, 'revision': doc.revision,
            'status': doc.status, 'access_level': doc.access_level, 'created_at': _iso(doc.created_at),
            'document_type': TYPE_LABELS[kinds[0]], 'document_type_key': kinds[0], 'document_types': kinds,
            'type_basis': 'visible_relationships', 'linked_counts': counts, 'groups': groups,
            'contract_id': doc.contract_id if doc.contract_id in contract_ids else None,
            'can_download': policy.has('download_document'),
        })
    reviews = sum(d['status'] not in ('approved', 'supplier_quote') for d in document_rows)
    # Metadata linkage check, not byte integrity or hidden-version inspection.
    by_id = {d.pk: d for d in documents}
    missing_lots = sum(any(lot.documents.get(kind) not in by_id or by_id[lot.documents[kind]].status != 'approved'
                           for kind in lot.item.required_documents) for lot in lots)
    reconciliations = [
        {'id': 'document_review', 'title': 'Документи очікують перевірки', 'status': 'attention' if reviews else 'clear',
         'count': reviews, 'next_action': {'section': 'organizer', 'sub': 'documents', 'label': 'Відкрити документи'}},
        {'id': 'lot_document_links', 'title': 'Партії з неповними посиланнями на документи',
         'status': 'attention' if missing_lots else 'clear', 'count': missing_lots,
         'basis': 'visible_document_links_and_approval_only',
         'next_action': {'section': 'erp', 'sub': 'stock', 'label': 'Перевірити комплектність партій'}},
    ]
    if policy.ceo and not geographic:
        from finance.models import StatementLine
        unbound = policy.queryset(StatementLine).filter(transaction__isnull=True)
        if currency:
            unbound = unbound.filter(currency=currency)
        count = unbound.count()
        reconciliations.append({'id': 'statement_unbound', 'title': 'Нерозпізнані рядки банківської виписки',
                               'status': 'attention' if count else 'clear', 'count': count,
                               'next_action': {'section': 'finance', 'sub': 'bank', 'label': 'Відкрити звірку'}})
    from operations.models import Configuration
    dataset = Configuration.objects.filter(key='dataset').first()
    synthetic = bool(getattr(settings, 'BOS_DATA_MODE', None) == 'demo'
                     or (dataset and isinstance(dataset.value, dict) and dataset.value.get('synthetic') is True))
    comparison = _comparison(completed_samples, now)
    if synthetic:
        comparison.update(available=False, change_percent=None,
                          reason='Синтетичний набір: час завантаження прикладів не є виміром прискорення реального бізнесу.')
    counts = Counter(row['stage'] for row in rows)
    return {'documents': document_rows, 'workflow': {
        'requests': rows, 'stage_labels': STAGES,
        'metrics': {'request_count': len(rows), 'stage_counts': {key: counts[key] for key in STAGES},
                    'overdue_count': sum(row['overdue'] for row in rows),
                    'timed_request_count': len(completed_samples),
                    'median_processing_hours': _median([h for _, h in completed_samples]),
                    'timed_purchase_count': len(purchase_samples),
                    'median_purchase_to_first_receipt_hours': _median(purchase_samples)},
        'comparison': comparison, 'reconciliations': reconciliations, 'synthetic': synthetic,
        'as_of': _iso(today), 'measured_at': _iso(now),
        'scope_notice': 'Лише доступні записи вибраної філії, точки та валюти. Стадія описує видимий шлях вимоги.',
        'timing_notice': 'Час нових записів фіксується при створенні. Невідомий історичний час не відновлюється. Тривалість не доводить ефект автоматизації.',
    }}
