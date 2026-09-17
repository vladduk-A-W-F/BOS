"""Детерминированный генератор демо-показателей для узлов оргструктуры.

Зачем отдельный модуль: реальных план/факт данных в БД пока нет (нет модели
бюджета), но дашборд руководителя должен выглядеть и вести себя как рабочий.
Генератор даёт правдоподобные цифры, которые:

* **детерминированы** — seed берётся из code узла + периода, поэтому при
  каждом запросе цифры одни и те же (иначе KPI прыгали бы на каждый рефетч);
* **аддитивны** — показатели поддерева = сумма показателей листьев, значит
  клик по родителю даёт согласованную с детьми картину;
* **согласованы со статусом** — узел со status='red' не покажет 112% плана.

Никакой специфики конкретной организации здесь нет: всё считается от
employee_count и type узла, поэтому генератор так же работает на любой
другой оргструктуре.
"""

import hashlib
import random

# Сколько «дохода» приносит один сотрудник за месяц, в гривне.
# Тип узла задаёт масштаб: центральный офис зарабатывает на голову больше
# регионального, мобильный — меньше всех.
REVENUE_PER_HEAD = {
    'headquarters': 145_000,
    'department':   120_000,
    'regional':      95_000,
    'foreign':      160_000,
    'mobile':        60_000,
}

# Насколько узел выполняет план — диапазон достижения, привязанный к статусу.
# Это и есть смысл цветов на карте: зелёный = план сделан, красный = провал.
# Зелёный узел план ПЕРЕвыполняет (а не «еле дотягивает»): иначе агрегат по
# всей компании садится на 96-99% и весь дашборд окрашивается в жёлтое,
# хотя проблемных филиалов всего три.
STATUS_ACHIEVEMENT = {
    'green':  (1.02, 1.18),
    'yellow': (0.90, 1.01),
    'red':    (0.62, 0.85),
}

# Множитель периода: квартал = три месяца (с небольшой нелинейностью,
# чтобы квартальные цифры не выглядели как месячные ×3 ровно).
PERIOD_MULTIPLIER = {'month': 1.0, 'quarter': 2.94}

SPARK_POINTS = 12


def _rng(*parts):
    """RNG с воспроизводимым seed из произвольных ключей."""
    key = '|'.join(str(p) for p in parts)
    seed = int(hashlib.md5(key.encode()).hexdigest()[:12], 16)
    return random.Random(seed)


METRIC_KEYS = (
    'revenue', 'plan_revenue', 'expenses', 'plan_expenses', 'ebitda', 'plan_ebitda',
    'net_profit', 'plan_net_profit', 'cash_flow', 'plan_cash_flow', 'receivable',
    'plan_receivable', 'payable', 'plan_payable', 'services', 'plan_services',
    'nps_weighted', 'kpi_weighted', 'heads',
)


def zero_metrics():
    return {k: 0.0 for k in METRIC_KEYS}


def branch_metrics(branch, period='month', is_container=False):
    """Демо-показатели ОДНОГО узла (без потомков).

    Возвращает плоский dict сумм — агрегатор просто складывает такие dict'ы
    по поддереву, поэтому здесь не должно быть производных величин
    (маржи, процентов): их считает агрегатор уже на сумме.

    is_container — у узла есть дети (группа «Іноземні філії», «Київ» и т.п.).
    Такие узлы своих показателей не имеют: их цифры это сумма детей, и если
    добавить сюда ещё и собственные, поддерево посчитается дважды.
    """
    if is_container:
        return zero_metrics()

    rng = _rng(branch.code, period)
    mult = PERIOD_MULTIPLIER.get(period, 1.0)

    # Голов минимум 3 — чтобы лист без заведённых сотрудников не давал нули
    # и не «съедал» строку в дереве и точку на карте.
    heads = max(branch.employee_count, 3)
    per_head = REVENUE_PER_HEAD.get(branch.type, 95_000)

    plan_revenue = heads * per_head * mult * rng.uniform(0.9, 1.1)
    lo, hi = STATUS_ACHIEVEMENT.get(branch.status, STATUS_ACHIEVEMENT['green'])
    achievement = rng.uniform(lo, hi)
    revenue = plan_revenue * achievement

    # Расходы держим долей от плана, а не от факта: иначе провал по доходу
    # автоматически «экономил» бы расходы, и EBITDA никогда не уходила в минус.
    expense_ratio = rng.uniform(0.62, 0.74)
    plan_expenses = plan_revenue * expense_ratio
    # Обычно укладываемся в бюджет расходов, иногда нет — карточка «Витрати»
    # считает процент зеркально, поэтому экономия там читается как зелёная.
    expenses = plan_expenses * rng.uniform(0.90, 1.03)

    ebitda = revenue - expenses
    plan_ebitda = plan_revenue - plan_expenses

    # Из EBITDA в чистую прибыль: проценты, амортизация, налоги.
    net_factor = rng.uniform(0.72, 0.86)
    net_profit = ebitda * net_factor
    plan_net_profit = plan_ebitda * net_factor

    return {
        'revenue':         revenue,
        'plan_revenue':    plan_revenue,
        'expenses':        expenses,
        'plan_expenses':   plan_expenses,
        'ebitda':          ebitda,
        'plan_ebitda':     plan_ebitda,
        'net_profit':      net_profit,
        'plan_net_profit': plan_net_profit,
        'cash_flow':       net_profit * rng.uniform(0.38, 0.50),
        'plan_cash_flow':  plan_net_profit * 0.40,
        # Плановые «потолки» задолженностей выше среднего факта: превышение
        # потолка — исключение (жёлтая карточка), а не норма.
        'receivable':      revenue * rng.uniform(0.22, 0.34),
        'plan_receivable': plan_revenue * 0.31,
        'payable':         revenue * rng.uniform(0.18, 0.29),
        'plan_payable':    plan_revenue * 0.26,
        'services':        heads * rng.uniform(7, 16) * mult,
        'plan_services':   heads * 12 * mult,
        # NPS взвешиваем по головам при агрегации — большой филиал должен
        # тянуть общий балл сильнее маленького.
        'nps_weighted':    rng.uniform(58, 92) * heads,
        'kpi_weighted':    rng.uniform(68, 96) * heads,
        'heads':           heads,
    }


def sparkline(key, scope_code, period, end_value, points=SPARK_POINTS):
    """Ряд из `points` значений, плавно приходящий к end_value.

    Sparkline рисует «как шли к текущему числу», поэтому последняя точка
    обязана совпадать с показанным значением — иначе график противоречит
    крупной цифре над ним.
    """
    if not end_value:
        return [0] * points
    rng = _rng('spark', key, scope_code, period)
    # Стартуем на 12-35% ниже/выше конца и идём к нему с шумом.
    start = end_value * rng.uniform(0.65, 0.9)
    series = []
    for i in range(points):
        t = i / (points - 1)
        base = start + (end_value - start) * t
        series.append(round(base * rng.uniform(0.94, 1.06), 2))
    series[-1] = round(end_value, 2)
    return series


def demo_task_stats(scope_code, period):
    """Демо-разбивка задач — для узлов, к которым реальные задачи не привязаны."""
    rng = _rng('tasks', scope_code, period)
    total = rng.randint(40, 260)
    done = int(total * rng.uniform(0.55, 0.72))
    overdue = int(total * rng.uniform(0.05, 0.14))
    process = int((total - done - overdue) * rng.uniform(0.35, 0.6))
    active = total - done - overdue - process
    return {
        'total': total, 'done': done, 'overdue': overdue,
        'process': process, 'active': max(active, 0),
        'completion_rate': round(done / total * 100) if total else 0,
    }
