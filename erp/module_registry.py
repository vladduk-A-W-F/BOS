"""Immutable server-owned composition metadata for the existing BoS writers.

This registry describes existing projections and forms. It never evaluates code,
queries arbitrary tables, creates a ledger, or grants permission to execute.
"""
from dataclasses import dataclass

from django.apps import apps
from django.conf import settings

from boss_project.policy import CEO_ACTIONS
from .network import TABLES
from .service import SCHEMAS


class RegistryConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    type: str = 'text'
    finance: bool = False


@dataclass(frozen=True)
class Model:
    id: str
    name: str
    django: str
    key: str
    label_field: str
    status_field: str | None
    columns: tuple
    relations: tuple = ()


@dataclass(frozen=True)
class Action:
    id: str
    name: str
    model: str
    ui_action: str
    presets: tuple = ()
    finance: bool = False


@dataclass(frozen=True)
class Module:
    id: str
    name: str
    depends: tuple
    models: tuple
    section: str
    sub: str


VIEWS = (
    ('control', 'list', 'Контроль'), ('flow', 'kanban', 'Потік'),
    ('network', 'map', 'Мережа'), ('focus', 'inbox', 'Фокус'),
)
MODELS = (
    Model('points', 'Робочі точки', 'erp.Location', 'id', 'name', None, (
        Column('code', 'Код'), Column('name', 'Точка'), Column('branch_name', 'Філія'),
        Column('kind', 'Тип'), Column('address', 'Адреса'), Column('lot_count', 'Партії', 'integer'),
        Column('coordinate_basis', 'Джерело координат'), Column('inventory_value', 'Запас', 'money', True))),
    Model('lots', 'Складські партії', 'erp.Lot', 'id', 'code', 'quality', (
        Column('code', 'Партія'), Column('item_name', 'Номенклатура'), Column('location_name', 'Точка'),
        Column('quantity', 'На складі', 'quantity'), Column('available', 'Доступно для операцій', 'quantity'),
        Column('quality', 'Якість', 'status'), Column('currency', 'Валюта'),
        Column('value', 'Вартість', 'money', True)), (('location_id', 'points'),)),
    Model('purchases', 'Постачання', 'erp.Purchase', 'id', 'code', 'effective_status', (
        Column('code', 'Замовлення'), Column('process', 'Процес'), Column('supplier_name', 'Постачальник'),
        Column('item_name', 'Номенклатура'), Column('location_name', 'Приймання'),
        Column('open_quantity', 'Ще прийняти', 'quantity'), Column('effective_status', 'Стан', 'status'),
        Column('due_date', 'Строк', 'date'), Column('currency', 'Валюта'),
        Column('price', 'Ціна', 'money', True)), (('destination_id', 'points'), ('production_id', 'jobs'))),
    Model('orders', 'Продажі', 'erp.SalesOrder', 'id', 'code', 'status', (
        Column('code', 'Замовлення'), Column('process', 'Процес'), Column('customer_name', 'Клієнт'),
        Column('location_name', 'Виконання'), Column('status', 'Стан', 'status'),
        Column('open_line_count', 'Рядки до виконання', 'integer'), Column('due_date', 'Строк', 'date'),
        Column('currency', 'Валюта')), (('fulfillment_location_id', 'points'),)),
    Model('jobs', 'Виробництво', 'erp.Production', 'id', 'code', 'status', (
        Column('code', 'Робота'), Column('item_name', 'Виріб'), Column('location_name', 'Точка'),
        Column('quantity', 'План', 'quantity'), Column('produced', 'Випуск', 'quantity'),
        Column('status', 'Стан', 'status'), Column('due_date', 'Строк', 'date'),
        Column('currency', 'Валюта')), (('location_id', 'points'),)),
    Model('transfers', 'Переміщення', 'erp.StockTransfer', 'id', 'code', 'status', (
        Column('code', 'Переміщення'), Column('item_name', 'Номенклатура'),
        Column('source_location_name', 'Звідки'), Column('destination_name', 'Куди'),
        Column('quantity', 'Кількість', 'quantity'), Column('status', 'Стан', 'status'),
        Column('due_date', 'Строк', 'date'), Column('currency', 'Валюта'),
        Column('total_cost', 'Вартість', 'money', True)),
        (('source_lot_id', 'lots'), ('received_lot_id', 'lots'),
         ('source_location_id', 'points'), ('destination_id', 'points'))),
    Model('invoices', 'Рахунки', 'operations.Invoice', 'invoice_id', 'code', None, (
        Column('code', 'Рахунок'), Column('customer_name', 'Клієнт'), Column('due_date', 'Строк', 'date'),
        Column('receivable', 'Залишилось сплатити', 'money', True), Column('retained', 'Утримано', 'money', True),
        Column('collectible', 'Доступно до оплати', 'money', True), Column('currency', 'Валюта')),
        (('order_id', 'orders'),)),
    Model('retentions', 'Утримання', 'erp.PaymentRetention', 'id', 'code', 'status', (
        Column('code', 'Утримання'), Column('invoice_id', 'Рахунок', 'integer'),
        Column('amount', 'Сума', 'money', True), Column('status', 'Стан', 'status'),
        Column('reason', 'Підстава'), Column('created_at', 'Створено', 'datetime'),
        Column('released_at', 'Знято', 'datetime'), Column('currency', 'Валюта')),
        (('invoice_id', 'invoices'),)),
)
# Existing network Policy exposes invoice identity/customer/date to all roles;
# only retention records and monetary columns are private to the CEO.
FINANCE_MODELS = frozenset({'retentions'})
ACTIONS = (
    Action('erp_location', 'Нова точка', 'points', 'location'),
    Action('erp_location_update', 'Реквізити точки', 'points', 'location_update', (('location_id', 'id'),)),
    Action('erp_opening', 'Початкова партія', 'lots', 'opening', finance=True),
    Action('erp_quality', 'Перевірити якість', 'lots', 'quality', (('lot_id', 'id'),)),
    Action('erp_attach', 'Додати документ партії', 'lots', 'attach', (('lot_id', 'id'),)),
    Action('erp_transfer_dispatch', 'Відправити переміщення', 'lots', 'transfer_dispatch', (('lot_id', 'id'),)),
    Action('erp_purchase', 'Нова закупівля', 'purchases', 'purchase'),
    Action('erp_receive', 'Прийняти поставку', 'purchases', 'receive', (('purchase_id', 'id'), ('location_id', 'destination_id'))),
    Action('erp_postpone', 'Змінити строк поставки', 'purchases', 'postpone', (('purchase_id', 'id'),)),
    Action('erp_purchase_network', 'Реквізити постачання', 'purchases', 'purchase_network', (('purchase_id', 'id'),)),
    Action('erp_order', 'Новий продаж', 'orders', 'order'),
    Action('erp_confirm_order', 'Підтвердити продаж', 'orders', 'confirm_order', (('order_id', 'id'),)),
    Action('erp_order_network', 'Реквізити продажу', 'orders', 'order_network', (('order_id', 'id'),)),
    Action('erp_invoice', 'Рахунок за відвантаження', 'orders', 'invoice', (('order_id', 'id'),), True),
    Action('erp_job', 'Нова виробнича робота', 'jobs', 'job'),
    Action('erp_start', 'Розпочати виробництво', 'jobs', 'start', (('production_id', 'id'),)),
    Action('erp_operator', 'Записати виконання', 'jobs', 'operator', (('production_id', 'id'),)),
    Action('erp_finish', 'Випустити партію', 'jobs', 'finish', (('production_id', 'id'), ('location_id', 'location_id'))),
    Action('erp_postpone_job', 'Змінити строк роботи', 'jobs', 'postpone_job', (('production_id', 'id'),)),
    Action('erp_transfer_receive', 'Прийняти переміщення', 'transfers', 'transfer_receive', (('transfer_id', 'id'),)),
    Action('erp_payment', 'Зареєструвати оплату', 'invoices', 'payment', (('invoice_id', 'invoice_id'),), True),
    Action('erp_hold_payment', 'Встановити утримання', 'invoices', 'hold_payment', (('invoice_id', 'invoice_id'),), True),
    Action('erp_release_payment', 'Зняти утримання', 'retentions', 'release_payment', (('retention_id', 'id'),), True),
)
MODULES = (
    Module('operations', 'Операції', (), ('points',), 'erp', 'network'),
    Module('warehouse', 'Склад', ('operations',), ('lots', 'transfers'), 'erp', 'stock'),
    Module('procurement', 'Постачання', ('operations', 'warehouse'), ('purchases',), 'erp', 'purchase'),
    Module('sales', 'Продажі', ('operations', 'warehouse'), ('orders',), 'erp', 'sales'),
    Module('production', 'Виробництво', ('operations', 'warehouse'), ('jobs',), 'erp', 'production'),
    Module('settlements', 'Розрахунки', ('operations', 'sales'), ('invoices', 'retentions'), 'erp', 'network'),
)


