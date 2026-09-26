from boss_project.policy import Policy
"""API дашборда руководителя.

Четыре эндпоинта:
  GET /api/branches/           — дерево оргструктуры (для сайдбара);
  GET /api/dashboard/summary/  — все виджеты дашборда одним ответом;
  GET /api/dashboard/helicopter/ — вертолётная видимость (светофор + пожары);
  GET /api/dashboard/activity/ — лента последних событий.

Формы ответов summary и helicopter зафиксированы фронтом
(frontend/boss_app_html.html, компоненты Dashboard и Heli) — менять поля
можно только парой с фронтом.
"""

from django.db.models import Avg, Count, Q
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ai_assistant.models import EmployeeChangeLog, TaskChangeLog
from employees.models import Employee
from tasks.models import Task
from tasks.queries import active as active_tasks,statistics as task_statistics,overdue_q

from . import demo
from .models import Branch
from .serializers import BranchTreeSerializer, ordered

# Сколько узлов максимум подсвечивать алертами — дашборд руководителя,
# а не лог: больше трёх строк превращают алерт-бар в шум.
MAX_ALERTS = 3

VALID_PERIODS = ('month', 'quarter')

# ── Вертолёт: пороги «пожаров» ─────────────────────────────────────────────
# Дашборд показывает цифры, вертолёт отвечает на вопрос «горит или нет».
# Пороги собраны здесь, чтобы после обкатки на живых данных крутить их
# в одном месте.
REVENUE_CRITICAL_PCT = 85   # доход компании < 85% плана — пожар
REVENUE_WARNING_PCT = 95    # < 95% — предупреждение
EXPENSE_OK_PCT = 90         # расходы: pct (план/факт) ниже 90 → перерасход
OVERDUE_WARN = 10           # > 10% задач просрочено — предупреждение…
OVERDUE_CRITICAL = 20       # …> 20% — пожар (минимумы 3/5 шт. защищают от
                            # «1 просрочка из 4 = пожар» на малых выборках)
KPI_MIN = 70                # средний KPI команды ниже — предупреждение
MAX_FIRES = 8               # вертолёт, а не лог: длинный список = шум

DIM_LABELS = {
    'finance':  'Фінанси',
    'tasks':    'Завдання',
    'branches': 'Філії',
    'team':     'Команда',
}

# Вклад измерения в health score: зелёное 25, жёлтое 14, красное 6.
_DIM_SCORE = {'green': 25, 'yellow': 14, 'red': 6}


@api_view(['GET'])
def branch_tree(request):
    """Дерево от корней вниз. Фронт расплющивает его сам."""
    roots = Branch.objects.filter(parent__isnull=True).prefetch_related('children')
    return Response(BranchTreeSerializer(ordered(roots), many=True).data)


def _scope(branch_id):
    """Узел + все его потомки. branch_id=None → вся компания.

    Возвращает (branches_in_scope, scope_code) — код нужен как seed
    для демо-генератора, чтобы «вся компания» и отдельный филиал давали
    разные, но стабильные ряды.
    """
    if branch_id:
        try:
            node = Branch.objects.get(pk=branch_id)
        except Branch.DoesNotExist:
            return None, None
        ids = node.descendant_ids()
        return Branch.objects.filter(id__in=ids), node.code
    return Branch.objects.all(), '__ALL__'


def _kpi(actual, plan, spark_key, scope_code, period, invert=False):
    """Один KPI в форме, которую ждёт KPICard на фронте.

    invert=True — для расходов и задолженности: там перевыполнение плана
    это плохо, поэтому pct считаем зеркально (план/факт), чтобы цветовая
    логика карточки (>=90% зелёный) осталась одна на все карточки.
    """
    actual = round(actual)
    plan = round(plan)
    if not plan:
        pct = 0
    elif invert:
        pct = round(plan / actual * 100) if actual else 100
    else:
        pct = round(actual / plan * 100)

    spark = demo.sparkline(spark_key, scope_code, period, actual)
    # Тренд MoM — сравнение двух последних точек ряда; ряд детерминирован,
    # поэтому тренд не «дрожит» между запросами.
    prev = spark[-2] if len(spark) > 1 and spark[-2] else 0
    if prev:
        delta = (actual - prev) / prev * 100
        trend = f'{delta:+.1f}%'
    else:
        trend = ''
    return {'actual': actual, 'plan': plan, 'pct': pct, 'trend': trend, 'spark': spark}


