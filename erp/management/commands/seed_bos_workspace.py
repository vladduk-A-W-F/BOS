"""Add populated completed examples without changing the primary demo order."""
from django.core.management.base import BaseCommand,CommandError
from django.conf import settings
from django.db import transaction
from operations.models import Configuration,Document
from erp.models import Item,Location,SalesOrder,SalesLine,Lot,InvoiceLink
from erp.service import dispatch,accepted_documents
from employees.models import Employee
from finance.models import Counterparty

class Command(BaseCommand):
    help='Додає завершені приклади для головного екрана без перезапису наявних даних.'
    @transaction.atomic
    def handle(self,*args,**options):
        if settings.BOS_DATA_MODE!='demo':raise CommandError('Лише навчальна база.')
        if Configuration.objects.filter(key='workspace_dataset').exists():self.stdout.write('Приклади робочого простору вже існують.');return
        if not Configuration.objects.filter(key='erp_dataset').exists():raise CommandError('Спочатку додайте ERP-демо.')
        if SalesOrder.objects.filter(code__in=['SO-090','SO-091','SO-092']).exists():self.stdout.write('Додаткові приклади пропущено: коди вже використовуються. Ваші дані збережено.');return
        item=Item.objects.filter(code='DEMO-101').first();loc=Location.objects.filter(code='WH-01').first();owner=Employee.objects.filter(full_name='Марія Прикладова').first();inspector=Employee.objects.filter(full_name='Іван Тестовий').first();customer=Counterparty.objects.filter(type='customer').first();doc=Document.objects.filter(code='ERP-CERT').order_by('-id').first()
        if not all([item,loc,owner,inspector,customer,doc]) or doc.status!='approved' or accepted_documents(item,{'certificate':doc.id}):
            self.stdout.write('Додаткові приклади пропущено: довідники або документи змінено. BoS відкриється з вашими записами.');return
        def act(a,**d):return dispatch({'action':'erp_'+a,**d},'ceo')
        for code,qty,price,cost,paid in [('SO-090','12','120','37','1440'),('SO-091','8','125','38','600'),('SO-092','10','120','39','0')]:
            order=act('order',code=code,customer_id=customer.id,owner_id=owner.id,due_date='2026-09-30',currency='EUR',lines=[{'item_id':item.id,'quantity':qty,'price':price}],notes='Синтетичний завершений приклад: показує зв’язок поставки, рахунку, оплати й собівартості.')['order_id'];act('confirm_order',order_id=order)
            line=SalesLine.objects.get(order_id=order)
            lot=act('opening',code='LOT-'+code,item_id=item.id,location_id=loc.id,quantity=qty,unit_cost=cost,currency='EUR',revision=item.revision,documents={'certificate':doc.id},reason='Навчальний приклад завершеної поставки')['lot_id']
            act('quality',lot_id=lot,result='approved',inspector_id=inspector.id,note='Навчальна перевірка комплектності');act('reserve',lot_id=lot,line_id=line.id,quantity=qty);act('ship',lot_id=lot,line_id=line.id,quantity=qty,reference='SHIP-'+code)
            inv=act('invoice',order_id=order,code='INV-'+code,due_date='2026-10-10')['invoice_id']
            if paid!='0':act('payment',invoice_id=inv,amount=paid,reference='PAY-'+code)
        Configuration.objects.create(key='workspace_dataset',value={'version':1,'synthetic':True,'orders':['SO-090','SO-091','SO-092']})
        self.stdout.write('Додано 3 завершені приклади: 3640 EUR відвантажень, 2040 EUR оплат, 1600 EUR відкрито.')
