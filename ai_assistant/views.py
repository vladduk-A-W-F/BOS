from boss_project.policy import Policy
from boss_project.archive import archive_records
import base64
from datetime import date
from io import BytesIO

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction, models
from django.utils import timezone
from django.db.models import Sum
from django.db.models.deletion import ProtectedError
from django.core.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from anthropic import Anthropic

import logging
# __name__ = 'ai_assistant.views' — matches the 'ai_assistant' logger in settings.LOGGING
logger = logging.getLogger(__name__)

from .models import ChatMessage, TaskChangeLog, ClaudeUsageLog, EmployeeChangeLog
from .serializers import ChatMessageSerializer
from tasks.models import Task
from employees.models import Employee
from finance.models import Counterparty, Contract, Transaction, Salary
from finance.commands import save_salary, save_transaction
from boss_project.archive import restore_record


def task_to_dict(task):
    """Serialize Task to dict for storing in TaskChangeLog.
    JSONField can't store date objects directly — we serialize to ISO string."""
    return {
        'title': task.title,
        'priority': task.priority,
        'status': task.status,
        'assignee': task.assignee,
        # Bulletproof: если deadline уже строка (свежий create() до refresh_from_db) — возвращаем как есть.
        # Если date-объект — .isoformat(). Если None — None.
        'deadline': (task.deadline.isoformat()
                     if hasattr(task.deadline, 'isoformat')
                     else task.deadline) if task.deadline else None,
        'category': task.category,
    }


def employee_to_dict(employee):
    """Serialize Employee to dict for storing in EmployeeChangeLog.
    Date birthday → ISO string for JSONField storage."""
    return {
        'full_name': employee.full_name,
        'role': employee.role,
        'department': employee.department,
        'birthday': employee.birthday.isoformat() if employee.birthday else None,
        'kpi': employee.kpi,
        'phone': employee.phone,
        'email': employee.email,
    }


# Anthropic Tool Use — descriptions of tools Claude can call.
# Each tool has a name, a description (Claude reads this to decide WHEN to use it),
# and an input_schema (JSON Schema describing the arguments).
TOOLS = [
    {
        "name": "create_task",
        "description": "Створити нову задачу в системі. Використовуй коли користувач просить додати/створити задачу.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Назва задачі"},
                "priority": {"type": "string", "enum": ["high", "medium", "low", "none"], "description": "Пріоритет, за замовчуванням medium. 'none' = без пріоритету"},
                "status": {"type": "string", "enum": ["active", "process", "done", "overdue"], "description": "Статус, за замовчуванням active"},
                "assignee": {"type": "string", "description": "ПІБ виконавця, наприклад 'Іванов О.'"},
                "deadline": {"type": "string", "description": "Дата у форматі YYYY-MM-DD"},
                "category": {"type": "string", "description": "Категорія задачі"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "update_task",
        "description": "Змінити існуючу задачу за її id. Можна оновити будь-яке поле.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "id задачі"},
                "title": {"type": "string"},
                "priority": {"type": "string", "enum": ["high", "medium", "low", "none"], "description": "'none' = прибрати пріоритет"},
                "status": {"type": "string", "enum": ["active", "process", "done", "overdue"]},
                "assignee": {"type": "string"},
                "deadline": {"type": "string"},
                "category": {"type": "string"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "delete_task",
        "description": "Видалити задачу за її id. УВАГА: перед викликом ОБОВ'ЯЗКОВО запитай у користувача підтвердження в чаті ('Ви впевнені, що хочете видалити задачу #N?') і чекай явного 'так' в наступному повідомленні.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "id задачі для видалення"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "list_tasks",
        "description": "Знайти задачі за фільтрами. Корисно коли потрібен конкретний підбір задач за критеріями.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "process", "done", "overdue"]},
                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                "assignee": {"type": "string"},
            },
        },
    },
    {
        "name": "undo_last_change",
        "description": "Скасувати ОСТАННЄ виконане змінення задачі (відновлює попередній стан). Використовуй коли користувач каже 'скасуй', 'відміни', 'верни', 'undo', 'поверни попередній стан', або просить виправити твою помилку.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "create_employee",
        "description": "Створити нового співробітника. Використовуй коли користувач просить додати/створити співробітника.",
        "input_schema": {
            "type": "object",
            "properties": {
                "full_name": {"type": "string", "description": "Повне імʼя, наприклад 'Олексій Іванов'"},
                "role": {"type": "string", "description": "Посада, наприклад 'Заступник директора'"},
                "department": {"type": "string", "description": "Відділ: Управління, Фінанси, IT, HR, Операції"},
                "birthday": {"type": "string", "description": "День народження YYYY-MM-DD (необовʼязково)"},
                "kpi": {"type": "integer", "description": "KPI 0-100, за замовчуванням 0"},
                "phone": {"type": "string"},
                "email": {"type": "string"},
            },
            "required": ["full_name"],
        },
    },
    {
        "name": "update_employee",
        "description": "Змінити існуючого співробітника за id. Можна оновити будь-яке поле.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "integer", "description": "id співробітника"},
                "full_name": {"type": "string"},
                "role": {"type": "string"},
                "department": {"type": "string"},
                "birthday": {"type": "string"},
                "kpi": {"type": "integer"},
                "phone": {"type": "string"},
                "email": {"type": "string"},
            },
            "required": ["employee_id"],
        },
    },
    {
        "name": "delete_employee",
        "description": "Видалити співробітника за id. УВАГА: перед викликом ОБОВʼЯЗКОВО запитай у користувача підтвердження в чаті і чекай явного 'так'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "integer"},
            },
            "required": ["employee_id"],
        },
    },
    {
        "name": "list_employees",
        "description": "Знайти співробітників за фільтрами (відділ).",
        "input_schema": {
            "type": "object",
            "properties": {
                "department": {"type": "string"},
            },
        },
    },
    # === FINANCE TOOLS ===
    {
        "name": "create_counterparty",
        "description": "Створити нового контрагента (клієнт/постачальник/послуги).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "enum": ["supplier", "customer", "service", "utility", "other"]},
                "phone": {"type": "string"},
                "email": {"type": "string"},
                "edrpou": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_counterparties",
        "description": "Показати всіх контрагентів компанії.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "delete_counterparty",
        "description": "Видалити контрагента за id. УВАГА: спочатку запитай підтвердження в чаті і чекай 'так'.",
        "input_schema": {
            "type": "object",
            "properties": {"counterparty_id": {"type": "integer"}},
            "required": ["counterparty_id"],
        },
    },
    {
        "name": "create_transaction",
        "description": "Створити фінансову транзакцію (дохід або витрату).",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["in", "out"]},
                "amount": {"type": "number"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "description": {"type": "string"},
                "category": {"type": "string", "enum": ["salary", "supplier", "customer", "utility", "rent", "tax", "other"]},
                "counterparty_id": {"type": "integer"},
            },
            "required": ["direction", "amount", "date", "description"],
        },
    },
    {
        "name": "list_transactions",
        "description": "Показати транзакції за період.",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["in", "out"]},
                "limit": {"type": "integer", "description": "макс. кількість, за замовчуванням 20"},
            },
        },
    },
    {
        "name": "create_contract",
        "description": "Створити договір з контрагентом.",
        "input_schema": {
            "type": "object",
            "properties": {
                "number": {"type": "string"},
                "name": {"type": "string"},
                "counterparty_id": {"type": "integer"},
                "amount": {"type": "number"},
                "category": {"type": "string", "enum": ["services", "goods", "utility", "rent", "supply", "other"]},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
            },
            "required": ["number", "name", "counterparty_id"],
        },
    },
    {
        "name": "list_contracts",
        "description": "Показати договори компанії.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_salary",
        "description": "Нарахувати зарплату співробітнику за місяць.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "integer"},
                "amount": {"type": "number"},
                "period_year": {"type": "integer"},
                "period_month": {"type": "integer"},
            },
            "required": ["employee_id", "amount", "period_year", "period_month"],
        },
    },
    {
        "name": "pay_salary",
        "description": "Позначити нараховану зарплату як виплачену (створює транзакцію-витрату).",
        "input_schema": {
            "type": "object",
            "properties": {
                "salary_id": {"type": "integer"},
                "payment_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["salary_id"],
        },
    },
    {
        "name": "list_salaries",
        "description": "Показати зарплати за період.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "paid", "cancelled"]},
            },
        },
    },
]