def _task_stats(branches_in_scope, branch_id, scope_code, period, policy=None):
    """Єдиний фактичний розподіл активних доручень, включно з реальним нулем."""
    qs=active_tasks(policy.tasks() if policy else None)
    if branch_id:qs=qs.filter(branch__in=branches_in_scope)
    return task_statistics(qs),False


def _team_stats(branches_in_scope, branch_id, totals):
    """Команда: реальные сотрудники, если заведены; иначе счётчики узлов."""
    qs = Employee.objects.all()
    if branch_id:
        qs = qs.filter(branch__in=branches_in_scope)
    agg = qs.aggregate(total=Count('id'), avg_kpi=Avg('kpi'))
    if agg['total']:
        return {'total': agg['total'], 'avg_kpi': round(agg['avg_kpi'] or 0)}
    heads = totals['heads'] or 1
    return {
        'total': round(totals['heads']),
        'avg_kpi': round(totals['kpi_weighted'] / heads),
    }


def _alerts(branches_in_scope, task_stats):
    """Алерт-бар: проблемные узлы + просроченные задачи.

    Пусто = всё в норме, фронт тогда прячет полосу.
    """
    alerts = []
    for b in branches_in_scope.filter(status='red')[:MAX_ALERTS]:
        alerts.append({'severity': 'critical', 'text': f'{b.name}: невиконання плану / простій'})
    remaining = MAX_ALERTS - len(alerts)
    if remaining > 0:
        for b in branches_in_scope.filter(status='yellow')[:remaining]:
            alerts.append({'severity': 'warning', 'text': f'{b.name}: відхилення від плану'})
    if task_stats.get('overdue'):
        alerts.append({'severity': 'warning',
                       'text': f"Прострочені задачі: {task_stats['overdue']}"})
    return alerts[:MAX_ALERTS + 1]


def _snapshot(scope_list, period):
    """Демо-показатели поддерева: суммы по всем узлам + % плана каждого узла.

    Общая часть dashboard_summary и dashboard_helicopter. Узлы-контейнеры
    (у которых есть дети) в сумму не входят — см. demo.branch_metrics.
    % выполнения поднимается от листа ко всем предкам, поэтому контейнер
    показывает процент своего поддерева (тултипы, дерево, вертолёт).
    """
    container_ids = set(
        Branch.objects.exclude(parent__isnull=True).values_list('parent_id', flat=True)
    )

    totals = demo.zero_metrics()
    parent_of = {b.id: b.parent_id for b in scope_list}
    rolled = {b.id: [0.0, 0.0] for b in scope_list}
    for b in scope_list:
        m = demo.branch_metrics(b, period, is_container=b.id in container_ids)
        for k, v in m.items():
            totals[k] += v
        node_id = b.id
        while node_id is not None and node_id in rolled:
            rolled[node_id][0] += m['revenue']
            rolled[node_id][1] += m['plan_revenue']
            node_id = parent_of.get(node_id)

    per_branch_pct = {
        bid: round(rev / plan * 100) if plan else 0
        for bid, (rev, plan) in rolled.items()
    }
    return totals, per_branch_pct



def _operational_dashboard(request, helicopter=False):
    from django.conf import settings
    p=Policy(request)
    tasks=active_tasks(p.tasks())
    branch_id=request.GET.get('branch_id') or request.GET.get('branch')
    if branch_id:
        try:
            branch=Branch.objects.get(pk=branch_id)
        except (Branch.DoesNotExist,ValueError):
            return Response({'detail':'Філію не знайдено.'},status=404)
        tasks=tasks.filter(branch_id__in=branch.descendant_ids())
    from operations.service import as_of
    stats=task_statistics(tasks);overdue=stats['overdue']
    if not helicopter:
        return Response({'is_demo':settings.BOS_DATA_MODE=='demo','tasks':stats,'scope':'Доступні операційні дані'})
    status='yellow' if overdue else 'green'
    return Response({'is_demo':settings.BOS_DATA_MODE=='demo','verdict':{'status':status,'headline':'Стан доступних доручень','score':stats['completion_rate']},'dimensions':[{'key':'tasks','label':'Доручення','status':status,'detail':str(overdue)+' прострочених'}],'fires':[{'severity':'warning','dimension':'tasks','title':str(overdue)+' прострочених доручень','detail':'Перевірте відповідальних і строки.'}] if overdue else [],'branches_health':[{'id':b.pk,'name':b.name,'overdue':tasks.filter(branch=b).filter(overdue_q()).count()} for b in Branch.objects.all()]})

