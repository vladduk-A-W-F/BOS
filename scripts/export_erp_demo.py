"""Rebuild synthetic ERP context in memory; never reads user business data."""
import os,sys,json,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE']='demo_settings';os.environ['BOS_DATA_MODE']='demo'
import django
from django.conf import settings
settings.DATABASES['default']['NAME']=':memory:';django.setup()
from django.core.management import call_command
from erp.queries import snapshot
from erp.assistant import tools_contract
from erp.models import Purchase,Production,SalesLine,Lot,Item,Location
from employees.models import Employee
from operations.models import Document
log=io.StringIO()
call_command('migrate',verbosity=0,stdout=log);call_command('seed_bos_demo',verbosity=0,stdout=log);call_command('seed_erp_demo',verbosity=0,stdout=log);call_command('seed_bos_workspace',verbosity=0,stdout=log)
d=snapshot();d['synthetic']=True;d['product']='BoS';d['tools']=tools_contract();d['instruction']='Навчальний приклад. Для виконання використовуй ID з поточної бази, а не цього файла. Лише одна дія після перевірки й погодження.'
p=ROOT/'erp/seed';p.mkdir(exist_ok=True)
(p/'demo_context_ua.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
po=Purchase.objects.get(code='PO-MAT');job=Production.objects.get(code='MO-101');line=SalesLine.objects.get(order__code='SO-101');lot=Lot.objects.get(code='LOT-MAT');emp=Employee.objects.get(full_name='Іван Тестовий')
examples={
 'product':'BoS','synthetic':True,'instruction':'Приклади незалежні. ID чинні тільки для свіжого демо; звірте з поточним експортом. Не виконуйте пакет автоматично. Кожну дію погоджує користувач.',
 'read_scenarios':[
 {'question':'Поясни SO-101','expected':'50 до поставки, 10 резерв, 40 забезпечити; 32 кг / 80 кріплень; дефіцит до закупівель 8 / 20.'},
 {'question':'Чому не можна відвантажити LOT-FG-HOLD?','expected':'Партію заблоковано, немає обов’язкового сертифіката; 10 фізичних одиниць не є придатними.'},
 {'question':'Чи можна резерв SO-101 віддати SO-102?','expected':'Спершу потрібне окреме рішення та звільнення резерву; один і той самий запас не резервується двічі.'},
 {'question':'Що потрібно для старту MO-101?','expected':'Передати матеріали на VENDOR-A, перевірити якість, зарезервувати 32 кг і 80 кріплень, погодити версію.'},
 {'question':'Що станеться після ECO-101?','expected':'Версія номенклатури B; відкриті роботи на перегляді; прийняті продажі та зафіксована версія робіт не переписуються.'}],
 'action_examples':[
 {'purpose':'Погоджене перенесення поставки','payload':{'action':'erp_postpone','purchase_id':po.id,'due_date':'2026-09-18','reason':'Навчальне підтвердження постачальника'}},
 {'purpose':'Передача наявного матеріалу підряднику','payload':{'action':'erp_transfer','lot_id':lot.id,'quantity':'24','location_id':job.location_id,'code':'V-MAT-AI','reason':'Давальницький матеріал MO-101','production_id':job.id}},
 {'purpose':'Приймання закупівлі у підрядника','payload':{'action':'erp_receive','purchase_id':po.id,'code':'RCV-MAT-AI','location_id':job.location_id,'quantity':'8','documents':{'certificate':Document.objects.get(code='ERP-CERT').id}}},
 {'purpose':'Доручення відповідальному','payload':{'action':'create_task','title':'Підтвердити матеріали й графік MO-101','assignee_id':emp.id,'deadline':'2026-09-11'}}],
 'nested_parameters':{'bom':[{'item_id':Item.objects.get(code='MAT-101').id,'quantity':'0.8'}],'lines':[{'item_id':line.item_id,'quantity':'50','price':'120'}],'routing':[{'name':'Виготовлення','instruction':'Виконати погоджені вимоги','days':2}],'documents':{'certificate':Document.objects.get(code='ERP-CERT').id},'external_codes':{'Код клієнта':'CLIENT-101','Код постачальника':'SUP-101'},'required_documents':['certificate']},
 'enums':{'currency':['EUR','UAH','USD'],'item.kind':['product','material','component'],'item.method':['buy','make','subcontract'],'location.kind':['warehouse','production','supplier'],'quality.result':['approved','blocked','rework'],'operator.result':['done','paused','defect']},
 'types':{'ids':'Цілі позитивні числа; не рядки','dates':'YYYY-MM-DD','quantity':'Позитивний десятковий рядок, до 3 знаків після крапки','money':'Невід’ємний десятковий рядок, до 2 знаків після крапки','minutes':'Ціле число','days':'Ціле число','reserve':'Вкажіть рівно один із line_id / production_id','documents':'Тип документа → ID перевіреного документа','finish.labor_cost':'Витрати робіт лише для поточної кількості випуску, не весь бюджет роботи'}
}
(p/'assistant_examples_ua.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2)+'\n')
print('Синтетичний контекст і приклади асистента оновлено.')
