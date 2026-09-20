from django.db import models
from django.utils import timezone
from django.db.models import Q

class Item(models.Model):
    code=models.CharField(max_length=60,unique=True)
    name=models.CharField(max_length=200)
    unit=models.CharField(max_length=20,default='шт.')
    kind=models.CharField(max_length=20,default='product')
    method=models.CharField(max_length=20,default='buy')
    revision=models.CharField(max_length=40,default='A')
    document=models.ForeignKey('operations.Document',null=True,blank=True,on_delete=models.PROTECT)
    material=models.CharField(max_length=200,blank=True)
    external_codes=models.JSONField(default=dict)
    required_documents=models.JSONField(default=list)
    bom=models.JSONField(default=list)
    routing=models.JSONField(default=list)
    minimum=models.DecimalField(max_digits=15,decimal_places=3,default=0)
    lead_days=models.PositiveIntegerField(default=7)
    planned_cost=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    currency=models.CharField(max_length=3,default='UAH')

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(('currency__in', ('EUR', 'USD', 'UAH'))), name='erp_item_currency'),
        ]

class Location(models.Model):
    branch=models.ForeignKey('branches.Branch',null=True,blank=True,on_delete=models.PROTECT)
    address=models.CharField(max_length=300,blank=True,default='')
    lat=models.DecimalField(max_digits=9,decimal_places=6,null=True,blank=True)
    lng=models.DecimalField(max_digits=9,decimal_places=6,null=True,blank=True)
    code=models.CharField(max_length=60,unique=True)
    name=models.CharField(max_length=200)
    kind=models.CharField(max_length=20,default='warehouse')
    supplier=models.ForeignKey('finance.Counterparty',null=True,blank=True,on_delete=models.PROTECT)

class Lot(models.Model):
    code=models.CharField(max_length=60,unique=True)
    item=models.ForeignKey(Item,on_delete=models.PROTECT)
    location=models.ForeignKey(Location,on_delete=models.PROTECT)
    revision=models.CharField(max_length=40)
    quantity=models.DecimalField(max_digits=15,decimal_places=3,default=0)
    quality=models.CharField(max_length=20,default='pending')
    unit_cost=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    currency=models.CharField(max_length=3,default='UAH')
    documents=models.JSONField(default=dict)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(quantity__gte=0),name='erp_nonnegative_lot')]
        constraints += [
            models.CheckConstraint(condition=models.Q(('unit_cost__gte', 0)), name='erp_lot_unit_cost'),
            models.CheckConstraint(condition=models.Q(('currency__in', ('EUR', 'USD', 'UAH'))), name='erp_lot_currency'),
        ]

class SalesOrder(models.Model):
    fulfillment_location=models.ForeignKey(Location,null=True,blank=True,on_delete=models.PROTECT)
    destination_country=models.CharField(max_length=2,blank=True,default='')
    code=models.CharField(max_length=60,unique=True)
    customer=models.ForeignKey('finance.Counterparty',on_delete=models.PROTECT)
    owner=models.ForeignKey('employees.Employee',on_delete=models.PROTECT)
    due_date=models.DateField()
    currency=models.CharField(max_length=3,default='UAH')
    status=models.CharField(max_length=20,default='quote')
    notes=models.TextField(blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(('currency__in', ('EUR', 'USD', 'UAH'))), name='erp_salesorder_currency'),
        ]

class SalesLine(models.Model):
    order=models.ForeignKey(SalesOrder,on_delete=models.PROTECT,related_name='lines')
    item=models.ForeignKey(Item,on_delete=models.PROTECT)
    revision=models.CharField(max_length=40)
    quantity=models.DecimalField(max_digits=15,decimal_places=3)
    price=models.DecimalField(max_digits=15,decimal_places=2)
    shipped=models.DecimalField(max_digits=15,decimal_places=3,default=0)
    invoiced=models.DecimalField(max_digits=15,decimal_places=3,default=0)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(quantity__gt=0)&Q(shipped__gte=0)&Q(shipped__lte=models.F('quantity')),name='erp_line_quantity')]
        constraints += [
            models.CheckConstraint(condition=models.Q(('invoiced__gte', 0), ('invoiced__lte', models.F('shipped'))), name='erp_line_invoiced'),
            models.CheckConstraint(condition=models.Q(('price__gte', 0)), name='erp_line_price'),
        ]

