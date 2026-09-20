"""Server-side role, object and field policy shared by API and assistant."""
from django.contrib.auth import get_user_model
from django.db.models import Q
from .identity import actor


CEO_ACTIONS = {'erp_location_update','erp_order_network','erp_purchase_network','erp_hold_payment','erp_release_payment','erp_statement_import','erp_statement_reconcile','erp_credit_invoice','erp_reverse_credit','erp_confirm_supplier_claim','erp_import_batch', 'erp_opening', 'erp_payment', 'erp_apply_change', 'erp_resolve_job', 'erp_adjust'}
DIRECTORY = {'id', 'full_name', 'role', 'department', 'branch', 'branch_name', 'archived_at'}
TRANSACTION_FIELDS = {'id', 'date', 'direction', 'category', 'currency', 'contract', 'counterparty', 'branch', 'archived_at'}


class Policy:
    def __init__(self, request):
        self.request = request
        self.actor = actor(request)
        self.role = self.actor.role
        # Never reuse request.user's permission cache after a role change.
        self.user = get_user_model().objects.get(pk=self.actor.user_id)

    @property
    def ceo(self):
        return self.role == 'ceo'

    def has(self, codename):
        return self.user.has_perm('operations.' + codename)

    def access_revision(self):
        import hashlib
        value = repr((self.actor.user_id, self.actor.employee_id, self.role,
                      sorted(self.user.get_all_permissions())))
        return hashlib.sha256(value.encode()).hexdigest()

    def capabilities(self):
        return {'read_scenarios': True, 'external_llm': False, 'ocr': False,
                'controlled_tasks': self.role != 'observer', 'write': self.role != 'observer',
                'finance': self.ceo, 'hr_private': self.ceo,
                'view_documents': self.ceo or self.has('view_document'),
                'download_documents': self.has('download_document'),
                'export_workspace': self.role != 'observer' and self.has('export_workspace')}

    def require(self, codename):
        if not self.has(codename):
            raise PermissionError('Немає дозволу на цю дію.')

    def require_export(self):
        if self.role == 'observer':
            raise PermissionError('Експорт недоступний для цієї ролі.')
        self.require('export_workspace')

    def documents(self):
        from operations.models import Document
        rows = Document.objects.defer('content')
        if self.ceo:
            return rows
        if not self.has('view_document'):
            return rows.none()
        levels = ['operational', 'management'] if self.role == 'manager' else ['operational']
        from finance.models import StatementImport
        from finance.statement_csv import marker
        private=set(StatementImport.objects.values_list('document__code',flat=True))
        private.update(d.code for d in rows if marker(d))
        return rows.filter(access_level__in=levels).exclude(code__in=private)

    def document(self, pk):
        return self.documents().get(pk=pk)

    def contracts(self):
        from operations.models import Document
        from finance.models import Contract
        if self.ceo:
            return Contract.objects.all()
        if not self.has('view_document'):
            return Contract.objects.none()
        hidden = Document.objects.exclude(pk__in=self.documents().values('pk')).exclude(contract_id=None)
        return Contract.objects.exclude(pk__in=hidden.values('contract_id'))

    def requests(self):
        from operations.models import ProcurementRequest
        return ProcurementRequest.objects.filter(document_id__in=self.documents().values('pk'))

    def quotes(self):
        from operations.models import SupplierQuote
        return SupplierQuote.objects.filter(request_id__in=self.requests().values('pk'), document_id__in=self.documents().values('pk'))

    def tasks(self):
        from tasks.queries import visible_tasks
        return visible_tasks(self)

    def transactions(self):
        from finance.models import Transaction
        rows = Transaction.objects.all()
        if self.ceo:
            return rows
        if self.role == 'observer':
            return rows.none()
        return rows.exclude(Q(category='salary') | Q(salary_record__isnull=False) | Q(statement_line__isnull=False))

    def history(self):
        from ai_assistant.models import ChatMessage
        return ChatMessage.objects.filter(user_id=self.actor.user_id, visibility_role=self.role, archived_at=None)

    def queryset(self, model):
        if self.ceo:
            return model.objects.all()
        if model._meta.label_lower in {'finance.statementimport','finance.statementline','finance.statementallocation'}:return model.objects.none()
        special = {'operations.document': self.documents, 'operations.procurementrequest': self.requests,
                   'operations.supplierquote': self.quotes, 'tasks.task': self.tasks,
                   'finance.contract': self.contracts, 'finance.transaction': self.transactions}
        if model._meta.label_lower in special:
            return special[model._meta.label_lower]()
        if model._meta.app_label=='erp':
            from erp.models import OrderCancellation,CancellationRelease,GoodsReturn,SupplierClaim,InvoiceAdjustment,InvoiceAdjustmentLine,Movement,Reservation
            from erp.models import StockTransfer,PaymentRetention,Lot
            if model in (InvoiceAdjustment,InvoiceAdjustmentLine,PaymentRetention):return model.objects.none()
            if model is StockTransfer:
                visible=self.queryset(Lot);docs=set(self.documents().values_list('pk',flat=True))
                allowed=[r.pk for r in model.objects.filter(source_lot__in=visible).filter(Q(received_lot__isnull=True)|Q(received_lot__in=visible))
                    if isinstance(r.documents,dict) and all(type(pk) is int and pk in docs for pk in r.documents.values())]
                return model.objects.filter(pk__in=allowed)
            if model is OrderCancellation:
                ids=self.erp_ids();return model.objects.filter(Q(line_id__in=ids['line_id'])|Q(purchase_id__in=ids['purchase_id']))
            if model is CancellationRelease:return model.objects.filter(cancellation__in=self.queryset(OrderCancellation),reservation__in=self.queryset(Reservation))
            if model is GoodsReturn:
                rows=model.objects.filter(source__in=self.queryset(Movement),result__in=self.queryset(Movement))
                docs=set(self.documents().values_list('pk',flat=True));allowed=[]
                for row in rows:
                    source=row.source_snapshot
                    historical=source.get('documents') if isinstance(source,dict) else None
                    if isinstance(historical,dict) and all(type(pk) is int and pk in docs for pk in historical.values()):allowed.append(row.pk)
                return rows.filter(pk__in=allowed)
            # Operational claim metadata follows the physical return. Monetary
            # confirmation fields/document are CEO-only in every projection.
            if model is SupplierClaim:return model.objects.filter(returned_goods__in=self.queryset(GoodsReturn))
        ids = self.erp_ids()
        names = {'item': 'item_id', 'lot': 'lot_id', 'salesorder': 'order_id', 'salesline': 'line_id',
                 'production': 'production_id', 'purchase': 'purchase_id', 'changeorder': 'change_id'}
        if model._meta.model_name in names:
            return model.objects.filter(pk__in=ids[names[model._meta.model_name]])
        qs = model.objects.all()
        for field in model._meta.fields:
            if field.attname in ids:
                qs = qs.filter(Q(**{field.attname + '__in': ids[field.attname]}) | Q(**{field.attname + '__isnull': True}))
        return qs

    def filter_queryset(self, rows):
        return rows if self.ceo else rows.filter(pk__in=self.queryset(rows.model).values('pk'))

    def erp_ids(self):
        from erp.models import Item, Lot, SalesOrder, SalesLine, Production, Purchase, ChangeOrder
        if hasattr(self, '_erp_ids'):
            return self._erp_ids
        docs = set(self.documents().values_list('pk', flat=True))
        item_rows = list(Item.objects.all())
        items = {x.pk for x in item_rows if x.document_id is None or x.document_id in docs}
        while True:
            complete = {x.pk for x in item_rows if x.pk in items and all(b.get('item_id') in items for b in x.bom)}
            if complete == items:
                break
            items = complete
        lots = {x.pk for x in Lot.objects.all() if x.item_id in items and all(v in docs for v in x.documents.values())}
        orders = {x.pk for x in SalesOrder.objects.all() if all(v in items for v in x.lines.values_list('item_id', flat=True))}
        lines = set(SalesLine.objects.filter(order_id__in=orders, item_id__in=items).values_list('pk', flat=True))
        jobs = {x.pk for x in Production.objects.all() if x.item_id in items and (x.line_id is None or x.line_id in lines) and all(b.get('item_id') in items for b in x.bom)}
        requests = set(self.requests().values_list('pk', flat=True))
        quotes = set(self.quotes().values_list('pk', flat=True))
        from erp.procurement import source_document_ids
        purchases = {x.pk for x in Purchase.objects.all() if x.item_id in items
            and (x.request_id is None or x.request_id in requests)
            and (x.quote_id is None or x.quote_id in quotes)
            and (x.production_id is None or x.production_id in jobs)
            and source_document_ids(x.approval_snapshot) is not None
            and source_document_ids(x.approval_snapshot).issubset(docs)}
        changes = set(ChangeOrder.objects.filter(item_id__in=items, document_id__in=docs).values_list('pk', flat=True))
        self._erp_ids = {'document_id': docs, 'item_id': items, 'lot_id': lots, 'order_id': orders, 'line_id': lines, 'production_id': jobs, 'purchase_id': purchases, 'change_id': changes, 'request_id': requests, 'quote_id': quotes}
        return self._erp_ids

    def check_reference(self, name, value):
        from django.core.exceptions import ObjectDoesNotExist
        if value is None:
            return
        if name in ('transfer_id','retention_id'):
            from erp.models import StockTransfer,PaymentRetention
            self.queryset(StockTransfer if name=='transfer_id' else PaymentRetention).get(pk=value)
        elif name in ('receipt_id','shipment_id','movement_id','source_movement_id'):
            from erp.models import Movement
            obj=self.queryset(Movement).get(pk=value)
            expected={'receipt_id':'receipt','shipment_id':'shipment'}.get(name)
            if expected and obj.kind!=expected:raise ObjectDoesNotExist('Запис недоступний.')
        elif name in ('return_id','goods_return_id','claim_id','supplier_claim_id','parent_claim_id','credit_id','invoice_adjustment_id','reversed_credit_id','cancellation_id'):
            from erp.models import GoodsReturn,SupplierClaim,InvoiceAdjustment,OrderCancellation
            model=GoodsReturn if name in ('return_id','goods_return_id') else SupplierClaim if name in ('claim_id','supplier_claim_id','parent_claim_id') else OrderCancellation if name=='cancellation_id' else InvoiceAdjustment
            self.queryset(model).get(pk=value)
        elif name=='source_document_id':self.document(value)
        elif name == 'task_id':
            self.tasks().get(pk=value)
        elif name == 'contract_id':
            self.contracts().get(pk=value)
        elif name == 'request_code':
            self.requests().get(code=value)
        elif name in self.erp_ids() and value not in self.erp_ids()[name]:
            raise ObjectDoesNotExist('Запис недоступний.')
        elif name == 'reservation_id':
            from erp.models import Reservation
            obj = Reservation.objects.get(pk=value)
            for field in ('lot_id', 'line_id', 'production_id'):
                self.check_reference(field, getattr(obj, field))
        elif name == 'invoice_id':
            from erp.models import InvoiceLink
            for order_id in InvoiceLink.objects.filter(invoice_id=value).values_list('order_id', flat=True):
                self.check_reference('order_id', order_id)

    def check_payload(self, data):
        if self.ceo:
            return
        for key, value in data.items():
            if key == 'documents' and isinstance(value, dict):
                for pk in value.values():
                    self.document(pk)
            elif isinstance(value, dict):
                self.check_payload(value)
            elif isinstance(value, list):
                for row in value:
                    if isinstance(row, dict):
                        self.check_payload(row)
            elif key.endswith('_id') or key == 'request_code':
                self.check_reference(key, value)

    def action(self, payload):
        if self.role == 'observer' or (not self.ceo and payload.get('action') in CEO_ACTIONS):
            raise PermissionError('Ця дія недоступна для вашої ролі.')
        self.check_payload(payload)
        # These two fields attest to the person who actually did the work.
        for field in ('inspector_id', 'operator_id'):
            if field in payload and not self.ceo and payload[field] != self.actor.employee_id:
                raise PermissionError('Вкажіть власний пов’язаний обліковий запис виконавця.')