# ── Tool handlers — one function per tool, dispatched by _TOOL_HANDLERS ──────


def _create_task(args):
    args.setdefault("priority", "medium")
    args.setdefault("status", "active")
    if args.get("priority") == "none":
        args["priority"] = None
    task = Task.objects.create(**args)
    task.refresh_from_db()
    TaskChangeLog.objects.create(
        action='create', task_id=task.id, task_title=task.title,
        after=task_to_dict(task),
    )
    return (
        f"Створено задачу #{task.id}: '{task.title}' "
        f"(статус: {task.status}, виконавець: {task.assignee or 'не призначено'})"
    )


def _update_task(args):
    task_id = args.pop("task_id")
    task = Task.objects.get(id=task_id)
    before = task_to_dict(task)
    if args.get("priority") == "none":
        args["priority"] = None
    if args.get("status") == "done" and "priority" not in args:
        args["priority"] = None
    for field, value in args.items():
        setattr(task, field, value)
    task.save()
    after = task_to_dict(task)
    TaskChangeLog.objects.create(
        action='update', task_id=task.id, task_title=task.title,
        before=before, after=after,
    )
    return f"Оновлено задачу #{task.id}: '{task.title}' (статус: {task.status})"


def _delete_task(args):
    task_id = args["task_id"]
    task = Task.objects.get(id=task_id)
    before = task_to_dict(task)
    title = task.title
    TaskChangeLog.objects.create(
        action='delete', task_id=task_id, task_title=title, before=before,
    )
    task.delete()
    return f"Видалено задачу #{task_id}: '{title}'"


def _list_tasks(args):
    qs = Task.objects.filter(**args)
    if not qs.exists():
        return "Немає задач."
    return "\n".join(
        f"#{t.id} [{t.status[0]}] {t.title} | {t.assignee or '—'} | {t.priority or '—'}"
        for t in qs
    )


def _create_employee(args):
    args.setdefault("kpi", 0)
    if args.get("birthday"):
        args["birthday"] = date.fromisoformat(args["birthday"])
    employee = Employee.objects.create(**args)
    EmployeeChangeLog.objects.create(
        action='create', employee_id=employee.id,
        employee_name=employee.full_name, after=employee_to_dict(employee),
    )
    logger.info(f"Created employee #{employee.id}: {employee.full_name}")
    return (
        f"Створено співробітника #{employee.id}: '{employee.full_name}' "
        f"(посада: {employee.role or 'не вказана'}, відділ: {employee.department or 'не вказаний'})"
    )