class Production(models.Model):
    code=models.CharField(max_length=60,unique=True)
    line=models.ForeignKey(SalesLine,null=True,blank=True,on_delete=models.PROTECT)
    item=models.ForeignKey(Item,on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=15,decimal_places=3)
    produced=models.DecimalField(max_digits=15,decimal_places=3,default=0)
    revision=models.CharField(max_length=40)
    bom=models.JSONField(default=list)
    routing=models.JSONField(default=list)
    location=models.ForeignKey(Location,on_delete=models.PROTECT)
    owner=models.ForeignKey('employees.Employee',on_delete=models.PROTECT)
    due_date=models.DateField()
    status=models.CharField(max_length=20,default='planned')
    needs_review=models.BooleanField(default=False)
    planned_cost=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    actual_cost=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    currency=models.CharField(max_length=3,default='UAH')

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(('produced__gte', 0), ('produced__lte', models.F('quantity')), ('quantity__gt', 0)), name='erp_production_quantity'),
            models.CheckConstraint(condition=models.Q(('actual_cost__gte', 0), ('planned_cost__gte', 0)), name='erp_production_costs'),
            models.CheckConstraint(condition=models.Q(('currency__in', ('EUR', 'USD', 'UAH'))), name='erp_production_currency'),
        ]

class Reservation(models.Model):
    lot=models.ForeignKey(Lot,on_delete=models.PROTECT,related_name='reservations')
    line=models.ForeignKey(SalesLine,null=True,blank=True,on_delete=models.PROTECT,related_name='reservations')
    production=models.ForeignKey(Production,null=True,blank=True,on_delete=models.PROTECT,related_name='reservations')
    quantity=models.DecimalField(max_digits=15,decimal_places=3)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(quantity__gte=0),name='erp_nonnegative_reserve'),models.CheckConstraint(condition=(Q(line__isnull=False)&Q(production__isnull=True))|(Q(line__isnull=True)&Q(production__isnull=False)),name='erp_reservation_target')]

class Purchase(models.Model):
    created_at=models.DateTimeField(null=True,default=timezone.now,editable=False)
    destination=models.ForeignKey(Location,null=True,blank=True,on_delete=models.PROTECT)
    origin_country=models.CharField(max_length=2,blank=True,default='')
    code=models.CharField(max_length=60,unique=True)
    item=models.ForeignKey(Item,on_delete=models.PROTECT)
    supplier=models.ForeignKey('finance.Counterparty',on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=15,decimal_places=3)
    received=models.DecimalField(max_digits=15,decimal_places=3,default=0)
    price=models.DecimalField(max_digits=15,decimal_places=2)
    extras=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    currency=models.CharField(max_length=3,default='UAH')
    due_date=models.DateField()
    original_due=models.DateField()
    revision=models.CharField(max_length=40)
    production=models.ForeignKey(Production,null=True,blank=True,on_delete=models.PROTECT)
    request=models.ForeignKey('operations.ProcurementRequest',null=True,blank=True,on_delete=models.PROTECT)
    quote=models.ForeignKey('operations.SupplierQuote',null=True,blank=True,on_delete=models.PROTECT)
    approval_snapshot=models.JSONField(null=True,blank=True)
    status=models.CharField(max_length=20,default='ordered')

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(('quantity__gt', 0), ('received__gte', 0), ('received__lte', models.F('quantity'))), name='erp_purchase_quantity'),
            models.CheckConstraint(condition=models.Q(('extras__gte', 0), ('price__gte', 0)), name='erp_purchase_costs'),
            models.CheckConstraint(condition=models.Q(('currency__in', ('EUR', 'USD', 'UAH'))), name='erp_purchase_currency'),
        ]

