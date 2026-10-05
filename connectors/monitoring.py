"""Connected sources in «Моніторинг»: freshness for everyone, mapped rows by role. Read-only.

Rows come from the latest stored snapshot read with the source's own mapping; nothing is fetched here.
Money follows the existing rule: amounts and payments only for the CEO; the observer sees freshness only.
"""
from django.utils import timezone

from . import mapping
from .views import STALE_AFTER, _visible, read_mapped

LIMIT = 50
MONEY = ('amount', 'currency')


def _freshness(connector, now):
    if connector.status == 'error':
        return 'error', 'Помилка читання: ' + (connector.last_error or 'джерело недоступне')
    if connector.last_sync_at is None:
        return 'unknown', 'Ще не прочитано'
    if connector.kind == 'google_sheets' and now - connector.last_sync_at > STALE_AFTER:
        return 'stale', 'Дані застаріли, оновіть джерело'
    if connector.kind == 'csv':
        # The time itself is last_sync_at; screens format it in the viewer's time zone.
        return 'file', 'Дані із завантаженого файлу'
    return 'fresh', 'Актуально'


def build(policy, now=None):
    """[{id, name, dataset, freshness, ...}] in the order the sources are listed in «Підключення»."""
    now = now or timezone.now()
    out = []
    for connector in _visible(policy).prefetch_related('snapshots'):
        state, note = _freshness(connector, now)
        item = {'id': connector.pk, 'name': connector.name, 'kind': connector.kind, 'dataset': connector.dataset,
                'dataset_label': connector.get_dataset_display(), 'freshness': state, 'freshness_label': note,
                'last_sync_at': connector.last_sync_at.isoformat() if connector.last_sync_at else None,
                'mapped': bool(connector.mapping)}
        if policy.role != 'observer':
            read = read_mapped(connector, connector.snapshots.first())
            if read is None:
                item['problem'] = 'Колонки не зіставлено з полями BoS' if connector.dataset in mapping.FIELDS else ''
            elif 'error' in read:
                item['problem'] = 'Відповідність колонок застаріла: ' + read['error']
            else:
                item.update(accepted=read['accepted'], total=read['total'], rejected=read['total'] - read['accepted'],
                            rejected_examples=read['rejected'][:5], table=_table(policy, connector, read))
        out.append(item)
    return out


def _table(policy, connector, read):
    labels = {f: label for f, label, _, _ in mapping.FIELDS[connector.dataset]}
    shown = [f for f in labels if f in connector.mapping or (f == 'currency' and 'amount' in connector.mapping)]
    if not policy.ceo:
        shown = [f for f in shown if f not in MONEY]
    rows = [{'ref': {'kind': 'connector', 'id': connector.pk}, 'late': False,
             'cells': ['' if r.get(f) is None else r[f] for f in shown]} for r in read['rows']]
    return {'key': f'source-{connector.pk}', 'title': connector.name, 'columns': [labels[f] for f in shown],
            'rows': rows[:LIMIT], 'total': len(rows)}


def attention(sources):
    """Plain-language items for sources that need a person: unreadable, stale, unmapped or with rejected rows."""
    out = []
    for s in sources:
        ref = {'kind': 'connector', 'id': s['id']}
        if s['freshness'] in ('error', 'stale'):
            out.append({'level': 'danger' if s['freshness'] == 'error' else 'warning', 'ref': ref,
                        'title': f'Джерело «{s["name"]}»: ' + s['freshness_label'].split(':')[0].lower(),
                        'detail': s['freshness_label']})
        if s.get('problem'):
            out.append({'level': 'warning', 'ref': ref, 'title': f'Джерело «{s["name"]}» не показується в моніторингу',
                        'detail': s['problem'] + '.'})
        elif s.get('rejected'):
            out.append({'level': 'warning', 'ref': ref,
                        'title': f'Джерело «{s["name"]}»: {s["rejected"]} з {s["total"]} рядків не прочитано',
                        'detail': 'Наприклад, рядок {row}: {reason}.'.format(**s['rejected_examples'][0])})
    return out