def _update_employee(args):
    employee_id = args.pop("employee_id")
    employee = Employee.objects.get(id=employee_id)
    before = employee_to_dict(employee)
    if args.get("birthday"):
        args["birthday"] = date.fromisoformat(args["birthday"])
    for field, value in args.items():
        setattr(employee, field, value)
    employee.save()
    after = employee_to_dict(employee)
    EmployeeChangeLog.objects.create(
        action='update', employee_id=employee.id,
        employee_name=employee.full_name, before=before, after=after,
    )
    logger.info(f"Updated employee #{employee.id}: {employee.full_name}")
    return f"Оновлено співробітника #{employee.id}: '{employee.full_name}' (посада: {employee.role}, відділ: {employee.department})"


@transaction.atomic
def _delete_employee(args):
    employee_id = args["employee_id"]
    employee = Employee.objects.get(id=employee_id)
    if employee.archived_at is not None:
        return f'Працівника #{employee_id} вже архівовано. Історію збережено.'
    before = employee_to_dict(employee)
    name_copy = employee.full_name
    EmployeeChangeLog.objects.create(
        action='delete', employee_id=employee_id,
        employee_name=name_copy, before=before,
    )
    employee.delete()
    logger.info(f"Archived employee #{employee_id}")
    return f"Архівовано працівника #{employee_id}: '{name_copy}'. Історію збережено."


def _list_employees(args):
    qs = Employee.objects.filter(**args)
    if not qs.exists():
        return "Немає співробітників."
    return "\n".join(
        f"#{e.id} {e.full_name} | {e.role or '—'} | {e.department or '—'} | KPI:{e.kpi}%"
        for e in qs
    )


def _undo_last_change(args):
    last_task = TaskChangeLog.objects.first()
    last_emp = EmployeeChangeLog.objects.filter(undone_at__isnull=True).first()

    if not last_task and not last_emp:
        return "Немає що скасовувати — історія змін порожня."

    if last_task and (not last_emp or last_task.changed_at > last_emp.changed_at):
        last = last_task
        entity_type = 'task'
    else:
        last = last_emp
        entity_type = 'employee'

    if entity_type == 'task':
        if last.action == 'create':
            try:
                Task.objects.get(id=last.task_id).delete()
                last.delete()
                return f"Скасовано створення задачі '{last.task_title}' — видалено з системи."
            except Task.DoesNotExist:
                last.delete()
                return f"Задача '{last.task_title}' вже не існує."

        elif last.action == 'update':
            try:
                task = Task.objects.get(id=last.task_id)
                before = dict(last.before or {})
                if before.get('deadline'):
                    before['deadline'] = date.fromisoformat(before['deadline'])
                for field, value in before.items():
                    setattr(task, field, value)
                task.save()
                last.delete()
                return f"Скасовано зміну задачі #{task.id} '{task.title}' — повернуто попередній стан."
            except Task.DoesNotExist:
                last.delete()
                return f"Задача '{last.task_title}' вже не існує."

        elif last.action == 'delete':
            before = dict(last.before or {})
            if before.get('deadline'):
                before['deadline'] = date.fromisoformat(before['deadline'])
            task = Task.objects.create(**before)
            last.delete()
            return f"Відновлено задачу '{task.title}' (новий id #{task.id})."

    elif entity_type == 'employee':
        with transaction.atomic():
            # Repeated undo must not create a replacement ID or remove the log.
            EmployeeChangeLog.objects.filter(pk=last.pk).update(undone_at=models.F('undone_at'))
            last.refresh_from_db()
            if last.undone_at is not None:
                return 'Цю зміну вже скасовано.'
            employee = Employee.objects.filter(pk=last.employee_id).first()
            if employee is None:
                return 'Історичний запис відсутній. Потрібна звірка; новий ID не створено.'
            if last.action == 'create':
                employee.delete()
                result = f'Створення працівника #{employee.pk} скасовано архівуванням. Історію збережено.'
            elif last.action == 'delete':
                restore_record(employee)
                result = f'Відновлено працівника #{employee.pk} зі збереженням ID та історії.'
            elif last.action == 'update':
                before = dict(last.before or {})
                for field, value in before.items():
                    if field in employee_to_dict(employee):
                        setattr(employee, field, date.fromisoformat(value) if field == 'birthday' and value else value)
                employee.save(update_fields=list(before))
                result = f'Скасовано зміну працівника #{employee.pk}.'
            else:
                return 'Цю зміну неможливо скасувати автоматично.'
            last.undone_at = timezone.now()
            last.save(update_fields=['undone_at'])
            return result


def _create_counterparty(args):
    args.setdefault("type", "other")
    cp = Counterparty.objects.create(**args)
    logger.info(f"Created counterparty #{cp.id}: {cp.name}")
    return f"Створено контрагента #{cp.id}: '{cp.name}' ({cp.get_type_display()})."


def _list_counterparties(args):
    qs = Counterparty.objects.with_totals().filter(is_active=True)
    if not qs.exists():
        return "Немає контрагентів."
    return "\n".join(
        f"#{c.id} {c.name} ({c.get_type_display()}) д/к {c.total_debit}/{c.total_credit}"
        for c in qs
    )


def _delete_counterparty(args):
    cp = Counterparty.objects.get(id=args["counterparty_id"])
    title = cp.name
    cp.delete()
    logger.info(f"Deleted counterparty #{args['counterparty_id']}: {title}")
    return f"Видалено контрагента '{title}'."