class Movement(models.Model):
    lot=models.ForeignKey(Lot,on_delete=models.PROTECT,related_name='movements')
    quantity=models.DecimalField(max_digits=15,decimal_places=3)
    kind=models.CharField(max_length=30)
    reference=models.CharField(max_length=100)
    reason=models.TextField(blank=True)
    line=models.ForeignKey(SalesLine,null=True,blank=True,on_delete=models.PROTECT)
    production=models.ForeignKey(Production,null=True,blank=True,on_delete=models.PROTECT)
    purchase=models.ForeignKey(Purchase,null=True,blank=True,on_delete=models.PROTECT)
    cost=models.DecimalField(max_digits=15,decimal_places=2,default=0)
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(('cost__gte', 0)), name='erp_movement_cost'),
        ]

class Inspection(models.Model):
    lot=models.ForeignKey(Lot,on_delete=models.PROTECT)
    result=models.CharField(max_length=20)
    note=models.TextField()
    inspector=models.ForeignKey('employees.Employee',on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)

class ChangeOrder(models.Model):
    code=models.CharField(max_length=60,unique=True)
    item=models.ForeignKey(Item,on_delete=models.PROTECT)
    document=models.ForeignKey('operations.Document',on_delete=models.PROTECT)
    target_revision=models.CharField(max_length=40)
    reason=models.TextField()
    status=models.CharField(max_length=20,default='draft')
    disposition=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

class InvoiceLink(models.Model):
    invoice=models.OneToOneField('operations.Invoice',on_delete=models.PROTECT)
    order=models.ForeignKey(SalesOrder,on_delete=models.PROTECT)
    lines=models.JSONField(default=list)

class OperatorEntry(models.Model):
    production=models.ForeignKey(Production,on_delete=models.PROTECT,related_name='entries')
    operation=models.CharField(max_length=120)
    operator=models.ForeignKey('employees.Employee',on_delete=models.PROTECT)
    result=models.CharField(max_length=20)
    minutes=models.PositiveIntegerField(default=0)
    defects=models.DecimalField(max_digits=15,decimal_places=3,default=0)
    note=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

class Event(models.Model):
    action=models.CharField(max_length=60)
    payload=models.JSONField()
    result=models.JSONField()
    role=models.CharField(max_length=20)
    created_at=models.DateTimeField(auto_now_add=True)


class ImportBatch(models.Model):
    """Immutable source receipt; ordinary business operations keep evolving."""
    id = models.UUIDField(primary_key=True, editable=False)
    namespace = models.CharField(max_length=48)
    cutover = models.DateField()
    semantic_sha256 = models.CharField(max_length=64)
    canonical_source = models.JSONField()
    source_part_sha256 = models.JSONField(default=dict)
    actor = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    receipt = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ImportIdentity(models.Model):
    namespace = models.CharField(max_length=48)
    entity = models.CharField(max_length=32)
    external_id = models.CharField(max_length=120)
    row_sha256 = models.CharField(max_length=64)
    source_row = models.JSONField()
    first_batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT)
    counterparty = models.ForeignKey('finance.Counterparty', null=True, on_delete=models.PROTECT)
    item = models.ForeignKey(Item, null=True, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, null=True, on_delete=models.PROTECT)
    lot = models.ForeignKey(Lot, null=True, on_delete=models.PROTECT)
    order = models.ForeignKey(SalesOrder, null=True, on_delete=models.PROTECT)
    line = models.ForeignKey(SalesLine, null=True, on_delete=models.PROTECT)
    purchase = models.ForeignKey(Purchase, null=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['namespace','entity','external_id'],name='bos_import_external_identity')]
        constraints += [models.UniqueConstraint(fields=['namespace', field], condition=models.Q(**{field+'__isnull':False}),name='bos_import_target_'+field)
                        for field in ('counterparty','item','location','lot','order','line','purchase')]
        constraints += [models.CheckConstraint(name='bos_import_target_kind', condition=
            models.Q(entity='counterparty',counterparty__isnull=False,item__isnull=True,location__isnull=True,lot__isnull=True,order__isnull=True,line__isnull=True,purchase__isnull=True) |
            models.Q(entity='item',counterparty__isnull=True,item__isnull=False,location__isnull=True,lot__isnull=True,order__isnull=True,line__isnull=True,purchase__isnull=True) |
            models.Q(entity='location',counterparty__isnull=True,item__isnull=True,location__isnull=False,lot__isnull=True,order__isnull=True,line__isnull=True,purchase__isnull=True) |
            models.Q(entity='opening_lot',counterparty__isnull=True,item__isnull=True,location__isnull=True,lot__isnull=False,order__isnull=True,line__isnull=True,purchase__isnull=True) |
            models.Q(entity='sales_order',counterparty__isnull=True,item__isnull=True,location__isnull=True,lot__isnull=True,order__isnull=False,line__isnull=True,purchase__isnull=True) |
            models.Q(entity='sales_line',counterparty__isnull=True,item__isnull=True,location__isnull=True,lot__isnull=True,order__isnull=True,line__isnull=False,purchase__isnull=True) |
            models.Q(entity='purchase_open_balance',counterparty__isnull=True,item__isnull=True,location__isnull=True,lot__isnull=True,order__isnull=True,line__isnull=True,purchase__isnull=False))]


