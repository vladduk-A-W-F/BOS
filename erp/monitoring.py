"""BoS 4 «Моніторинг»: numbers, tables and standard queries. Read-only, no LLM.

Every row comes from Policy-scoped querysets; money is shown only to the CEO,
matching Policy.capabilities()['finance'].
"""
from datetime import date
from decimal import Decimal as D

from django.utils import timezone

from operations.models import Invoice
from operations.service import as_of
from tasks.models import Task
from .balances import invoice_settlement, purchase_open, sales_open
from .models import Lot, Movement, Purchase, SalesOrder

LIMIT = 50
QUALITY = {'pending': 'Чекає перевірки', 'blocked': 'Заблоковано', 'rework': 'Доопрацювання', 'approved': 'Допущено'}
MOVES = {'opening': 'Початковий залишок', 'receipt': 'Надходження', 'transfer_out': 'Видача', 'transfer_in': 'Прийнято',
         'transfer_dispatch': 'Відправлено', 'transfer_receive': 'Прийнято', 'consume': 'Списано у виробництво',
         'production': 'Випуск', 'shipment': 'Відвантаження', 'return': 'Повернення', 'adjustment': 'Коригування'}
PRIORITY = {'high': 'Високий', 'medium': 'Середній', 'low': 'Низький'}


def _num(value):
    value = D(value)
    return int(value) if value == value.to_integral() else float(value)


def _date(value):
    return value.isoformat() if value else ''


def _table(key, title, columns, rows):
    return {'key': key, 'title': title, 'columns': columns, 'rows': rows[:LIMIT], 'total': len(rows)}


def _open_orders(policy, today, overdue_only=False):
    rows = []
    orders = policy.queryset(SalesOrder).filter(status='confirmed').select_related('customer', 'branch').order_by('due_date', 'code')
    for order in orders:
        lines = list(order.lines.all())
        ordered = sum((l.quantity for l in lines), D(0))
        remaining = sum((sales_open(l) for l in lines), D(0))
        if not remaining or (overdue_only and order.due_date >= today):
            continue
        cells = [order.code, order.customer.name, order.branch.short_name or order.branch.name if order.branch else '',
                 _date(order.due_date), f'{_num(ordered - remaining)} з {_num(ordered)}']
        if policy.ceo:
            cells.append(_num(sum((l.quantity * l.price for l in lines), D(0))))
        rows.append({'ref': {'kind': 'order', 'id': order.pk}, 'late': order.due_date < today, 'cells': cells})
    columns = ['Замовлення', 'Клієнт', 'Філія', 'Строк', 'Відвантажено'] + (['Сума, грн'] if policy.ceo else [])
    return columns, rows


def _problem_lots(policy):
    lots = (policy.queryset(Lot).exclude(quality='approved').filter(quantity__gt=0)
            .select_related('item', 'location').order_by('quality', 'code'))
    rows = [{'ref': {'kind': 'lot', 'id': lot.pk}, 'late': lot.quality == 'blocked', 'unit': lot.item.unit,
             'cells': [lot.item.name, lot.location.name, _num(lot.quantity), QUALITY.get(lot.quality, lot.quality), lot.code]}
            for lot in lots]
    return ['Виріб', 'Склад', 'Кількість', 'Стан', 'Партія'], rows


def _debts(policy, today, overdue_only=False):
    if not policy.ceo:
        return None
    rows = []
    for invoice in Invoice.objects.select_related('customer').order_by('due_date', 'code'):
        rest = invoice_settlement(invoice)['receivable']
        if not rest or (overdue_only and invoice.due_date >= today):
            continue
        late = (today - invoice.due_date).days if invoice.due_date < today else 0
        rows.append({'ref': {'kind': 'invoice', 'id': invoice.pk}, 'late': late > 0,
                     'cells': [invoice.code, invoice.customer.name, _num(invoice.amount), _num(invoice.paid),
                               _num(rest), _date(invoice.due_date), late]})
    return ['Рахунок', 'Клієнт', 'Сума, грн', 'Оплачено, грн', 'Залишок, грн', 'Строк', 'Днів прострочки'], rows