@api_view(['GET'])
def dashboard_summary(request):
    if not Policy(request).ceo:return _operational_dashboard(request)
    """Все виджеты дашборда для выбранного узла и периода."""
    branch_id = request.GET.get('branch_id') or request.GET.get('branch')
    if branch_id in ('all', 'null', ''):
        branch_id = None

    period = request.GET.get('period', 'month')
    if period not in VALID_PERIODS:
        period = 'month'

    branches_in_scope, scope_code = _scope(branch_id)
    if branches_in_scope is None:
        return Response({'detail': 'Branch not found'}, status=404)

    scope_list = list(branches_in_scope)
    totals, per_branch_pct = _snapshot(scope_list, period)

    # Финансовые KPI целиком демо — и факт, и план.
    #
    # Подмешивать сюда реальные Transaction нельзя: плана в БД нет (модели
    # бюджета не существует), поэтому реальный факт делился бы на выдуманный
    # план другого порядка и все проценты выполнения теряли смысл.
    # Как только появится модель плана — факт берётся из транзакций, план
    # из неё, и is_demo выключается. До тех пор BETA-баннер честно висит.
    heads = totals['heads'] or 1
    net_margin = (totals['net_profit'] / totals['revenue'] * 100) if totals['revenue'] else 0
    plan_margin = (totals['plan_net_profit'] / totals['plan_revenue'] * 100) if totals['plan_revenue'] else 0

    kpis = {
        'revenue':    _kpi(totals['revenue'], totals['plan_revenue'], 'revenue', scope_code, period),
        'expenses':   _kpi(totals['expenses'], totals['plan_expenses'], 'expenses', scope_code, period, invert=True),
        'ebitda':     _kpi(totals['ebitda'], totals['plan_ebitda'], 'ebitda', scope_code, period),
        'net_profit': _kpi(totals['net_profit'], totals['plan_net_profit'], 'net_profit', scope_code, period),
        'net_margin': _kpi(net_margin, plan_margin, 'net_margin', scope_code, period),
        'cash_flow':  _kpi(totals['cash_flow'], totals['plan_cash_flow'], 'cash_flow', scope_code, period),
        'receivable': _kpi(totals['receivable'], totals['plan_receivable'], 'receivable', scope_code, period, invert=True),
        'payable':    _kpi(totals['payable'], totals['plan_payable'], 'payable', scope_code, period, invert=True),
    }

    task_stats, tasks_are_demo = _task_stats(branches_in_scope, branch_id, scope_code, period, Policy(request))
    team = _team_stats(branches_in_scope, branch_id, totals)

    services_val = round(totals['services'])
    nps_val = round(totals['nps_weighted'] / heads)

    branch_rows = []
    for b in scope_list:
        row = {
            'id': b.id, 'code': b.code, 'name': b.name, 'type': b.type,
            'parent': b.parent_id, 'lat': b.lat, 'lng': b.lng,
            'status': b.status, 'employee_count': b.employee_count,
            'revenue_pct': per_branch_pct.get(b.id, 0),
        }
        branch_rows.append(row)

    return Response({
        # is_demo управляет BETA-баннером. Пока плана нет в БД — всегда True.
        'is_demo': True,
        'tasks_are_demo': tasks_are_demo,
        'period': period,
        'selected_branch': int(branch_id) if branch_id else None,
        'kpis': kpis,
        'tasks': task_stats,
        'team': team,
        'alerts': _alerts(branches_in_scope, task_stats),
        'branches': branch_rows,
        'services': {
            'value': services_val,
            'plan': round(totals['plan_services']),
            'spark': demo.sparkline('services', scope_code, period, services_val),
        },
        'nps': {
            'value': nps_val,
            'status': 'green' if nps_val >= 70 else 'yellow' if nps_val >= 50 else 'red',
            'spark': demo.sparkline('nps', scope_code, period, nps_val),
        },
    })


def _ua_plural(n, forms):
    """Украинская плюрализация: 1 пожежа / 2 пожежі / 5 пожеж."""
    n10, n100 = n % 10, n % 100
    if n10 == 1 and n100 != 11:
        return forms[0]
    if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
        return forms[1]
    return forms[2]


def _dim(key, status, detail):
    """Одно измерение вертолёта в форме, которую ждёт фронт."""
    return {'key': key, 'label': DIM_LABELS[key], 'status': status, 'detail': detail}


