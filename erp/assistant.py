"""Read-only grounded scenarios; proposals are handled by the existing confirmation UI."""
import json
from pathlib import Path
from . import queries,service
from .models import SalesOrder,Lot,Production,Purchase,Item

def tools_contract():
    result={f'erp_{name}':{'required':req.split(),'optional':opt.split()} for name,(req,opt) in service.SCHEMAS.items()}
    result.update({'erp_statement_import':{'required':'document_id source_sha256 source_system account_ref format parser_version'.split(),'optional':[]},'erp_statement_reconcile':{'required':'line_id transaction matching reason allocations'.split(),'optional':[]}})
    return result

def parameter_guide():
    path=Path(__file__).parent/'seed/assistant_examples_ua.json'
    if not path.exists():return {}
    d=json.loads(path.read_text())
    return {k:d[k] for k in ('types','enums')}

def answer(message,policy):
    t=message.lower()
    order=next((o for o in policy.queryset(SalesOrder) if o.code.lower() in t),None)
    if not order and not any(x in t for x in ['erp','склад','матеріал','дефіцит','виробництв','підрядник','партії','якість','собіварт','рахунк']):return None
    result={'mode':'local_scenario','sources':[]}
    if any(x in t for x in ['створи','спиши','перемісти','зарезервуй','відвантаж','оплати','запусти','зареєструй']):
        result['text']='Дію ще не виконано. В ERP оберіть відповідну операцію, заповніть поля та погодьте перегляд. Або завантажте контекст, отримайте JSON з action=erp_… у ChatGPT та імпортуйте його тут. Оплата в ERP — облік отриманих коштів, без банківського переказу.'
        return result
    if order:
        plans=[queries.plan_line(l,policy) for l in order.lines.select_related('item')]
        lines=['Замовлення '+order.code+' · клієнт '+order.customer.name+' · до '+str(order.due_date)]
        for p in plans:
            lines.append(p['item']+': поставити ще '+p['remaining']+', придатний резерв '+p['reserved']+', вільно '+p['free']+', забезпечити '+p['shortage']+'.')
            for m in p['materials']:lines.append(m['code']+': потрібно '+m['need']+' '+m['unit']+', доступно '+m['available']+', очікується до строку '+m['before_due']+', не покрито '+m['deficit']+'.')
            lines.append('Розрахункова дата '+p['estimated_date']+'. '+('; '.join(p['reasons']) or 'Погодьте остаточний строк із відповідальним.'))
            lines.append(p['basis'])
        lines.append('Джерела: ERP → Продажі / Склад / Постачання; поточні записи, без змін.')
        result['text']='\n'.join(lines);return result
    d=queries.snapshot(policy)
    if any(x in t for x in ['собіварт','рахунк']):
        if not policy.ceo:
            return {**result,'text':'Фінансове зведення доступне керівнику. Ви можете переглянути доступні замовлення, залишки та строки.'}
        lines=[x['code']+': відвантаження '+x['shipped_value']+', собівартість '+x['shipped_cost']+', різниця '+x['gross_margin']+' '+x['currency']+'.' for x in d['costs']]
        lines.extend(x['code']+': до оплати '+x['open']+' '+x['currency']+' до '+x['due_date']+'.' for x in d['invoices'])
        lines.append('Джерела: ERP → Фінансовий результат. Без податків і загальних витрат; повернення потребують окремого коригування.')
    elif any(x in t for x in ['виробництв','підрядник']):
        lines=[j['code']+': план '+str(j['quantity'])+', випущено '+str(j['produced'])+', до '+j['due_date']+(' · потрібне рішення щодо версії' if j['needs_review'] else '')+'.' for j in d['jobs']]
        lines.append('Джерела: ERP → Виробництво. Для старту всі матеріали мають бути на дільниці, зарезервовані та дозволені за якістю.')
    else:
        items={x['id']:x for x in d['items']};locations={x['id']:x for x in d['locations']}
        lines=[x['code']+' · '+items[x['item_id']]['code']+' · '+locations[x['location_id']]['name']+': фізично '+str(x['quantity'])+', резерв '+x['reserved']+', придатно й вільно '+x['available']+'.' for x in d['lots'] if float(x['quantity'])>0]
        lines.append('Джерела: ERP → Склад і Якість. Для потреб конкретного замовлення вкажіть його код, наприклад SO-101.')
    result['text']='\n'.join(lines) if lines else 'ERP поки не містить записів. Додайте номенклатуру й замовлення.'
    return result