def _create_transaction(args):
    operation_id = args.pop('operation_id', None)
    cp_id = args.pop("counterparty_id", None)
    if cp_id:
        args["counterparty"] = Counterparty.objects.get(id=cp_id)
    args.setdefault("category", "other")
    tx = save_transaction(changes=args, operation_id=operation_id)
    logger.info(f"Created transaction #{tx.id}: {tx.direction} {tx.amount}")
    arrow = 'дохід' if tx.direction == 'in' else 'витрата'
    return f"Створено транзакцію #{tx.id}: {arrow} {tx.amount} {tx.currency} — '{tx.description}'."


def _list_transactions(args):
    limit = args.get("limit", 20)
    qs = Transaction.objects.all()
    if args.get("direction"):
        qs = qs.filter(direction=args["direction"])
    qs = qs[:limit]
    if not qs:
        return "Немає транзакцій."
    return "\n".join(
        f"#{t.id} {t.date} {t.direction} {t.amount}{t.currency} — {t.description}"
        for t in qs
    )


def _create_contract(args):
    cp = Counterparty.objects.get(id=args.pop("counterparty_id"))
    args["counterparty"] = cp
    args.setdefault("category", "other")
    ct = Contract.objects.create(**args)
    logger.info(f"Created contract #{ct.id}: {ct.number}")
    return f"Створено договір #{ct.id} №{ct.number} '{ct.name}' з {cp.name} на суму {ct.amount} {ct.currency}."


def _list_contracts(args):
    qs = Contract.objects.select_related('counterparty').all()
    if not qs.exists():
        return "Немає договорів."
    return "\n".join(
        f"#{c.id} №{c.number} {c.name} | {c.counterparty.name} | {c.amount}{c.currency} [{c.status}]"
        for c in qs
    )


def _create_salary(args):
    operation_id = args.pop('operation_id', None)
    emp = Employee.objects.get(id=args.pop("employee_id"))
    sal = save_salary(changes={'employee': emp, **args}, operation_id=operation_id)
    logger.info(f"Created salary #{sal.id} for {emp.full_name}")
    return (
        f"Нараховано зарплату #{sal.id}: {emp.full_name} за "
        f"{sal.period_year}-{sal.period_month:02d} — {sal.amount} {sal.currency} (статус: очікує виплати)."
    )


def _pay_salary(args):
    salary = Salary.objects.get(id=args["salary_id"])
    salary, tx = salary.mark_paid(args.get("payment_date"))
    logger.info(f"Paid salary #{salary.id} → tx #{tx.id}")
    return f"Зарплата #{salary.id} виплачена. Створена транзакція #{tx.id} на {salary.amount} {salary.currency}."


def _list_salaries(args):
    qs = Salary.objects.select_related('employee').all()
    if args.get("status"):
        qs = qs.filter(status=args["status"])
    if not qs:
        return "Немає зарплат."
    return "\n".join(
        f"#{s.id} {s.employee.full_name} {s.period_year}-{s.period_month:02d}: {s.amount}{s.currency} [{s.status}]"
        for s in qs
    )


# ── Dispatch table: maps tool name → handler function ────────────────────────

_TOOL_HANDLERS = {
    'create_task': _create_task,
    'update_task': _update_task,
    'delete_task': _delete_task,
    'list_tasks': _list_tasks,
    'create_employee': _create_employee,
    'update_employee': _update_employee,
    'delete_employee': _delete_employee,
    'list_employees': _list_employees,
    'undo_last_change': _undo_last_change,
    'create_counterparty': _create_counterparty,
    'list_counterparties': _list_counterparties,
    'delete_counterparty': _delete_counterparty,
    'create_transaction': _create_transaction,
    'list_transactions': _list_transactions,
    'create_contract': _create_contract,
    'list_contracts': _list_contracts,
    'create_salary': _create_salary,
    'pay_salary': _pay_salary,
    'list_salaries': _list_salaries,
}


def execute_tool(name, args, *, operation_id=None):
    """Run a tool call and return a human-readable string for Claude to read.
    Dispatches to individual handler functions via _TOOL_HANDLERS.
    Logs every create/update/delete to audit logs for real undo support."""
    handler = _TOOL_HANDLERS.get(name)
    if not handler:
        return f"Помилка: невідомий інструмент '{name}'"
    try:
        if operation_id is not None and name in ('create_transaction', 'create_salary'):
            args = {**args, 'operation_id': operation_id}
        logger.info(f"Tool called: {name} with args {args}")
        return handler(args)
    except Task.DoesNotExist:
        logger.warning(f"Tool {name} failed: task {args.get('task_id')} not found")
        return f"Помилка: задачі з id {args.get('task_id')} не існує."
    except Employee.DoesNotExist:
        logger.warning(f"Tool {name} failed: employee {args.get('employee_id')} not found")
        return f"Помилка: співробітника з id {args.get('employee_id')} не існує."
    except Counterparty.DoesNotExist:
        logger.warning(f"Tool {name} failed: counterparty {args.get('counterparty_id')} not found")
        return f"Помилка: контрагента з id {args.get('counterparty_id')} не існує."
    except Contract.DoesNotExist:
        return "Помилка: договір не знайдено."
    except Salary.DoesNotExist:
        logger.warning(f"Tool {name} failed: salary {args.get('salary_id')} not found")
        return f"Помилка: нарахування зарплати з id {args.get('salary_id')} не існує."
    except ValueError as e:
        logger.warning(f"Tool {name} validation error: {e}")
        return f"Помилка: невірний формат даних — {str(e)}"
    except (TypeError, KeyError) as e:
        logger.warning(f"Tool {name} bad arguments: {e}")
        return f"Помилка: відсутній або невірний аргумент — {str(e)}"
    except ProtectedError:
        return 'Дію не виконано: запис є джерелом історії. Пов’язані дані збережено.'
    except ValidationError as e:
        return 'Дію не виконано: ' + '; '.join(e.messages)
    except IntegrityError as e:
        logger.warning(f"Tool {name} DB integrity error: {e}")
        return "Помилка: порушення цілісності даних (можливо, дублювання унікального поля)."
    except Exception as e:
        logger.error(f"Tool {name} crashed with unexpected error: {e}", exc_info=True)
        return f"Несподівана помилка виконання {name}: {str(e)}"