def fields_for(request, kind, names):
    p = Policy(request)
    if p.ceo:
        return set(names)
    if kind == 'employee':
        return DIRECTORY
    if kind == 'transaction':
        return TRANSACTION_FIELDS
    if kind == 'counterparty':
        return set(names) - {'total_debit', 'total_credit', 'balance', 'notes'} if p.role == 'manager' else {'id', 'name', 'type', 'is_active'}
    if kind == 'contract':
        return set(names) - {'notes'} if p.role == 'manager' else {'id', 'number', 'name', 'counterparty', 'counterparty_name', 'category', 'status', 'start_date', 'end_date'}
    return set(names)


class ScopedSerializerMixin:
    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request is not None:
            p = Policy(request)
            allowed = fields_for(request, self.Meta.model._meta.model_name, fields)
            fields = {k: v for k, v in fields.items() if k in allowed}
            if 'contract' in fields and hasattr(fields['contract'], 'queryset'):
                fields['contract'].queryset = p.contracts()
        return fields

    def to_representation(self, instance):
        result = super().to_representation(instance)
        request = self.context.get('request')
        if request is not None and self.Meta.model._meta.model_name == 'transaction':
            p = Policy(request)
            if not p.ceo and result.get('contract') and not p.contracts().filter(pk=result['contract']).exists():
                result['contract'] = None
        return result