class CorrectionRecord(models.Model):
    operation_id=models.UUIDField(unique=True)
    payload_hash=models.CharField(max_length=64)
    code=models.CharField(max_length=60,unique=True)
    reason=models.TextField()
    business_date=models.DateField()
    created_at=models.DateTimeField(auto_now_add=True)
    actor=models.ForeignKey('auth.User',on_delete=models.PROTECT)
    event=models.ForeignKey(Event,on_delete=models.PROTECT)
    class Meta:
        abstract=True


class OrderCancellation(CorrectionRecord):
    line=models.ForeignKey(SalesLine,null=True,on_delete=models.PROTECT)
    purchase=models.ForeignKey(Purchase,null=True,on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=15,decimal_places=3)
    before_snapshot=models.JSONField()
    after_snapshot=models.JSONField()
    class Meta:
        constraints=[models.CheckConstraint(condition=(Q(line__isnull=False,purchase__isnull=True)|Q(line__isnull=True,purchase__isnull=False)),name='bos_cancel_target'),
            models.CheckConstraint(condition=Q(quantity__gt=0,quantity__lt=10**12),name='bos_cancel_quantity')]


class CancellationRelease(models.Model):
    cancellation=models.ForeignKey(OrderCancellation,on_delete=models.PROTECT)
    reservation=models.ForeignKey(Reservation,on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=15,decimal_places=3)
    before_quantity=models.DecimalField(max_digits=15,decimal_places=3)
    after_quantity=models.DecimalField(max_digits=15,decimal_places=3)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['cancellation','reservation'],name='bos_cancel_release_once'),
            models.CheckConstraint(condition=Q(quantity__gt=0,quantity__lt=10**12,before_quantity__gte=models.F('quantity'),before_quantity__lt=10**12,after_quantity__gte=0,after_quantity__lt=10**12,after_quantity=models.F('before_quantity')-models.F('quantity')),name='bos_cancel_release_balance')]