@api_view(['GET'])
def dashboard_helicopter(request):
    if not Policy(request).ceo:return _operational_dashboard(request,True)
    """Вертолётная видимость: светофор компании + отсортированные «пожары».

    Всегда считает всю компанию — drill-down по конкретному филиалу делает
    обычный дашборд (фронт переходит туда с выбранным branch_id). Из
    параметров понимает только period=month|quarter.
    """
    period = request.GET.get('period', 'month')
    if period not in VALID_PERIODS:
        period = 'month'

    scope_list = list(Branch.objects.all())
    if not scope_list:
        return Response({
            'is_demo': True,
            'period': period,
            'verdict': {'status': 'green', 'headline': 'Немає даних про філії', 'score': 0},
            'dimensions': [_dim(k, 'green', 'Немає даних') for k in DIM_LABELS],
            'fires': [],
            'branches_health': [],
        })

    totals, per_branch_pct = _snapshot(scope_list, period)
    task_stats, _ = _task_stats(scope_list, None, '__ALL__', period, Policy(request))
    team = _team_stats(scope_list, None, totals)

    revenue_pct = round(totals['revenue'] / totals['plan_revenue'] * 100) \
        if totals['plan_revenue'] else 0
    # Зеркальный pct расходов, как в _kpi(invert=True): ниже 100 = перерасход.
    expense_pct = round(totals['plan_expenses'] / totals['expenses'] * 100) \
        if totals['expenses'] else 100

    # ── Статусы четырёх измерений ──
    if revenue_pct < REVENUE_CRITICAL_PCT:
        fin_status = 'red'
    elif revenue_pct < REVENUE_WARNING_PCT or expense_pct < EXPENSE_OK_PCT:
        fin_status = 'yellow'
    else:
        fin_status = 'green'

    overdue = task_stats.get('overdue', 0)
    total_tasks = task_stats.get('total', 0)
    overdue_ratio = round(overdue / total_tasks * 100) if total_tasks else 0
    if total_tasks and overdue >= max(5, total_tasks * OVERDUE_CRITICAL / 100):
        task_status = 'red'
    elif total_tasks and overdue >= max(3, total_tasks * OVERDUE_WARN / 100):
        task_status = 'yellow'
    else:
        task_status = 'green'

    red_n = sum(1 for b in scope_list if b.status == 'red')
    yellow_n = sum(1 for b in scope_list if b.status == 'yellow')
    br_status = 'red' if red_n else 'yellow' if yellow_n else 'green'

    avg_kpi = team.get('avg_kpi', 0)
    # kpi=0 у всех сотрудников значит «никто не заполнял», а не «команда ноль»:
    # нет сигнала — нет пожара, иначе вертолёт врёт на пустых данных.
    if avg_kpi <= 0:
        team_status, team_detail = 'green', 'KPI ще не задані'
    else:
        team_detail = f'Середній KPI {avg_kpi}'
        team_status = 'red' if avg_kpi < KPI_MIN - 10 \
            else 'yellow' if avg_kpi < KPI_MIN else 'green'

    dimensions = [
        _dim('finance', fin_status,
             f'Дохід {revenue_pct}% плану'
             + (f', витрати {expense_pct}% бюджету' if expense_pct < EXPENSE_OK_PCT else '')),
        _dim('tasks', task_status,
             f'{overdue} прострочених із {total_tasks}' if total_tasks else 'Завдань немає'),
        _dim('branches', br_status,
             ', '.join(filter(None, [
                 f'{red_n} {_ua_plural(red_n, ("червона", "червоні", "червоних"))}' if red_n else '',
                 f'{yellow_n} {_ua_plural(yellow_n, ("жовта", "жовті", "жовтих"))}' if yellow_n else '',
             ])) or 'Усі філії в нормі'),
        _dim('team', team_status, team_detail),
    ]

    # ── Пожары ──
    fires = []

    def add_fire(severity, dimension, title, detail, branch_id=None, pct=None):
        fires.append({'severity': severity, 'dimension': dimension,
                      'branch_id': branch_id, 'pct': pct,
                      'title': title, 'detail': detail})

    # Филиальные пожары идём от листьев к корням: узел пропускается, если
    # пожар уже найден глубже в его поддереве — отвечаем «где именно», а не
    # «где-то рядом».
    parent_of = {b.id: b.parent_id for b in scope_list}

    def depth(bid):
        d = 0
        while parent_of.get(bid) is not None:
            bid = parent_of[bid]
            d += 1
        return d

    covered_ancestors = set()
    for b in sorted(scope_list, key=lambda x: (-depth(x.id), x.name)):
        if b.status not in ('red', 'yellow') or b.id in covered_ancestors:
            continue
        severity = 'critical' if b.status == 'red' else 'warning'
        pct = per_branch_pct.get(b.id, 0)
        add_fire(severity, 'branches', f'{b.name}: дохід {pct}% від плану',
                 'Невиконання плану / простій' if severity == 'critical'
                 else 'Відхилення від плану',
                 branch_id=b.id, pct=pct)
        node = parent_of.get(b.id)
        while node is not None:
            covered_ancestors.add(node)
            node = parent_of.get(node)

    if fin_status != 'green':
        sev = 'critical' if revenue_pct < REVENUE_CRITICAL_PCT else 'warning'
        add_fire(sev, 'finance', f'Компанія: дохід {revenue_pct}% від плану',
                 'Сукупний недобір по компанії', pct=revenue_pct)
        if expense_pct < EXPENSE_OK_PCT:
            add_fire(sev, 'finance', 'Компанія: перевитрата бюджету',
                     'Витрати перевищили запланований бюджет')

    if task_status != 'green':
        add_fire('critical' if task_status == 'red' else 'warning',
                 'tasks', f'Прострочені завдання: {overdue}',
                 f'{overdue_ratio}% усіх завдань прострочено')

    if team_status != 'green':
        add_fire('critical' if team_status == 'red' else 'warning',
                 'team', f'Середній KPI команди: {avg_kpi}',
                 f'Нижче цільового рівня {KPI_MIN}')

    order = {'critical': 0, 'warning': 1}
    fires.sort(key=lambda f: (order[f['severity']],
                              f['pct'] if f['pct'] is not None else 999))
    fires = fires[:MAX_FIRES]

    # ── Вердикт + health score ──
    crit_n = sum(1 for f in fires if f['severity'] == 'critical')
    warn_n = len(fires) - crit_n
    vstatus = 'red' if crit_n else 'yellow' if warn_n else 'green'
    if vstatus == 'green':
        headline = 'Усе під контролем'
    else:
        bits = []
        if crit_n:
            bits.append(f'{crit_n} {_ua_plural(crit_n, ("пожежа", "пожежі", "пожеж"))}')
        if warn_n:
            bits.append(f'{warn_n} {_ua_plural(warn_n, ("попередження", "попередження", "попереджень"))}')
        headline = ', '.join(bits)

    # ── Здоровье филиалов для таблицы drill-down ──
    real_overdue = dict(
        Policy(request).tasks().filter(overdue_q()).filter(branch__isnull=False)
        .values('branch').annotate(n=Count('id'))
        .values_list('branch', 'n')
    )
    srank = {'red': 0, 'yellow': 1, 'green': 2}
    health_rows = []
    for b in scope_list:
        od = real_overdue.get(b.id,0)
        health_rows.append({
            'id': b.id, 'name': b.name, 'status': b.status,
            'pct': per_branch_pct.get(b.id, 0),
            'overdue': od, 'heads': b.employee_count,
        })
    health_rows.sort(key=lambda r: (srank[r['status']], r['pct']))

    return Response({
        'is_demo': True,
        'period': period,
        'verdict': {'status': vstatus, 'headline': headline,
                    'score': sum(_DIM_SCORE[d['status']] for d in dimensions)},
        'dimensions': dimensions,
        'fires': fires,
        'branches_health': health_rows,
    })


@api_view(['GET'])
def dashboard_activity(request):
    """Лента событий — сведённые вместе журналы задач, сотрудников и AI."""
    try:
        limit = min(int(request.GET.get('limit', 10)), 50)
    except ValueError:
        limit = 10

    events = []
    verb = {'create': 'створено', 'update': 'змінено', 'delete': 'видалено'}

    for log in TaskChangeLog.objects.filter(task_id__in=Policy(request).tasks().values('pk'))[:limit]:
        events.append({
            'icon': f'task_{log.action}',
            'text': f'Задачу «{log.task_title}» {verb.get(log.action, log.action)}',
            'time': log.changed_at,
        })
    for log in (EmployeeChangeLog.objects.all() if Policy(request).ceo else EmployeeChangeLog.objects.none())[:limit]:
        events.append({
            'icon': f'task_{log.action}',
            'text': f'Співробітника {log.employee_name} {verb.get(log.action, log.action)}',
            'time': log.changed_at,
        })

    events.sort(key=lambda e: e['time'], reverse=True)
    for e in events:
        e['time'] = e['time'].isoformat()
    return Response(events[:limit])
