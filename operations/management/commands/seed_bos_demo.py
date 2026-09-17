import json,hashlib
from pathlib import Path
from django.core.management.base import BaseCommand,CommandError
from django.conf import settings
from django.db import transaction
from operations.models import *
from employees.models import Employee
from tasks.models import Task
from branches.models import Branch
from finance.models import Counterparty

class Command(BaseCommand):
    help='Створює узгоджену навчальну компанію BoS в окремій базі.'
    @transaction.atomic
    def handle(self,*args,**opts):
        if settings.BOS_DATA_MODE!='demo':raise CommandError('Навчальні дані заборонено імпортувати в робочу базу.')
        if Configuration.objects.filter(key='dataset').exists():self.stdout.write('Навчальна компанія вже існує. Записи збережено.');return
        if Employee.objects.exists() or Task.objects.exists() or Branch.objects.exists():raise CommandError('База не порожня. Автоматичне перезаписування заборонене.')
        seed=Path(__file__).resolve().parents[2]/'seed'
        def read(n):return json.loads((seed/(n+'.json')).read_text())
        branch=Branch.objects.create(code='DEMO',name='ДемоПром · навчальна компанія',short_name='ДемоПром',type='headquarters',employee_count=6,status='yellow')
        names=['Олексій Демонстраційний','Марія Прикладова','Іван Тестовий','Олена Навчальна','Олег Зразковий','Анна Макетна']
        roles=['Керівник','Менеджер закупівель','Інженер','Фінансовий менеджер','Менеджер продажів','Координатор складу']
        depts=['Управління','Закупівлі','Інженерія','Фінанси','Продажі','Склад'];employees={}
        for i,row in enumerate(read('employees')):employees[row['id']]=Employee.objects.create(full_name=names[i],role=roles[i],department=depts[i],branch=branch)
        suppliers={x:Counterparty.objects.create(name='Навчальний постачальник '+c,type='supplier') for x,c in zip(['S01','S02','S03'],'ABC')}
        customers={f'C{i:02}':Counterparty.objects.create(name=f'Навчальний клієнт {i}',type='customer') for i in range(1,4)}
        def doc(code,rev,title,text,status='approved',access_level='operational'):
            return Document.objects.create(access_level=access_level,code=code,revision=rev,title=title,text=text,sections=[{'source':'Розділ 1','text':text}],checksum=hashlib.sha256(text.encode()).hexdigest(),status=status)
        requests={}
        for r in read('requests'):
            text=f"Навчальна специфікація. Деталь {r['part']}; версія {r['revision']}; кількість {r['quantity']} шт. Матеріал: сталь. Обов’язкові покриття та сертифікат матеріалу. Потрібна дата {r['required_by']}. Не для виробництва."
            d=doc(r['document_id'],r['revision'],'Специфікація '+r['part'],text)
            requests[r['id']]=ProcurementRequest.objects.create(code=r['id'],part=r['part'],revision=r['revision'],quantity=r['quantity'],currency=r['currency'],required_by=r['required_by'],owner=employees[r['owner_id']],document=d,details={'project':'Навчальні промислові поставки','material':'Сталь','operations':'Виготовлення монтажного кронштейна','coating':'Обов’язкове','quality':'Сертифікат матеріалу; перевірка комплектності','tax_basis':'Без ПДВ'})
        for q in read('quotes'):
            terms={k:v for k,v in q.items() if k not in ('id','tenant_id','request_id','supplier_id','document_id')};terms.update(tooling='0',special_processes='0',moq=1)
            text=f"Навчальна пропозиція {q['id']}. Версія {q['revision']}. Ціна {q['unit_price']} EUR/шт.; налагодження {q['setup']}; доставка {q['shipping']}. Покриття: {'включено' if q['coating_included'] else 'не включено'}. Сертифікат матеріалу: так. Строк: {q['lead_weeks']} тижнів після замовлення. Чинна до {q['valid_until']}. Без ПДВ. Не є комерційною пропозицією."
            d=doc(q['id'],q['revision'],'Пропозиція '+q['id'],text,'supplier_quote',access_level='management')
            SupplierQuote.objects.create(code=q['id'],request=requests[q['request_id']],supplier=suppliers[q['supplier_id']],document=d,terms=terms)
        titles=['Перевірити покриття пропозиції Q12','Підтвердити версію B з постачальником C','Оновити прострочену пропозицію Q31','Підготувати порівняння R01','Підтвердити вхідний контроль R02','Звірити оплату I01','Передати специфікацію R01','Підготувати зустріч із клієнтом']
        for i,t in enumerate(read('tasks')):Task.objects.create(id=i+1,title=titles[i],assignee=employees[t['assignee_id']].full_name,deadline=t['deadline'],status=t['status'],category='Закупівлі' if t['request_id'] else 'Загальне',branch=branch)
        for i in read('invoices'):Invoice.objects.create(code=i['id'],customer=customers[i['customer_id']],amount=i['amount'],paid=i['paid'],currency=i['currency'],due_date=i['due_date'])
        doc('D-CASH','1','Навчальна виписка','На 09.09.2026 залишок становить 24 000 EUR. Навчальні дані; банківське підключення відсутнє.',access_level='ceo')
        Configuration.objects.create(key='dataset',value={'synthetic':True,'as_of':'2026-09-09','source':'Підготовлений BoS dataset; українська локалізація','id_mapping':'E01..E06 → Employee 1..6; T01..T08 → Task 1..8'})
        Configuration.objects.create(key='cash',value={'amount':'24000','currency':'EUR','source':'D-CASH'})
        Configuration.objects.create(key='organization',value={'name':'ДемоПром','description':'Навчальна компанія промислових поставок','industry':'Виробництво','process_owner':'Марія Прикладова','timezone':'Europe/Vienna','locale':'uk-UA','ai_timeout':30,'ai_max_steps':4,'ai_hourly_limit':30})
        self.stdout.write('Навчальну компанію BoS створено: 6 співробітників, 8 доручень, 3 заявки, 9 пропозицій, 13 документів.')
