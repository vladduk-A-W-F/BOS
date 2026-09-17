import hashlib
from django.core.management.base import BaseCommand,CommandError
from django.conf import settings
from django.db import transaction
from operations.models import Configuration,Document
from finance.models import Counterparty
from employees.models import Employee
from erp.models import *
from erp.service import dispatch

class Command(BaseCommand):
    help='Створює пов’язаний навчальний приклад ERP без перезаписування наявних записів.'
    @transaction.atomic
    def handle(self,*args,**opts):
        if settings.BOS_DATA_MODE!='demo':raise CommandError('ERP-демо дозволене лише в навчальній базі.')
        if Configuration.objects.filter(key='erp_dataset').exists():self.stdout.write('ERP-демо вже існує. Записи збережено.');return
        if Item.objects.exists() or SalesOrder.objects.exists():raise CommandError('ERP містить дані. Автоматичний імпорт зупинено.')
        if not Configuration.objects.filter(key='dataset').exists():raise CommandError('Спочатку виконайте seed_bos_demo.')
        def act(action,**data):return dispatch({'action':'erp_'+action,**data},'ceo')
        owner=Employee.objects.get(full_name='Марія Прикладова');engineer=Employee.objects.get(full_name='Іван Тестовий')
        supplier=Counterparty.objects.filter(type='supplier').order_by('id').first();customer=Counterparty.objects.filter(type='customer').order_by('id').first()
        def doc(code,revision,title,text):return Document.objects.create(access_level='operational',code=code,revision=revision,title=title,text=text,sections=[{'source':'Розділ 1','text':text}],checksum=hashlib.sha256(text.encode()).hexdigest(),status='approved')
        spec=doc('ERP-SPEC','A','Навчальна специфікація DEMO-101','Виріб DEMO-101: матеріал 0,8 кг; кріплення 2 шт. на виріб. Версія A. Усі значення синтетичні, не для реального виробництва.')
        spec_b=doc('ERP-SPEC','B','Зміна специфікації DEMO-101','Версія B. Уточнено контроль поверхні. Потрібне рішення щодо незавершених робіт версії A. Склад виробу без змін.')
        certificate=doc('ERP-CERT','1','Навчальний сертифікат партій','Навчальне підтвердження комплектності матеріалу й продукції. Не є сертифікатом реального виробника.')
        main=act('location',code='WH-01',name='Основний склад · комірки А1–А3',kind='warehouse')['location_id']
        prod=act('location',code='SHOP-01',name='Власна виробнича дільниця',kind='production')['location_id']
        vendor=act('location',code='VENDOR-A',name='Матеріали у підрядника A',kind='supplier',supplier_id=supplier.id)['location_id']
        raw=act('item',code='MAT-101',name='Навчальна сталева заготовка',unit='кг',kind='material',method='buy',revision='A',currency='EUR',required_documents=['certificate'],minimum='8',lead_days=7,planned_cost='12')['item_id']
        fast=act('item',code='FAST-101',name='Кріпильний елемент',unit='шт.',kind='component',method='buy',revision='A',currency='EUR',minimum='20',lead_days=3,planned_cost='2')['item_id']
        product=act('item',code='DEMO-101',name='Навчальний монтажний вузол',unit='шт.',kind='product',method='subcontract',revision='A',currency='EUR',material='Сталь',document_id=spec.id,external_codes={'Код клієнта':'CLIENT-101','Код постачальника':'SUP-101'},required_documents=['certificate'],planned_cost='40',bom=[{'item_id':raw,'quantity':'0.8'},{'item_id':fast,'quantity':'2'}],routing=[{'name':'Виготовлення','instruction':'Виконати операцію за погодженим кресленням.','days':2},{'name':'Покриття','instruction':'Зафіксувати завершення покриття та зауваження.','days':2},{'name':'Контроль','instruction':'Перевірити комплектність і передати результат якості.','days':1}])['item_id']
        order=act('order',code='SO-101',customer_id=customer.id,owner_id=owner.id,due_date='2026-09-30',currency='EUR',lines=[{'item_id':product,'quantity':'50','price':'120'}])['order_id'];act('confirm_order',order_id=order)
        competing=act('order',code='SO-102',customer_id=customer.id,owner_id=owner.id,due_date='2026-09-25',currency='EUR',lines=[{'item_id':product,'quantity':'5','price':'125'}])['order_id'];act('confirm_order',order_id=competing)
        line=SalesLine.objects.get(order_id=order)
        job=act('job',code='MO-101',item_id=product,quantity='40',location_id=vendor,owner_id=engineer.id,due_date='2026-09-24',line_id=line.id)['production_id']
        documents={'certificate':certificate.id}
        lots=[]
        for code,item,qty,cost,quality,docs in [('LOT-MAT',raw,'24','12','approved',documents),('LOT-FAST',fast,'60','2','approved',{}),('LOT-FG-OK',product,'10','40','approved',documents),('LOT-FG-HOLD',product,'10','40','blocked',{})]:
            lot=act('opening',code=code,item_id=item,location_id=main,quantity=qty,unit_cost=cost,currency='EUR',revision='A',documents=docs)['lot_id'];act('quality',lot_id=lot,result=quality,inspector_id=engineer.id,note='Навчальна перевірка' if quality=='approved' else 'Немає сертифіката; відвантаження заблоковано');lots.append(lot)
        act('reserve',lot_id=lots[2],quantity='10',line_id=line.id)
        act('purchase',code='PO-MAT',item_id=raw,supplier_id=supplier.id,quantity='8',price='12',currency='EUR',due_date='2026-09-16',revision='A',production_id=job,direct_reason='Навчальна пряма закупівля матеріалу для демонстраційного виробництва')
        act('purchase',code='PO-FAST',item_id=fast,supplier_id=supplier.id,quantity='20',price='2',currency='EUR',due_date='2026-09-12',revision='A',production_id=job,direct_reason='Навчальна пряма закупівля кріплень для демонстраційного виробництва')
        act('change',code='ECO-101',item_id=product,document_id=spec_b.id,target_revision='B',reason='Навчальний сценарій зміни контролю поверхні після запуску підготовки.')
        Configuration.objects.create(key='erp_dataset',value={'version':'1.0','synthetic':True,'as_of':'2026-09-09','primary_order':'SO-101','competing_order':'SO-102','main_job':'MO-101','scenario':'50 виробів: 10 зарезервовано, 40 виготовити, 10 заблоковано; дефіцит 8 кг та 20 кріплень закривають дві очікувані поставки.'})
        self.stdout.write('ERP-демо створено: замовлення, матеріали, резерви, підрядник, закупівлі та зміна версії.')