# Keywords that signal user wants to undo the last action.
# When detected in the CURRENT message — we force Claude to call undo_last_change via tool_choice.
# This bulletproofs the most critical operation against text-only hallucinations.
UNDO_TRIGGERS = [
    'скасуй', 'скасув',
    'відміни', 'відмін',
    'верни попередн', 'поверни попередн', 'поверни назад',
    'undo', 'виправ помилку',
    # Multi-undo triggers — same forcing logic applies, prompt rule 7 teaches Claude
    # to call undo_last_change multiple times in one turn for these.
    'ще одну', 'ще раз', 'ще дв', 'ще тр',  # "ще дві", "ще трі"
    'далі скасуй', 'продовжуй скасув',
    'скасуй усі', 'скасуй всі',
    'скасуй останн',  # "скасуй останні N"
    'попередні зміни', 'попередню зміну',
]


# Words that NEGATE an undo trigger. If any of these appears within 3 words BEFORE
# a trigger word — we treat the message as "do not undo", not as "undo".
# Examples that should NOT trigger undo:
#   "не скасуй це"
#   "ні, не треба скасовувати"
#   "не варто скасовувати останнє"
NEGATION_WORDS = ['не', 'ні', 'не треба', 'не варто', "не потрібно"]


def is_undo_intent(message_lower):
    """Detect undo intent in user's message, ignoring triggers that are negated.
    Returns True only if there's a non-negated undo trigger somewhere in the message."""
    for trigger in UNDO_TRIGGERS:
        idx = message_lower.find(trigger)
        if idx == -1:
            continue
        # Get up to 3 words immediately before the trigger
        before_text = message_lower[:idx].rstrip()
        words_before = before_text.split()[-3:]
        words_str = ' '.join(words_before)
        # If any negation word appears in those 3 words — this trigger is negated, skip
        if any(neg in words_str for neg in NEGATION_WORDS):
            continue
        # Non-negated trigger found
        return True
    return False


# ── TOKEN OPTIMIZATION: Compressed rules + shared helpers ─────────────────────

# Compressed rules — ~40% shorter than original, same semantics.
# Original was ~1200 tokens; this is ~700 tokens. Saves ~500 tokens per request.
RULES_PROMPT = """ФОРМАТ: markdown (**жирний**), списки через дефіс, без заголовків (#). 3-6 рядків.

ПРІОРИТЕТ: high/medium/low або відсутній. priority='none' прибирає. status='done' → priority=None.

ПРАВИЛА:
1. "покажи"/"які"/"скільки"=запит → list_tasks або текст. "створи"/"видали"/"зміни"=команда → tool. Сумнів→покажи.
2. update_task однієї—без підтвердження. Декількох—запитай "Підтверджуєш?".
3. delete_task/delete_employee/delete_counterparty—ЗАВЖДИ з підтвердженням.
4. undo_last_change: "скасуй"/"відміни"/"верни". Можна кілька разів підряд. Масовий undo—викликай потрібну кількість разів, результат одним повідомленням.
5. Масові дії (>1) — попередь про специфіку відміни перед виконанням.
6. Після tool—коротко повідом результат.
7. НІКОЛИ не пиши "Створено"/"Видалено" без реального виклику tool. Без tool→"Не зміг" або "Готовий після підтвердження".
8. Співробітники: create_employee, update_employee, delete_employee (з підтвердженням), list_employees. undo_last_change працює і для задач, і для співробітників."""


def _is_data_query(message_lower):
    """Detect if user message requires business data context.
    Returns True for queries about tasks, employees, finance, etc.
    Returns False for simple greetings, general questions — saves ~2000 tokens."""
    return any(kw in message_lower for kw in [
        'задач', 'завдан', 'дедлайн', 'пріоритет', 'виконав', 'статус',
        'співробітник', 'відділ', 'kpi', 'день народж', 'посада',
        'контрагент', 'договір', 'транзакці', 'зарплат', 'нараху',
        'покажи', 'які задач', 'скільки', 'хто', 'що робить',
        'бюджет', 'дохід', 'витрат', 'фінанс', 'банк', 'рахунок',
        'створи', 'додай', 'зміни', 'видали', 'онови',
        'скасуй', 'відміни', 'верни', 'undo',
    ])


def _build_tasks_context(request):
    from tasks.queries import active,project_list
    tasks=project_list(active(Policy(request).tasks()).exclude(status='done')[:100])
    return '\n'.join(f"- #{t['id']} [{t['status']}] {t['title']} | {t['assignee_name']} | {t['deadline']} | Прострочено: {t['is_overdue']}" for t in tasks) or 'Немає.'


def _build_employees_context(request):
    Policy(request)
    employees=Employee.objects.all()[:100]
    return '\n'.join(f"- #{e.id} {e.full_name} | {e.role} | {e.department}" for e in employees) or 'Немає.'