def validated_selection():
    """Reject unknown/broken server metadata before publishing any descriptor."""
    model_ids = {model.id for model in MODELS}
    module_ids = {module.id for module in MODULES}
    action_ids = {action.id for action in ACTIONS}
    if (len(model_ids) != len(MODELS) or len(module_ids) != len(MODULES)
            or len(action_ids) != len(ACTIONS) or model_ids != set(TABLES)):
        raise RegistryConfigurationError('Duplicate or unknown registry identity')
    for model in MODELS:
        try:
            apps.get_model(model.django)
        except (ValueError, LookupError) as exc:
            raise RegistryConfigurationError('Unknown Django model') from exc
        columns = {column.key for column in model.columns}
        if (len(columns) != len(model.columns) or model.label_field not in columns
                or (model.status_field and model.status_field not in columns)
                or any(target not in model_ids for _, target in model.relations)
                or any(column.type not in {'text', 'integer', 'quantity', 'money', 'date', 'datetime', 'status'} for column in model.columns)
                or any(column.type == 'money' and not column.finance for column in model.columns)):
            raise RegistryConfigurationError('Invalid model descriptor')
    for action in ACTIONS:
        if (action.model not in model_ids or action.id != 'erp_' + action.ui_action
                or action.ui_action not in SCHEMAS):
            raise RegistryConfigurationError('Unknown writer action')
        accepted = set(' '.join(SCHEMAS[action.ui_action]).split())
        if any(parameter not in accepted for parameter, _ in action.presets):
            raise RegistryConfigurationError('Preset is not accepted by writer')
    owners = [model for module in MODULES for model in module.models]
    if len(owners) != len(set(owners)) or set(owners) != model_ids:
        raise RegistryConfigurationError('Every projected model requires one module owner')
    for module in MODULES:
        if module.id in module.depends or not set(module.depends).issubset(module_ids):
            raise RegistryConfigurationError('Unknown module dependency')
    config = getattr(settings, 'BOS_ENABLED_MODULES', tuple(module.id for module in MODULES))
    if (not isinstance(config, (tuple, list)) or not config or any(type(value) is not str for value in config)
            or len(set(config)) != len(config) or not set(config).issubset(module_ids)):
        raise RegistryConfigurationError('Unknown module composition')
    selected = set(config)
    if 'operations' not in selected or any(not set(module.depends).issubset(selected) for module in MODULES if module.id in selected):
        raise RegistryConfigurationError('Missing module dependency')
    # Also reject a source-level dependency cycle, not just a missing setting.
    done = set()
    while done != selected:
        ready = {module.id for module in MODULES if module.id in selected and set(module.depends).issubset(done)}
        if not ready - done:
            raise RegistryConfigurationError('Module dependency cycle')
        done |= ready
    return selected


