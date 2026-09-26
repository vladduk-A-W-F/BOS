# Generated manually for the narrow BoS 3.0 CRM training boundary.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('employees', '0005_employee_user'),
        ('erp', '0008_compose_branch_network'),
        ('finance', '0008_statement_ledgers'),
        ('operations', '0010_supplier_invoice_registration'),
        ('training', '0001_initial'),
    ]
    operations = [
        migrations.CreateModel(
            name='CRMDeal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('case_id', models.CharField(max_length=40)),
                ('stable_handoff_hash', models.CharField(max_length=64)),
                ('title', models.CharField(max_length=200)),
                ('next_action', models.CharField(max_length=500)),
                ('stage', models.CharField(choices=[('qualification', 'Кваліфікація'), ('supply', 'Забезпечення'), ('fulfillment', 'Виконання'), ('collection', 'Контроль оплати'), ('won', 'Завершено'), ('lost', 'Не завершено')], max_length=20)),
                ('contact_name', models.CharField(blank=True, max_length=120)),
                ('contact_role', models.CharField(blank=True, max_length=120)),
                ('contact_email', models.EmailField(blank=True, max_length=254)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('counterparty', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='crm_deals', to='finance.counterparty')),
                ('invoice', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='crm_deals', to='operations.invoice')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='owned_crm_deals', to='employees.employee')),
                ('sales_order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='crm_deals', to='erp.salesorder')),
                ('training_session', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='crm_deals', to='training.trainingsession')),
            ],
            options={'ordering': ['-updated_at', '-id']},
        ),
        migrations.CreateModel(
            name='CRMActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('note', 'Нотатка'), ('call', 'Дзвінок'), ('meeting', 'Зустріч'), ('follow_up', 'Наступний контакт')], max_length=20)),
                ('summary', models.CharField(max_length=1000)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('status', models.CharField(choices=[('planned', 'Заплановано'), ('done', 'Виконано'), ('cancelled', 'Скасовано')], default='planned', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deal', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='activities', to='crm.crmdeal')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='crm_activities', to='employees.employee')),
            ],
            options={'ordering': ['due_date', '-created_at', '-id']},
        ),
        migrations.AddConstraint(model_name='crmdeal', constraint=models.UniqueConstraint(fields=('training_session', 'case_id', 'stable_handoff_hash'), name='crm_training_handoff_once')),
        migrations.AddConstraint(model_name='crmdeal', constraint=models.CheckConstraint(condition=models.Q(('stage__in', ['qualification', 'supply', 'fulfillment', 'collection', 'won', 'lost'])), name='crm_deal_stage')),
        migrations.AddConstraint(model_name='crmactivity', constraint=models.CheckConstraint(condition=models.Q(('kind__in', ['note', 'call', 'meeting', 'follow_up'])), name='crm_activity_kind')),
        migrations.AddConstraint(model_name='crmactivity', constraint=models.CheckConstraint(condition=models.Q(('status__in', ['planned', 'done', 'cancelled'])), name='crm_activity_status')),
    ]