def _build_finance_context(request):
    p=Policy(request)
    counterparties=Counterparty.objects.filter(is_active=True)[:20]
    cp_text='\n'.join(f'- #{c.id} {c.name} ({c.get_type_display()})' for c in counterparties) or 'Немає.'
    contracts=p.contracts().filter(status='active')[:20]
    ct_text='\n'.join(f'- #{c.id} №{c.number} {c.name}'+(f', {c.amount} {c.currency}' if p.ceo or p.role=='manager' else '') for c in contracts) or 'Немає.'
    result=f'Контрагенти:\n{cp_text}\nДоговори:\n{ct_text}'
    if p.ceo:
        today=date.today()
        for row in p.transactions().filter(date__year=today.year,date__month=today.month).values('currency','direction').annotate(total=Sum('amount')).order_by('currency','direction'):
            result+=f"\n{row['currency']} · {row['direction']}: {row['total']}"
    return result


def _build_system_prompt(tasks_text, employees_text, finance_text="", extra_instructions=""):
    """Shared system prompt builder — conditional context + compressed rules."""
    parts = ["Ти асистент керівника компанії. Відповідай українською, коротко по суті.\n"]
    if extra_instructions:
        parts.append(extra_instructions + "\n")
    if tasks_text:
        parts.append(f"Задачі:\n{tasks_text}\n")
    if employees_text:
        parts.append(f"Співробітники:\n{employees_text}\n")
    if finance_text:
        parts.append(finance_text + "\n")
    parts.append(RULES_PROMPT)
    return "\n".join(parts)


def _trim_history(history, max_chars=8000):
    """Keep recent messages within a character budget (~4 chars/token).
    Always keeps the last user message. Drops oldest first."""
    if not history:
        return []
    result = []
    total = 0
    for msg in reversed(history):
        msg_len = len(msg.content)
        if total + msg_len > max_chars and len(result) >= 2:
            break
        result.append(msg)
        total += msg_len
    result.reverse()
    return result


def _deduplicate_history(messages):
    """Remove consecutive messages with near-identical content (Jaccard >0.8)."""
    if len(messages) < 2:
        return messages
    deduped = [messages[0]]
    for msg in messages[1:]:
        prev = deduped[-1]
        if msg.role == prev.role and len(msg.content) > 20:
            words_a = set(msg.content.lower().split())
            words_b = set(prev.content.lower().split())
            if words_a and words_b:
                jaccard = len(words_a & words_b) / len(words_a | words_b)
                if jaccard > 0.8:
                    continue
        deduped.append(msg)
    return deduped


def _run_tool_loop(client, system_prompt, messages, tools=TOOLS,
                   max_iterations=10, tool_choice=None, max_tokens=1024):
    """Shared tool-use loop with Anthropic prompt caching.
    system_prompt is sent as a cacheable content block — on iterations 2+,
    Anthropic charges only 10% for the cached prefix."""
    total_in = total_out = 0
    ai_response = None
    for iteration in range(max_iterations):
        create_kwargs = {
            "model": "claude-sonnet-4-5",
            "max_tokens": max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "tools": tools,
            "messages": messages,
        }
        if iteration == 0 and tool_choice:
            create_kwargs["tool_choice"] = tool_choice

        logger.info(f"Calling Claude (iteration {iteration})")
        ai_response = client.messages.create(**create_kwargs)
        total_in += ai_response.usage.input_tokens
        total_out += ai_response.usage.output_tokens

        if ai_response.stop_reason == "end_turn":
            break

        messages.append({"role": "assistant", "content": ai_response.content})
        tool_results = []
        for block in ai_response.content:
            if block.type == "tool_use":
                result = execute_tool(block.name, dict(block.input), operation_id=block.id)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result),
                })
        # Ни tool_use, ни end_turn — продолжать цикл бессмысленно (пустой tool_results
        # отправлять назад нельзя — API отвергнет user-сообщение без tool_result).
        if not tool_results:
            break
        messages.append({"role": "user", "content": tool_results})

    reply_parts = [b.text for b in ai_response.content if b.type == "text"]
    reply = "\n".join(reply_parts) if reply_parts else "Готово."
    return reply, total_in, total_out, iteration + 1


class ChatHistoryView(generics.ListAPIView):
    """Own readable history; clearing archives it without deleting source files."""
    serializer_class = ChatMessageSerializer

    def get_queryset(self):
        return Policy(self.request).history()

    def delete(self, request, *args, **kwargs):
        p=Policy(request)
        if p.role=='observer':
            return Response({'error':'Спостерігач не може архівувати історію.'},status=403)
        count,_=archive_records(p.history(),actor=request.user)
        return Response({'archived_messages':count,'preserved_files':True})


class ChatView(APIView):
    def post(self, request):
        message = request.data.get('message', '').strip()
        if not message:
            return Response({"error": "message is required"}, status=400)

        logger.info(f"Chat request received: '{message[:80]}'")
        user_msg = ChatMessage.objects.create(user=request.user,visibility_role=Policy(request).role,role='user', content=message)

        try:
            # Load history — trim to token budget + deduplicate
            history = list(
                Policy(request).history().prefetch_related('attached_file')
                .order_by('-created_at')[:20]
            )[::-1]
            history = _trim_history(history)
            history = _deduplicate_history(history)

            # Conditional context — skip DB queries for simple questions (saves ~2000 tokens)
            message_lower = message.lower()
            needs_data = _is_data_query(message_lower)

            if needs_data:
                tasks_text = _build_tasks_context(request)
                employees_text = _build_employees_context(request)
                finance_text = _build_finance_context(request)
            else:
                tasks_text = employees_text = finance_text = ""

            system_prompt = _build_system_prompt(tasks_text, employees_text, finance_text)

            messages = _build_messages_with_last_file(history)
            client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            should_force_undo = is_undo_intent(message_lower)

            tool_choice = (
                {"type": "tool", "name": "undo_last_change"}
                if should_force_undo else None
            )

            reply, total_in, total_out, num_calls = _run_tool_loop(
                client, system_prompt, messages,
                tool_choice=tool_choice, max_tokens=1024,
            )
        except Exception as e:
            # AI-вызов не удался — убираем из истории только что созданное user-сообщение,
            # чтобы история не расходилась с реальными ответами бота.
            user_msg.delete()
            logger.exception(f"Chat failed: '{message[:80]}'")
            return Response({"error": f"Не вдалося звернутись до AI: {e}"}, status=500)

        assistant_msg = ChatMessage.objects.create(user=request.user,visibility_role=Policy(request).role,role='assistant', content=reply)
        ClaudeUsageLog.objects.create(
            endpoint='chat', model='claude-sonnet-4-5',
            input_tokens=total_in, output_tokens=total_out,
            chat_message=assistant_msg,
        )
        logger.info(f"Chat usage: {total_in}in+{total_out}out tokens ({num_calls} call(s))")
        return Response({"reply": reply})