def _tasks(policy, today, overdue_only=False):
    rows = []
    for task in policy.tasks().filter(archived_at__isnull=True).exclude(status='done').select_related('branch'):
        late = task.status == 'overdue' or bool(task.deadline and task.deadline < today)
        if overdue_only and not late:
            continue
        rows.append({'ref': {'kind': 'task', 'id': task.pk}, 'late': late,
                     'cells': [task.title, task.assignee, task.branch.short_name if task.branch else '',
                               _date(task.deadline), PRIORITY.get(task.priority, '')]})
    rows.sort(key=lambda r: (not r['late'], r['cells'][3] or '9999'))
    return ['Доручення', 'Відповідальний', 'Філія', 'Строк', 'Пріоритет'], rows


def _movements(policy, kinds=None, day=None):
    rows = policy.queryset(Movement).select_related('lot__item', 'lot__location').order_by('-created_at', '-pk')
    if kinds:
        rows = rows.filter(kind__in=kinds)
    if day:
        rows = rows.filter(created_at__date=day)
    out = [{'ref': {'kind': 'lot', 'id': m.lot_id}, 'late': False,
            'cells': [timezone.localtime(m.created_at).strftime('%d.%m %H:%M'), MOVES.get(m.kind, m.kind),
                      m.lot.item.name, _num(m.quantity), m.lot.location.name, m.reference]}
           for m in rows[:LIMIT]]
    return ['Коли', 'Операція', 'Виріб', 'Кількість', 'Склад', 'Документ'], out


def _late_purchases(policy, today):
    rows = []
    for po in policy.queryset(Purchase).filter(due_date__lt=today).select_related('item', 'supplier').order_by('due_date'):
        rest = purchase_open(po)
        if rest:
            rows.append({'ref': {'kind': 'purchase', 'id': po.pk}, 'late': True, 'unit': po.item.unit,
                         'cells': [po.code, po.item.name, po.supplier.name, _num(rest), _date(po.due_date), (today - po.due_date).days]})
    return ['Закупівля', 'Що', 'Постачальник', 'Чекаємо', 'Строк', 'Днів прострочки'], rows


QUERIES = (
    ('late_orders', 'Прострочені замовлення', False),
    ('debts', 'Хто винен і скільки', True),
    ('blocked_lots', 'Партії без допуску', False),
    ('late_tasks', 'Прострочені доручення', False),
    ('received_today', 'Що надійшло сьогодні', False),
    ('late_purchases', 'Закупівлі, що запізнюються', False),
)


def query(policy, key):
    today = as_of()
    known = {k: (title, ceo) for k, title, ceo in QUERIES}
    if key not in known:
        raise KeyError('Невідомий запит.')
    title, ceo_only = known[key]
    if ceo_only and not policy.ceo:
        raise PermissionError('Фінансові запити доступні лише керівнику.')
    if key == 'late_orders':
        columns, rows = _open_orders(policy, today, overdue_only=True)
    elif key == 'debts':
        columns, rows = _debts(policy, today)
    elif key == 'blocked_lots':
        columns, rows = _problem_lots(policy)
    elif key == 'late_tasks':
        columns, rows = _tasks(policy, today, overdue_only=True)
    elif key == 'received_today':
        columns, rows = _movements(policy, ('receipt', 'transfer_receive', 'production'), timezone.localdate())
    else:
        columns, rows = _late_purchases(policy, today)
    return {'as_of': _date(today), **_table(key, title, columns, rows)}


def _days(n):
    n = abs(int(n))
    word = 'день' if n % 10 == 1 and n % 100 != 11 else 'дні' if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 'днів'
    return f'{n} {word}'


def _money(value):
    return f'{_num(value):,}'.replace(',', ' ') + ' грн'


