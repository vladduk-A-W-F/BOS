from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies=[('operations','0009_request_timing'),('erp','0008_compose_branch_network')]
    operations=[migrations.CreateModel(
        name='SupplierInvoiceRegistration',
        fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('identity_sha256',models.CharField(max_length=64,unique=True)),('invoice_identity_sha256',models.CharField(max_length=64,unique=True)),('source_sha256',models.CharField(max_length=64)),('context_sha256',models.CharField(max_length=64)),('semantic_context_sha256',models.CharField(max_length=64)),
            ('invoice_number',models.CharField(max_length=60)),('invoice_date',models.DateField()),('amount',models.DecimalField(decimal_places=2,max_digits=14)),('currency',models.CharField(max_length=3)),
            ('receipt_ids',models.JSONField(default=list)),('return_ids',models.JSONField(default=list)),('created_at',models.DateTimeField(auto_now_add=True)),
            ('document',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='supplier_invoice_registrations',to='operations.document')),
            ('purchase',models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,related_name='supplier_invoice_registration',to='erp.purchase')),
            ('registered_by',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to=settings.AUTH_USER_MODEL)),
            ('supplier',models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,to='finance.counterparty')),
        ],options={'ordering':['-created_at','-id']},
    ),migrations.AddConstraint(model_name='supplierinvoiceregistration',constraint=models.CheckConstraint(condition=models.Q(('amount__gte',0),('amount__lte',__import__('decimal').Decimal('999999999999.99'))),name='bos_supplier_invoice_amount_range')),
      migrations.AddConstraint(model_name='supplierinvoiceregistration',constraint=models.CheckConstraint(condition=models.Q(('currency__in',('EUR','USD','UAH'))),name='bos_supplier_invoice_currency'))]