class GoodsReturn(CorrectionRecord):
    direction=models.CharField(max_length=10)
    source=models.ForeignKey(Movement,on_delete=models.PROTECT,related_name='source_returns')
    result=models.OneToOneField(Movement,on_delete=models.PROTECT,related_name='exact_return')
    quantity=models.DecimalField(max_digits=15,decimal_places=3)
    source_quantity=models.DecimalField(max_digits=15,decimal_places=3)
    source_cost=models.DecimalField(max_digits=15,decimal_places=2)
    currency=models.CharField(max_length=3)
    unit_cost=models.DecimalField(max_digits=15,decimal_places=2)
    allocated_cost=models.DecimalField(max_digits=15,decimal_places=2)
    source_snapshot=models.JSONField()
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(direction__in=['supplier','customer'],currency__in=['EUR','USD','UAH']),name='bos_return_kind_currency'),
            models.CheckConstraint(condition=Q(quantity__gt=0,quantity__lt=10**12,source_quantity__gt=0,source_quantity__lt=10**12,quantity__lte=models.F('source_quantity')),name='bos_return_quantities'),
            models.CheckConstraint(condition=Q(source_cost__gte=0,source_cost__lt=10**13,unit_cost__gte=0,unit_cost__lt=10**13,allocated_cost__gte=0,allocated_cost__lt=10**13,allocated_cost__lte=models.F('source_cost')),name='bos_return_costs'),
            models.CheckConstraint(condition=~Q(source=models.F('result')),name='bos_return_distinct_source')]


class SupplierClaim(CorrectionRecord):
    operation_id=models.UUIDField(unique=True,null=True)
    payload_hash=models.CharField(max_length=64,null=True)
    code=models.CharField(max_length=60,unique=True,null=True)
    record_kind=models.CharField(max_length=16)
    returned_goods=models.ForeignKey(GoodsReturn,on_delete=models.PROTECT,db_column='return_id')
    parent=models.OneToOneField('self',null=True,on_delete=models.PROTECT,related_name='confirmation')
    agreed_amount=models.DecimalField(max_digits=14,decimal_places=2,null=True)
    currency=models.CharField(max_length=3)
    source_document=models.ForeignKey('operations.Document',null=True,on_delete=models.PROTECT)
    source_snapshot=models.JSONField(default=dict)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(currency__in=['EUR','USD','UAH']),name='bos_claim_currency'),
            models.CheckConstraint(condition=Q(agreed_amount__isnull=True)|Q(agreed_amount__gte=0,agreed_amount__lt=10**12),name='bos_claim_amount'),
            models.CheckConstraint(condition=Q(record_kind='pending',parent__isnull=True,agreed_amount__isnull=True,source_document__isnull=True,operation_id__isnull=True,payload_hash__isnull=True)|Q(record_kind='confirmation',parent__isnull=False,agreed_amount__isnull=False,source_document__isnull=False,operation_id__isnull=False,payload_hash__isnull=False,code__isnull=False),name='bos_claim_record_shape'),
            models.CheckConstraint(condition=~Q(parent=models.F('pk')),name='bos_claim_distinct_parent')]


class InvoiceAdjustment(CorrectionRecord):
    kind=models.CharField(max_length=12)
    basis=models.CharField(max_length=12)
    invoice=models.ForeignKey('operations.Invoice',on_delete=models.PROTECT)
    reversed_credit=models.OneToOneField('self',null=True,on_delete=models.PROTECT,related_name='reversal')
    basis_snapshot=models.JSONField()
    basis_hash=models.CharField(max_length=64)
    total=models.DecimalField(max_digits=14,decimal_places=2)
    currency=models.CharField(max_length=3)
    source_document=models.ForeignKey('operations.Document',null=True,on_delete=models.PROTECT)
    source_snapshot=models.JSONField(default=dict)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(total__gte=0,total__lt=10**12,currency__in=['EUR','USD','UAH']),name='bos_credit_amount_currency'),
            models.CheckConstraint(condition=Q(kind='credit',basis__in=['return','commercial'],reversed_credit__isnull=True)|Q(kind='reversal',basis='reversal',reversed_credit__isnull=False),name='bos_credit_kind_source'),
            models.CheckConstraint(condition=~Q(reversed_credit=models.F('pk')),name='bos_credit_distinct_reverse')]