def _attention(policy, today, orders, lots, debts, purchases, tasks):
    """What needs a person's decision now, in plain words, worst first. Built from the same rows as the tables."""
    out = []
    for r in orders:
        if r['late']:
            code, customer, _, due, shipped = r['cells'][:5]
            days = (today - date.fromisoformat(due)).days
            out.append({'level': 'danger', 'ref': r['ref'], 'title': f'Замовлення {code} прострочене на {_days(days)}',
                        'detail': f'{customer}: відвантажено {shipped}.'})
    for r in debts or []:
        if r['late']:
            code, customer, _, _, rest, _, days = r['cells']
            out.append({'level': 'danger', 'ref': r['ref'], 'title': f'{customer} винен {_money(rest)}',
                        'detail': f'Рахунок {code}, прострочка {_days(days)}.'})
    for r in lots:
        if r['late']:
            item, place, qty, state, code = r['cells']
            out.append({'level': 'danger', 'ref': r['ref'], 'title': f'Партія {code} заблокована',
                        'detail': f'{item}, {qty} {r["unit"]} на «{place}». Не відвантажувати до рішення якості.'})
    for r in purchases:
        code, item, supplier, rest, _, days = r['cells']
        out.append({'level': 'warning', 'ref': r['ref'], 'title': f'Закупівля {code} запізнюється на {_days(days)}',
                    'detail': f'{supplier}: чекаємо ще {rest} {r["unit"]} — {item}.'})
    for r in lots:
        if not r['late']:
            item, place, qty, state, code = r['cells']
            out.append({'level': 'warning', 'ref': r['ref'], 'title': f'Партія {code}: {state.lower()}',
                        'detail': f'{item}, {qty} {r["unit"]} на «{place}».'})
    for r in tasks:
        if r['late']:
            title, who = r['cells'][:2]
            out.append({'level': 'warning', 'ref': r['ref'], 'title': f'Прострочене доручення: {title}',
                        'detail': f'Відповідальний: {who}.' if who else 'Відповідального не призначено.'})
    return out[:8]


def build(policy):
    today = as_of()
    orders = _table('orders', 'Замовлення в роботі', *_open_orders(policy, today))
    lots = _table('lots', 'Проблемні партії', *_problem_lots(policy))
    tasks = _table('tasks', 'Доручення', *_tasks(policy, today))
    moves = _table('movements', 'Останні операції', *_movements(policy))
    debts = _debts(policy, today)
    tables = [orders, lots] + ([_table('invoices', 'Рахунки й оплати', *debts)] if debts else []) + [tasks, moves]
    late_po = _late_purchases(policy, today)[1]
    late_tasks = sum(r['late'] for r in _tasks(policy, today)[1])
    numbers = [
        {'key': 'orders', 'label': 'Замовлень у роботі', 'value': orders['total'], 'alert': sum(r['late'] for r in orders['rows'])},
        {'key': 'lots', 'label': 'Проблемних партій', 'value': lots['total'], 'alert': lots['total']},
        {'key': 'tasks', 'label': 'Прострочених доручень', 'value': late_tasks, 'alert': late_tasks},
        {'key': 'purchases', 'label': 'Закупівель із запізненням', 'value': len(late_po), 'alert': len(late_po)},
    ]
    if debts:
        numbers.insert(2, {'key': 'invoices', 'label': 'До оплати, грн',
                           'value': _num(sum((D(str(r['cells'][4])) for r in debts[1]), D(0))),
                           'alert': sum(r['late'] for r in debts[1])})
    attention = _attention(policy, today, orders['rows'], lots['rows'], debts[1] if debts else None, late_po,
                           _tasks(policy, today)[1])
    return {'as_of': _date(today), 'numbers': numbers, 'tables': tables, 'attention': attention,
            'queries': [{'key': k, 'title': t} for k, t, ceo in QUERIES if policy.ceo or not ceo]}