def _first_text(content_blocks):
    """Вытащить первый текстовый блок из ответа Claude (content = [blocks]).

    content[0] безопасно только когда модель вернула ровно один text-блок;
    при tool_use/разнобое блоков первый блок может быть не текстом — ищем по типам.
    """
    for block in content_blocks or []:
        if getattr(block, 'type', None) == 'text':
            return block.text
    return ''


class MeetingProtocolView(APIView):
    """POST /api/meeting/protocol/ — text in, protocol+tasks out."""
    def post(self, request):
        text = request.data.get('text', '').strip()
        if not text:
            return Response({"error": "text is required"}, status=400)

        logger.info(f"Meeting protocol request, text length {len(text)}")
        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": (
                    "Ти — секретар керівника. Отримуєш текст наради та повертаєш: "
                    "1) Короткий протокол (дата, присутні, рішення), "
                    "2) Список доручень '• [відповідальний] — [завдання] — [дедлайн]'. "
                    "Тільки українською. Використовуй markdown."
                ),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": f"Текст наради:\n{text}\n\nСтвори протокол та доручення."
            }],
        )
        result = _first_text(response.content)
        ClaudeUsageLog.objects.create(
            endpoint='meeting', model='claude-sonnet-4-5',
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        logger.info(f"Meeting usage: {response.usage.input_tokens}in+{response.usage.output_tokens}out tokens")
        return Response({"result": result})


class DictateProcessView(APIView):
    """POST /api/dictate/process/ — text + style + lang in, processed text out."""
    def post(self, request):
        text = request.data.get('text', '').strip()
        style = request.data.get('style', 'official')
        lang = request.data.get('lang', 'uk')

        if not text:
            return Response({"error": "text is required"}, status=400)

        logger.info(f"Dictate request, style={style}, lang={lang}, text length {len(text)}")
        style_map = {
            'official': 'офіційно-діловий',
            'professional': 'професійний',
            'brief': 'стислий та чіткий',
        }
        lang_map = {'uk': 'українською', 'ru': 'російською', 'en': 'англійською'}

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=768,
            system=[{
                "type": "text",
                "text": "Ти — літературний редактор та перекладач. Обробляєш голосові нотатки.",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Перетвори на {style_map.get(style, 'офіційно-діловий')} стиль "
                    f"та подай {lang_map.get(lang, 'українською')}. Тільки результат.\n\n{text}"
                ),
            }],
        )
        result = _first_text(response.content)
        ClaudeUsageLog.objects.create(
            endpoint='dictate', model='claude-sonnet-4-5',
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        logger.info(f"Dictate usage: {response.usage.input_tokens}in+{response.usage.output_tokens}out tokens")
        return Response({"result": result})


from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse


def _parse_docx(file_bytes):
    """Извлекаем текст из DOCX: параграфы + таблицы (markdown-разметкой)."""
    from docx import Document
    doc = Document(BytesIO(file_bytes))
    parts = []
    # Параграфы
    for p in doc.paragraphs:
        if p.text.strip():
            parts.append(p.text)
    # Таблицы — каждая строка как markdown row
    for table in doc.tables:
        parts.append('')  # пустая строка-разделитель
        for row in table.rows:
            cells = [c.text.strip().replace('|', '\\|') for c in row.cells]
            parts.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(parts)


def _parse_xlsx(file_bytes):
    """Извлекаем все листы XLSX как markdown-таблицы."""
    from openpyxl import load_workbook
    wb = load_workbook(BytesIO(file_bytes), data_only=True)  # data_only=True → формулы как значения
    parts = []
    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        parts.append(f'### Аркуш: {sheet_name}\n')
        for row in sheet.iter_rows(values_only=True):
            # Пропускаем полностью пустые строки
            if all(cell is None or str(cell).strip() == '' for cell in row):
                continue
            cells = ['' if c is None else str(c).strip().replace('|', '\\|') for c in row]
            parts.append('| ' + ' | '.join(cells) + ' |')
        parts.append('')  # разделитель между листами
    return '\n'.join(parts)


def _build_file_blocks_from_chatfile(chatfile):
    """Восстановить content blocks для Claude из сохранённого ChatFile.
    PDF читается с диска и заново кодируется в base64 (нативная поддержка Anthropic).
    DOCX/XLSX — берём уже распарсенный текст из parsed_text (не парсим повторно).
    """
    if chatfile.mime_type == 'application/pdf':
        with chatfile.file.open('rb') as f:
            b64 = base64.standard_b64encode(f.read()).decode('utf-8')
        return [{
            'type': 'document',
            'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': b64},
        }]
    # DOCX / XLSX — parsed_text уже markdown
    return [{
        'type': 'text',
        'text': f'=== Зміст файлу {chatfile.original_name} ===\n\n{chatfile.parsed_text}\n\n=== Кінець файлу ===',
    }]