class InvoiceAdjustmentLine(models.Model):
    document=models.ForeignKey(InvoiceAdjustment,on_delete=models.PROTECT,related_name='lines')
    invoice_line_index=models.PositiveIntegerField()
    line=models.ForeignKey(SalesLine,on_delete=models.PROTECT)
    returned_goods=models.ForeignKey(GoodsReturn,null=True,on_delete=models.PROTECT,db_column='return_id')
    quantity=models.DecimalField(max_digits=15,decimal_places=3)
    amount=models.DecimalField(max_digits=14,decimal_places=2)
    source_snapshot=models.JSONField()
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(quantity__gte=0,quantity__lt=10**12,amount__gte=0,amount__lt=10**12),name='bos_credit_line_amount'),
            models.CheckConstraint(condition=Q(returned_goods__isnull=False,quantity__gt=0)|Q(returned_goods__isnull=True,quantity=0),name='bos_credit_line_source'),
            models.UniqueConstraint(fields=['document','invoice_line_index','returned_goods'],condition=Q(returned_goods__isnull=False),name='bos_credit_return_line_once'),
            models.UniqueConstraint(fields=['document','invoice_line_index'],condition=Q(returned_goods__isnull=True),name='bos_credit_commercial_line_once')]


class StockTransfer(models.Model):
    """A dispatched quantity is in transit, never available at either point."""
    code=models.CharField(max_length=60,unique=True)
    source_lot=models.ForeignKey(Lot,on_delete=models.PROTECT,related_name='dispatched_transfers')
    source_location=models.ForeignKey(Location,on_delete=models.PROTECT,related_name='outgoing_transfers')
    destination=models.ForeignKey(Location,on_delete=models.PROTECT,related_name='incoming_transfers')
    item=models.ForeignKey(Item,on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=15,decimal_places=3)
    revision=models.CharField(max_length=40)
    documents=models.JSONField(default=dict)
    unit_cost=models.DecimalField(max_digits=15,decimal_places=2)
    total_cost=models.DecimalField(max_digits=15,decimal_places=2)
    currency=models.CharField(max_length=3)
    status=models.CharField(max_length=20,default='in_transit')
    dispatch_movement=models.OneToOneField(Movement,on_delete=models.PROTECT,related_name='outbound_transfer')
    receipt_movement=models.OneToOneField(Movement,null=True,blank=True,on_delete=models.PROTECT,related_name='inbound_transfer')
    received_lot=models.OneToOneField(Lot,null=True,blank=True,on_delete=models.PROTECT,related_name='received_transfer')
    reason=models.TextField()
    due_date=models.DateField(null=True,blank=True)
    dispatched_at=models.DateTimeField(auto_now_add=True)
    received_at=models.DateTimeField(null=True,blank=True)

    class Meta:
        constraints=[
            models.CheckConstraint(condition=Q(quantity__gt=0,unit_cost__gte=0,total_cost__gte=0,currency__in=['EUR','USD','UAH']),name='bos_transfer_amounts'),
            models.CheckConstraint(condition=~Q(source_location=models.F('destination')),name='bos_transfer_points_distinct'),
            models.CheckConstraint(condition=Q(status='in_transit',received_at__isnull=True,received_lot__isnull=True,receipt_movement__isnull=True)|Q(status='received',received_at__isnull=False,received_lot__isnull=False,receipt_movement__isnull=False),name='bos_transfer_state'),
        ]


class PaymentRetention(models.Model):
    """Contractual hold on AR; releasing a hold never records payment."""
    code=models.CharField(max_length=60,unique=True)
    invoice=models.ForeignKey('operations.Invoice',on_delete=models.PROTECT,related_name='payment_retentions')
    amount=models.DecimalField(max_digits=14,decimal_places=2)
    currency=models.CharField(max_length=3)
    status=models.CharField(max_length=20,default='held')
    reason=models.TextField()
    release_reason=models.TextField(blank=True,default='')
    created_at=models.DateTimeField(auto_now_add=True)
    released_at=models.DateTimeField(null=True,blank=True)

    class Meta:
        constraints=[
            models.CheckConstraint(condition=Q(amount__gt=0,currency__in=['EUR','USD','UAH']),name='bos_retention_amount'),
            models.CheckConstraint(condition=Q(status='held',released_at__isnull=True)|Q(status='released',released_at__isnull=False),name='bos_retention_state'),
        ]
