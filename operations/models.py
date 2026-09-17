from decimal import Decimal
import uuid
from django.db import models
from django.conf import settings
from .private_storage import private_document_storage

class Document(models.Model):
    access_level=models.CharField(max_length=20,default='ceo',choices=[('operational','Операційний'),('management','Менеджмент'),('ceo','Лише керівник')])
    code=models.CharField(max_length=80)
    revision=models.CharField(max_length=40)
    title=models.CharField(max_length=200)
    filename=models.CharField(max_length=200,blank=True)
    content=models.BinaryField(default=bytes)
    original_file=models.FileField(storage=private_document_storage,max_length=255,null=True,blank=True)
    size=models.PositiveBigIntegerField(null=True,blank=True)
    text=models.TextField(blank=True)
    sections=models.JSONField(default=list)
    status=models.CharField(max_length=30,default='needs_review')
    checksum=models.CharField(max_length=64)
    contract=models.ForeignKey('finance.Contract',null=True,blank=True,on_delete=models.SET_NULL)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['code','revision'],name='bos_document_version')]
        ordering=['-created_at']
        permissions=[('download_document','Завантажувати доступні документи'),('export_workspace','Експортувати доступний робочий контекст')]

class ProcurementRequest(models.Model):
    code=models.CharField(max_length=30,unique=True)
    part=models.CharField(max_length=120)
    revision=models.CharField(max_length=40)
    quantity=models.PositiveIntegerField()
    unit=models.CharField(max_length=20,default='шт.')
    currency=models.CharField(max_length=3,default='EUR')
    required_by=models.DateField()
    owner=models.ForeignKey('employees.Employee',on_delete=models.PROTECT)
    document=models.ForeignKey(Document,on_delete=models.PROTECT)
    details=models.JSONField(default=dict)
    status=models.CharField(max_length=30,default='review')

class SupplierQuote(models.Model):
    code=models.CharField(max_length=30,unique=True)
    request=models.ForeignKey(ProcurementRequest,on_delete=models.CASCADE,related_name='quotes')
    supplier=models.ForeignKey('finance.Counterparty',on_delete=models.PROTECT)
    document=models.ForeignKey(Document,on_delete=models.PROTECT)
    terms=models.JSONField(default=dict)

class ActionProposal(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    session_key=models.CharField(max_length=64)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL,related_name='bos_proposals')
    role=models.CharField(max_length=20)
    payload=models.JSONField()
    fingerprint=models.CharField(max_length=64)
    expires_at=models.DateTimeField()
    receipt=models.JSONField(null=True)
    created_at=models.DateTimeField(auto_now_add=True)

class AuditEvent(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    action=models.CharField(max_length=40)
    task=models.ForeignKey('tasks.Task',on_delete=models.SET_NULL,null=True)
    payload=models.JSONField(default=dict)
    created_at=models.DateTimeField(auto_now_add=True)

class Invoice(models.Model):
    code=models.CharField(max_length=30,unique=True)
    customer=models.ForeignKey('finance.Counterparty',on_delete=models.PROTECT)
    amount=models.DecimalField(max_digits=14,decimal_places=2)
    paid=models.DecimalField(max_digits=14,decimal_places=2,default=0)
    currency=models.CharField(max_length=3)
    due_date=models.DateField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(('amount__gte', 0), ('amount__lte', Decimal('999999999999.99'))), name='bos_invoice_amount_range'),
            models.CheckConstraint(condition=models.Q(('paid__gte', 0), ('paid__lte', models.F('amount'))), name='bos_invoice_paid_range'),
            models.CheckConstraint(condition=models.Q(('currency__in', ('EUR', 'USD', 'UAH'))), name='bos_invoice_currency'),
        ]

class Configuration(models.Model):
    key=models.CharField(max_length=50,unique=True)
    value=models.JSONField(default=dict)


class LoginAttempt(models.Model):
    # Shared across workers; never store the supplied username or IP address.
    key = models.CharField(max_length=64, primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    latest_ticket = models.UUIDField(default=uuid.uuid4)