def _build_messages_with_last_file(history):
    """Собрать messages для Claude API. Подцепляем ТОЛЬКО последний файл в истории —
    это компромисс между удобством (можно спрашивать follow-up) и экономией токенов
    (не таскаем все прошлые PDF в каждом запросе).

    history — список ChatMessage, отсортированный по возрастанию времени.
    """
    # Найти id последнего user-сообщения с файлом
    last_file_msg_id = None
    for msg in reversed(history):
        if msg.role == 'user' and hasattr(msg, 'attached_file'):
            last_file_msg_id = msg.id
            break

    messages = []
    for msg in history:
        if msg.id == last_file_msg_id:
            # Разворачиваем в content blocks: файл + текст сообщения
            file_blocks = _build_file_blocks_from_chatfile(msg.attached_file)
            messages.append({
                'role': 'user',
                'content': file_blocks + [{'type': 'text', 'text': msg.content}],
            })
        else:
            messages.append({'role': msg.role, 'content': msg.content})
    return messages


@csrf_exempt
def chat_with_file(request):
    """POST /api/chat/file/ (multipart) — message with attached file.
    Uses shared helpers for context building + tool loop with prompt caching."""
    if request.method != 'POST':
        return JsonResponse({'error': 'method not allowed'}, status=405)

    uploaded = request.FILES.get('file')
    user_message = request.POST.get('message', '').strip()

    if not uploaded:
        return JsonResponse({'error': 'no file provided'}, status=400)
    if not user_message:
        user_message = 'Опиши, що в цьому файлі.'

    MAX_BYTES = 30 * 1024 * 1024
    if uploaded.size > MAX_BYTES:
        return JsonResponse({
            'error': f'Файл занадто великий ({uploaded.size//1024//1024} MB). Ліміт {MAX_BYTES//1024//1024} MB.'
        }, status=400)

    filename = uploaded.name
    name_lower = filename.lower()
    file_bytes = uploaded.read()

    if name_lower.endswith('.pdf') and not file_bytes[:5] == b'%PDF-':
        return JsonResponse({'error': 'Файл не є дійсним PDF (відсутній PDF-хедер).'}, status=400)
    if name_lower.endswith(('.docx', '.xlsx', '.xlsm')) and not file_bytes[:4] == b'PK\x03\x04':
        return JsonResponse({'error': 'Файл не є дійсним DOCX/XLSX (очікувався ZIP-архів).'}, status=400)

    parsed_text = ''
    try:
        if name_lower.endswith('.pdf'):
            mime_type = 'application/pdf'
        elif name_lower.endswith('.docx'):
            mime_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            parsed_text = _parse_docx(file_bytes)
        elif name_lower.endswith(('.xlsx', '.xlsm')):
            mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            parsed_text = _parse_xlsx(file_bytes)
        else:
            return JsonResponse({
                'error': f'Непідтримуваний тип файлу: {filename}. Підтримуються: PDF, DOCX, XLSX.'
            }, status=400)
    except Exception as e:
        logger.exception('Помилка парсингу файлу')
        return JsonResponse({'error': f'Не вдалося прочитати файл: {e}'}, status=500)

    from django.core.files.base import ContentFile
    from .models import ChatFile

    user_msg = ChatMessage.objects.create(
        user=request.user,visibility_role=Policy(request).role,
        role='user',
        content=f'[Файл: {filename}] {user_message}',
    )
    ChatFile.objects.create(
        chat_message=user_msg,
        original_name=filename,
        file=ContentFile(file_bytes, name=filename),
        mime_type=mime_type,
        size=uploaded.size,
        parsed_text=parsed_text,
    )

    # History with trimming + dedup
    history = list(
        Policy(request).history().prefetch_related('attached_file')
        .order_by('-created_at')[:20]
    )[::-1]
    history = _trim_history(history)
    history = _deduplicate_history(history)
    messages = _build_messages_with_last_file(history)

    # Shared context builders (cached)
    tasks_text = _build_tasks_context(request)
    employees_text = _build_employees_context(request)

    file_instructions = (
        "До повідомлення прикріплено документ — проаналізуй зміст. "
        "Якщо є задачі/доручення/дедлайни — запропонуй створити через create_task (з підтвердженням)."
    )
    system_prompt = _build_system_prompt(
        tasks_text, employees_text,
        extra_instructions=file_instructions,
    )

    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        reply, total_in, total_out, num_calls = _run_tool_loop(
            client, system_prompt, messages, max_tokens=1536,
        )
    except Exception as e:
        # Сообщение с файлом НЕ удаляем — файл уже сохранён на диск, оставляем
        # пользователю возможность повторить запрос (follow-up) из истории.
        logger.exception("chat_with_file: AI call failed")
        return JsonResponse({'error': f'Не вдалося звернутись до AI: {e}'}, status=500)

    assistant_msg = ChatMessage.objects.create(user=request.user,visibility_role=Policy(request).role,role='assistant', content=reply)
    ClaudeUsageLog.objects.create(
        endpoint='chat', model='claude-sonnet-4-5',
        input_tokens=total_in, output_tokens=total_out,
        chat_message=assistant_msg,
    )
    logger.info(f'chat_with_file: {total_in}in+{total_out}out tokens ({num_calls} call(s))')
    return JsonResponse({'reply': reply})