def build(policy):
    selected = validated_selection()
    capability = policy.capabilities()
    visible_modules = [module for module in MODULES if module.id in selected]
    visible_ids = {model for module in visible_modules for model in module.models}
    if not policy.ceo:
        visible_ids -= FINANCE_MODELS
    allowed_actions = [action for action in ACTIONS if action.model in visible_ids and capability['write']
        and (policy.ceo or (not action.finance and action.id not in CEO_ACTIONS))]
    actions = [{'id': action.id, 'name': action.name, 'model': action.model,
        'ui_action': action.ui_action, 'presets': dict(action.presets),
        'preview_endpoint': '/api/erp/preview/', 'confirm_endpoint': '/api/operations/confirm/',
        'authorization': 'rechecked_by_existing_writer'} for action in allowed_actions]
    models = []
    for model in MODELS:
        if model.id not in visible_ids:
            continue
        models.append({'id': model.id, 'name': model.name,
            'source': {'rows': 'rows.' + model.id, 'django': model.django},
            'key': model.key, 'label_field': model.label_field, 'status_field': model.status_field,
            'columns': [{'key': column.key, 'label': column.label, 'type': column.type, 'finance': column.finance}
                for column in model.columns if policy.ceo or not column.finance],
            'relations': [{'field': field, 'target': target} for field, target in model.relations if target in visible_ids],
            'actions': [action.id for action in allowed_actions if action.model == model.id],
            'views': [view[0] for view in VIEWS], 'default_view': 'control'})
    modules = [{'id': module.id, 'name': module.name, 'depends': list(module.depends),
        'models': [model for model in module.models if model in visible_ids],
        'views': [view[0] for view in VIEWS],
        'actions': [action.id for action in allowed_actions if action.model in module.models],
        'menus': [{'id': module.id, 'name': module.name, 'section': module.section, 'sub': module.sub}],
        'permissions': {'write': capability['write'], 'finance': policy.ceo}, 'automations': []}
        for module in visible_modules]
    return {'schema': 'bos.modules.v1',
        'data': {'schema': 'bos.network.v1', 'endpoint': '/api/erp/network/',
                 'export_endpoint': '/api/erp/network/export/' if capability['export_workspace'] else None},
        'views': [{'id': key, 'type': kind, 'name': name} for key, kind, name in VIEWS],
        'modules': modules, 'models': models, 'actions': actions, 'automations': [],
        'permissions': {'role': policy.role, 'write': capability['write'], 'finance': policy.ceo,
                        'export': capability['export_workspace']},
        'configuration': {'mode': 'server_owned', 'mutable': False, 'scope': 'navigation_composition'}}
