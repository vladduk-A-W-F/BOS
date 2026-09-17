"""Bounded initial import. No generic model writes, historical repair or file import."""
from contextlib import contextmanager
from functools import wraps
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal,ROUND_HALF_EVEN,localcontext
from fractions import Fraction
import hashlib,json,re
from uuid import UUID,uuid4

from django.db import connection,transaction
from django.db.models import Sum
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from employees.models import Employee
from finance.models import Counterparty
from operations.models import ActionProposal,Configuration,Document
from operations.service import Conflict,as_of
from boss_project.identity import actor
from boss_project.policy import Policy
from boss_project.data_rules import field_values,text_value
from .models import ImportBatch,ImportIdentity,Item,Location,Lot,Movement,SalesOrder,SalesLine,Purchase,Event

D=Decimal
ENTITIES=('counterparty','item','location','opening_lot','sales_order','sales_line','purchase_open_balance')
TARGET={'counterparty':('counterparty',Counterparty),'item':('item',Item),'location':('location',Location),
 'opening_lot':('lot',Lot),'sales_order':('order',SalesOrder),'sales_line':('line',SalesLine),'purchase_open_balance':('purchase',Purchase)}
REQUIRED={
 'counterparty':'name type','item':'bos_code name unit kind revision currency','location':'bos_code name',
 'opening_lot':'bos_code item_ref location_ref unit revision quantity unit_cost currency source_reference reason',
 'sales_order':'bos_code customer_ref owner_id due_date currency source_status',
 'sales_line':'order_ref item_ref unit revision quantity price',
 'purchase_open_balance':'bos_code item_ref supplier_ref unit revision source_order_code source_line_id original_quantity received_before_cutover remaining_quantity price original_extras remaining_extras currency original_due due_date source_reference'}
DEFAULTS={'counterparty':dict(edrpou='',phone='',email='',address=''),
 'item':dict(method='buy',planned_cost='0.00',minimum='0.000',lead_days=7,material='',document=None,required_documents=[]),
 'location':dict(kind='warehouse'),'opening_lot':dict(documents={}),'sales_order':dict(notes=''),'sales_line':{},'purchase_open_balance':dict(source_documents={})}
QFIELDS={'quantity','minimum','original_quantity','received_before_cutover','remaining_quantity'}
MFIELDS={'price','unit_cost','original_extras','remaining_extras','planned_cost'}
MONEY_KEYS=('opening_raw_value','opening_movement_cost','sales_open_value','purchase_original_value','purchase_cutover_open_value')
CURRENCIES=('EUR','UAH','USD')
REFS={'item_ref':'item','location_ref':'location','supplier_ref':'counterparty','customer_ref':'counterparty','order_ref':'sales_order'}
ISSUED={}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()


def decimal(value,places,positive=False):
    if not isinstance(value,str) or not re.fullmatch(r'\d+(?:\.\d+)?',value) or len(value)>40:
        raise ValueError('Потрібен десятковий рядок без exponent або коми.')
    n=D(value);quantum=D(1).scaleb(-places)
    if n>D('1000000000') or n!=n.quantize(quantum) or (positive and n<=0):
        raise ValueError('Перевірте точність, кількість або місткість числа.')
    return format(n,f'.{places}f')


def external(value,maximum=120):
    text_value(value,maximum=maximum)
    if not value or value.strip()!=value:raise ValueError('Потрібен непорожній точний код без крайніх пробілів.')
    return value


def document_ref(value):
    if not isinstance(value,dict) or set(value)!={'document_id','code','revision','checksum'}:raise ValueError('Потрібні точні ID/код/версія/checksum документа.')
    if type(value['document_id']) is not int or value['document_id']<=0:raise ValueError('Некоректний ID документа.')
    external(value['code'],80);external(value['revision'],40)
    if not isinstance(value['checksum'],str) or not re.fullmatch('[a-f0-9]{64}',value['checksum']):raise ValueError('Потрібен SHA256 документа.')
    return value


class InvalidBatch(ValueError):
    def __init__(self,errors,status=422):self.errors=errors;self.status=status;super().__init__('Перевірте рядки імпорту.')


def error(row,field,message,code='BAD_VALUE',locators=None):
    key=(row.get('entity') if isinstance(row.get('entity'),str) else None,row.get('external_id') if isinstance(row.get('external_id'),str) else None)
    where=(locators or {}).get(key,{'row':None,'part':'json'})
    return dict(entity=key[0],external_id=key[1],**where,field=field,code=code,message=str(message))


def exact_arithmetic(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        with localcontext() as ctx:
            ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
            return fn(*args,**kwargs)
    return wrapped



@exact_arithmetic
def normalize(raw,collect=False):
    keys={'format','batch_id','namespace','cutover','tax_basis','bindings','rows','expected_source_control_totals'}
    if not isinstance(raw,dict) or set(raw)!=keys:raise InvalidBatch([error({},'batch','Невідомі або відсутні ключі пакета.')],400)
    if raw['format']!='bos.initial-import.v1' or raw['tax_basis']!='excluding_VAT':raise InvalidBatch([error({},'format','Непідтриманий формат або податкова база.')],400)
    try:
        assert isinstance(raw['batch_id'],str)
        token=UUID(raw['batch_id']);assert token.version==4 and str(token)==raw['batch_id']
        assert isinstance(raw['namespace'],str) and re.fullmatch('[a-z][a-z0-9_-]{0,47}',raw['namespace'])
        assert date.fromisoformat(raw['cutover']).isoformat()==raw['cutover']
        assert isinstance(raw['rows'],list) and isinstance(raw['bindings'],list) and 1<=len(raw['rows'])+len(raw['bindings'])<=100
    except (TypeError,ValueError,AssertionError):raise InvalidBatch([error({},'batch','Перевірте UUID4, namespace, дату та 1–100 рядків.')],400)
    validate_controls(raw['expected_source_control_totals'])
    out=deepcopy(raw);errors=[];seen=set();locators={};rows=[]
    for number,source in enumerate(raw['rows'],1):
        row=deepcopy(source)
        if not isinstance(row,dict):errors.append(error({},'rows','Рядок має бути об’єктом.'));continue
        key=(row.get('entity'),row.get('external_id'));field='row'
        try:
            if key[0] not in ENTITIES:raise ValueError('Невідомий вид рядка.')
            external(key[1]);locators[key]={'row':number,'part':'json'}
            if key in seen:errors.append(error(row,'external_id','Зовнішній ID повторено.','DUPLICATE_ID',locators));continue
            seen.add(key)
            required=set(REQUIRED[key[0]].split())|{'entity','external_id'};allowed=required|set(DEFAULTS[key[0]])
            if set(row)-allowed or not required<=set(row):raise ValueError('Невідомі або відсутні поля рядка.')
            row={**deepcopy(DEFAULTS[key[0]]),**row}
            for field,value in list(row.items()):
                if field in QFIELDS:row[field]=decimal(value,3,positive=field not in {'minimum','received_before_cutover'})
                elif field in MFIELDS:row[field]=decimal(value,2)
                elif field in REFS:external(value)
                elif field=='bos_code':external(value,60)
                elif field in ('source_order_code','source_line_id'):external(value,200)
                elif field in ('revision','unit'):external(value,40 if field=='revision' else 20)
                elif field in ('due_date','original_due'):
                    if date.fromisoformat(value).isoformat()!=value:raise ValueError('Потрібна ISO дата.')
                elif field=='currency' and value not in CURRENCIES:raise ValueError('Підтримано EUR,UAH,USD.')
                elif isinstance(value,str):text_value(value,maximum=1000)
            if 'owner_id' in row and (type(row['owner_id']) is not int or row['owner_id']<=0):raise ValueError('Потрібен ID відповідального.')
            if key[0]=='counterparty' and row['type'] not in ('supplier','customer'):raise ValueError('Потрібен supplier/customer.')
            if key[0]=='item':
                if row['method']!='buy' or row['kind'] not in ('product','material','component'):raise ValueError('Перший профіль підтримує каталог buy.')
                if type(row['lead_days']) is not int or not 0<=row['lead_days']<=730:raise ValueError('Перевірте lead_days.')
                if not isinstance(row['required_documents'],list) or any(not isinstance(x,str) or not 1<=len(x)<=60 for x in row['required_documents']):raise ValueError('Перевірте види документів.')
                if row['document'] is not None:document_ref(row['document'])
            if key[0]=='location' and row['kind']!='warehouse':raise ValueError('Потрібен склад warehouse.')
            if key[0]=='sales_order' and row['source_status'] not in ('quote','confirmed'):raise ValueError('Потрібен статус quote/confirmed.')
            for field in ('documents','source_documents'):
                if field in row:
                    if not isinstance(row[field],dict):raise ValueError('Документи мають бути словником.')
                    for kind,ref in row[field].items():external(kind,60);document_ref(ref)
            if key[0]=='purchase_open_balance':
                if D(row['original_quantity'])-D(row['received_before_cutover'])!=D(row['remaining_quantity']):raise ValueError('Початкова кількість мінус отримане не дорівнює залишку.')
                if D(row['remaining_extras'])>D(row['original_extras']):raise ValueError('Витрати залишку перевищують первинні.')
            for f in ('source_reference','reason'):
                if f in row and (not isinstance(row[f],str) or not row[f].strip()):raise ValueError('Потрібне явне посилання та обґрунтування джерела.')
            rows.append(row)
        except (ValueError,TypeError,KeyError) as exc:errors.append(error(row,field,exc,locators=locators))
    bindings=[]
    for b in raw['bindings']:
        try:
            if not isinstance(b,dict) or set(b)!={'entity','external_id','target_id'} or b['entity'] not in ('item','counterparty','location'):raise ValueError('Невідома прив’язка.')
            external(b['external_id']);key=(b['entity'],b['external_id'])
            if key in seen:raise ValueError('ID рядка або прив’язки повторено.')
            seen.add(key)
            if type(b['target_id']) is not int or b['target_id']<=0:raise ValueError('Некоректний target ID.')
            bindings.append(b)
        except (ValueError,TypeError,KeyError) as exc:errors.append(error({},'bindings',exc))
    out['rows']=sorted(rows,key=lambda r:(r['entity'],r['external_id']));out['bindings']=sorted(bindings,key=lambda r:(r['entity'],r['external_id']))
    if collect:return out,locators,errors
    if errors:raise InvalidBatch(errors)
    return out,locators


def source_totals(rows):
    counts={entity:0 for entity in ENTITIES};money={c:{k:D(0) for k in MONEY_KEYS} for c in CURRENCIES};stock={}
    orders={r['external_id']:r for r in rows if r['entity']=='sales_order'}
    with localcontext() as ctx:
        ctx.prec=50;ctx.rounding=ROUND_HALF_EVEN
        for r in rows:
            entity=r['entity'];counts[entity]+=1
            if entity=='opening_lot':
                raw=D(r['quantity'])*D(r['unit_cost']);m=money[r['currency']];m['opening_raw_value']+=raw;m['opening_movement_cost']+=raw.quantize(D('.01'))
                key=tuple(r[k] for k in ('item_ref','location_ref','unit','revision','currency'));stock[key]=stock.get(key,D(0))+D(r['quantity'])
            elif entity=='sales_line' and r['order_ref'] in orders:money[orders[r['order_ref']]['currency']]['sales_open_value']+=D(r['quantity'])*D(r['price'])
            elif entity=='purchase_open_balance':
                m=money[r['currency']];m['purchase_original_value']+=D(r['original_quantity'])*D(r['price'])+D(r['original_extras']);m['purchase_cutover_open_value']+=D(r['remaining_quantity'])*D(r['price'])+D(r['remaining_extras'])
    return {'counts':counts,'money':[dict(currency=c,**{k:format(money[c][k],'.2f' if k=='opening_movement_cost' else '.5f') for k in MONEY_KEYS}) for c in CURRENCIES],
        'stock':[dict(zip(('item_ref','location_ref','unit','revision','currency'),key),quantity=format(value,'.3f')) for key,value in sorted(stock.items())]}


def semantic(batch):return digest({k:v for k,v in batch.items() if k!='batch_id'})

def row_hash(batch,row):
    data={'namespace':batch['namespace'],'cutover':batch['cutover'],'row':row}
    if row['entity']=='sales_order':data['lines']=[r for r in batch['rows'] if r['entity']=='sales_line' and r['order_ref']==row['external_id']]
    return digest(data)


def fingerprint():
    from .service import fingerprint as base
    return digest({'erp':base(),'counterparties':list(Counterparty.objects.order_by('pk').values()),
        'employees':json.loads(json.dumps(list(Employee.objects.order_by('pk').values()),default=str)),
        'dataset':list(Configuration.objects.filter(key='dataset').values()),
        'identities':list(ImportIdentity.objects.order_by('pk').values()),
        'batches':list(ImportBatch.objects.order_by('pk').values('id','semantic_sha256'))})


class ImportAuthority:
    def __new__(cls,*args,**kwargs):raise TypeError('Контекст видає тільки імпортне погодження.')


def assert_authority(authority,kind,hash_value,phase=None):
    value=ISSUED.get(id(authority))
    if (type(authority) is not ImportAuthority or not value or value['object'] is not authority or
        value['kind']!=kind or value['hash']!=hash_value or (kind=='purchase' and digest(value['row'])!=value['row_hash']) or (phase is not None and value['phase']!=phase) or value['connection'] is not transaction.get_connection() or
        not connection.in_atomic_block or not any(block is value['atomic'] for block in connection.atomic_blocks)):
        raise PermissionError('Імпортний контекст відсутній, завершений або не відповідає рядку.')
    return value


@contextmanager
def authority(kind,hash_value,principal,phase,row=None,parent=None):
    if phase not in ('preview','apply') or not connection.in_atomic_block or principal.role!='ceo':raise PermissionError('Потрібне погодження керівника у транзакції.')
    if parent is not None:
        p=ISSUED.get(id(parent))
        if not p or p['phase']!=phase or p['principal']!=principal:raise PermissionError('Інший контекст імпорту.')
    token=object.__new__(ImportAuthority)
    ISSUED[id(token)]={'object':token,'kind':kind,'hash':hash_value,'principal':principal,'phase':phase,'row':row,
        'atomic':connection.atomic_blocks[-1],'connection':transaction.get_connection()}
    if kind=='purchase':
        ISSUED[id(token)]['row']=deepcopy(row);ISSUED[id(token)]['row_hash']=digest(row)
    try:yield token
    finally:ISSUED.pop(id(token),None)


def historical_purchase(data,item,context,phase):
    value=assert_authority(context,'purchase',digest(data),phase);
    if phase not in ('preview','apply'):raise PermissionError('Невідома фаза імпорту.')
    row=value['row'];batch=row['batch'];r=row['source']
    # Admission is exact and issued by the coordinator; normal ERP input cannot mint it.
    if item.unit!=r['unit'] or item.revision!=r['revision']:raise ValueError('Історична одиниця/версія не відповідає номенклатурі.')
    snapshot={k:deepcopy(v) for k,v in r.items() if k not in ('entity','bos_code','item_ref','supplier_ref')}
    snapshot.update(source='imported_open_balance',namespace=batch['namespace'],batch_id=batch['batch_id'],cutover=batch['cutover'],row_sha256=row_hash(batch,r),actor_id=value['principal'].user_id)
    return {**data,'approval_snapshot':snapshot,'quote_id':None,'request_id':None,'production_id':None},r['original_due']


def locked_references(batch):
    cp_ids=set();employee_ids={r['owner_id'] for r in batch['rows'] if r['entity']=='sales_order'}
    for b in batch['bindings']:
        if b['entity']=='counterparty':cp_ids.add(b['target_id'])
    cp_ids.update(ImportIdentity.objects.filter(namespace=batch['namespace'],counterparty_id__isnull=False).values_list('counterparty_id',flat=True))
    list(Counterparty.objects.select_for_update().filter(pk__in=cp_ids).order_by('pk'))
    list(Employee.objects.select_for_update().filter(pk__in=employee_ids).order_by('pk'))


def checked_documents(values,policy):
    result={}
    from operations.private_storage import verified_document_bytes
    from operations.service import newest
    for kind,ref in values.items():
        doc=policy.documents().get(pk=ref['document_id'])
        if (doc.code,doc.revision,doc.checksum)!=(ref['code'],ref['revision'],ref['checksum']) or newest(doc.code).pk!=doc.pk or doc.status!='approved':
            raise ValueError('Потрібна дозволена актуальна перевірена версія документа.')
        verified_document_bytes(doc);result[kind]=doc.pk
    return result


def plan(batch,locators,policy):
    existing={ (x.entity,x.external_id):x for x in ImportIdentity.objects.filter(namespace=batch['namespace']).select_related(*[x[0] for x in TARGET.values()])}
    known=ImportBatch.objects.filter(pk=batch['batch_id']).first()
    if known and known.semantic_sha256!=semantic(batch):raise Conflict('UUID пакета вже використано з іншим змістом.')
    refs={key:getattr(obj,TARGET[obj.entity][0]) for key,obj in existing.items()}
    new=[];reused=[];binds=[];binding_reused=[];errors=[];incoming={(r['entity'],r['external_id']):r for r in batch['rows']}
    for b in batch['bindings']:
        key=(b['entity'],b['external_id']);h=row_hash(batch,b)
        if key in existing:
            old=existing[key]
            if old.row_sha256!=h or getattr(old,TARGET[b['entity']][0]+'_id')!=b['target_id']:raise Conflict('Змінено первинну прив’язку зовнішнього ID.')
            policy.check_reference(TARGET[b['entity']][0]+'_id',b['target_id']);binding_reused.append(b)
            continue
        try:
            obj=TARGET[b['entity']][1].objects.get(pk=b['target_id'])
            if ImportIdentity.objects.filter(namespace=batch['namespace'],**{TARGET[b['entity']][0]+'_id':obj.pk}).exists():raise Conflict('Запис уже має зовнішній ID у цьому джерелі.')
            policy.check_reference(TARGET[b['entity']][0]+'_id',obj.pk)
            if b['entity']=='counterparty' and (not obj.is_active or obj.type not in ('supplier','customer')):raise ValueError('Потрібен активний supplier/customer.')
            if b['entity']=='item' and (obj.method!='buy' or obj.kind not in ('product','material','component')):raise ValueError('Перший профіль підтримує каталог buy.')
            if b['entity']=='location' and obj.kind!='warehouse':raise ValueError('Потрібен склад warehouse.')
            refs[key]=obj;binds.append(b)
        except (ObjectDoesNotExist,ValueError) as exc:errors.append(error(b,'target_id',str(exc),'MISSING_REFERENCE',locators))
    for r in batch['rows']:
        key=(r['entity'],r['external_id'])
        if key in existing:
            if existing[key].row_sha256!=row_hash(batch,r):raise Conflict('Зовнішній ID уже має інший первинний зміст або склад позицій.')
            target=refs[key]
            if target is None:raise Conflict('Первинне джерело імпорту відсутнє.')
            policy.check_reference(TARGET[r['entity']][0]+'_id',target.pk);reused.append(r)
        else:new.append(r)
    def value(ref,field):
        if ref in refs:return getattr(refs[ref],field)
        return incoming[ref][field]
    for r in new:
        try:
            for field,entity in REFS.items():
                if field in r and (entity,r[field]) not in refs and (entity,r[field]) not in incoming:
                    raise ValueError('Недоступне посилання '+field)
            field_values(TARGET[r['entity']][1],{**r,**({'code':r['bos_code']} if 'bos_code' in r else {})})
            if 'bos_code' in r and TARGET[r['entity']][1].objects.filter(code=r['bos_code']).exists():raise Conflict('Код BoS уже існує. Оберіть явне зіставлення або інший код.')
            if 'item_ref' in r:
                key=('item',r['item_ref'])
                if value(key,'unit')!=r['unit'] or value(key,'revision')!=r['revision']:raise ValueError('Одиниця/версія не відповідає номенклатурі.')
                if value(key,'method')!='buy' or value(key,'kind') not in ('product','material','component'):raise ValueError('Нові рядки потребують чинного каталогу buy.')
            if 'location_ref' in r and value(('location',r['location_ref']),'kind')!='warehouse':raise ValueError('Нові залишки потребують чинного складу warehouse.')
            for field,kind in (('supplier_ref','supplier'),('customer_ref','customer')):
                if field in r and (value(('counterparty',r[field]),'type')!=kind or (('counterparty',r[field]) in refs and not refs[('counterparty',r[field])].is_active)):
                    raise ValueError('Тип або активність контрагента не відповідає операції.')
            if r['entity']=='sales_order':
                owner=Employee.objects.get(pk=r['owner_id'])
                if owner.archived_at is not None:raise ValueError('Відповідальний архівний.')
                if not any(x['entity']=='sales_line' and x['order_ref']==r['external_id'] for x in batch['rows']):raise ValueError('Замовлення потребує позицій.')
            if r['entity']=='sales_line':
                key=('sales_order',r['order_ref'])
                if key not in incoming:raise ValueError('Потрібна повна шапка цього пакета.')
                if key in existing:raise Conflict('Додавання позицій до імпортованого замовлення не підтримано.')
            if r['entity']=='item' and r['document'] is not None:checked_documents({'spec':r['document']},policy)
            checked_documents(r.get('documents',r.get('source_documents',{})),policy)
            if r['entity']=='opening_lot':
                item=refs.get(('item',r['item_ref']));location=refs.get(('location',r['location_ref']))
                if item and location and Lot.objects.filter(item=item,location=location).exists():raise Conflict('У групі номенклатура/склад уже є persisted партії: повторний зріз заборонено.')
        except (ObjectDoesNotExist,ValueError,KeyError) as exc:errors.append(error(r,'reference',str(exc),'MISSING_REFERENCE',locators))
    controls=source_totals(batch['rows'])
    if errors:raise InvalidBatch(errors)
    if controls!=batch['expected_source_control_totals']:raise InvalidBatch([error({},'expected_source_control_totals','Незалежні підсумки джерела не збігаються.','TOTALS_MISMATCH')])
    return dict(batch=batch,refs=refs,new=new,reused=reused,binds=binds,binding_reused=binding_reused,source_control_totals=controls,known=known,locators=locators)


def round_fraction(value):
    scaled=value*100;whole,rem=divmod(scaled.numerator,scaled.denominator)
    if rem*2>scaled.denominator or (rem*2==scaled.denominator and whole%2):whole+=1
    return D((1 if whole<0 else 0,tuple(int(c) for c in str(abs(whole))),-2))


@exact_arithmetic
def live_totals(p):
    money={c:{k:D(0) for k in ('inventory_raw_value','opening_movement_cost','sales_open_value','purchase_open_value')} for c in CURRENCIES};stock=[];groups=set()
    from .service import free,usable
    from .balances import sales_open,purchase_open
    for r in p['batch']['rows']:
        entity=r['entity'];obj=p['refs'].get((entity,r['external_id']))
        if entity=='opening_lot':
            item=p['refs'].get(('item',r['item_ref']));loc=p['refs'].get(('location',r['location_ref']))
            key=tuple(r[k] for k in ('item_ref','location_ref','unit','revision','currency'))
            if key in groups:continue
            groups.add(key);physical=D(0);available=D(0)
            if item and loc:
                for lot in Lot.objects.filter(item=item,location=loc,revision=r['revision'],currency=r['currency']).select_related('item'):
                    physical+=lot.quantity;available+=free(lot) if usable(lot) else D(0)
                    money[lot.currency]['inventory_raw_value']+=lot.quantity*lot.unit_cost
                    money[lot.currency]['opening_movement_cost']+=sum((m.cost for m in lot.movements.filter(kind='opening')),D(0))
            stock.append(dict(zip(('item_ref','location_ref','unit','revision','currency'),key),physical=format(physical,'.3f'),available=format(available,'.3f')))
        elif entity=='sales_line' and obj:
            money[obj.order.currency]['sales_open_value']+=round_fraction(Fraction(sales_open(obj))*Fraction(obj.price))
        elif entity=='purchase_open_balance' and obj:
            money[obj.currency]['purchase_open_value']+=round_fraction(Fraction(purchase_open(obj))*(Fraction(obj.price)+Fraction(obj.extras)/Fraction(obj.quantity)))
    return {'scope':'batch_targets_and_opening_groups','money':[dict(currency=c,**{k:format(v,'.5f' if k=='inventory_raw_value' else '.2f') for k,v in money[c].items()}) for c in CURRENCIES],
        'stock':sorted(stock,key=lambda r:tuple(r[k] for k in ('item_ref','location_ref','unit','revision','currency')))}


def mappings(p,preview=False):
    newkeys={(r['entity'],r['external_id']) for r in p['new']};out=[]
    for row in p['batch']['rows']:
        key=(row['entity'],row['external_id']);obj=p['refs'].get(key);new=key in newkeys
        out.append(dict(entity=row['entity'],external_id=row['external_id'],**p['locators'].get(key,{'row':None,'part':'json'}),
            decision='create' if new else 'reuse',target_model=TARGET[row['entity']][0],target_id=None if preview and new else obj.pk if obj else None,
            bos_code=row.get('bos_code',''),display_name=row.get('name',row.get('source_order_code',row['external_id']))))
    boundkeys={(r['entity'],r['external_id']) for r in p['binds']}
    for row in p['batch']['bindings']:
        key=(row['entity'],row['external_id']);obj=p['refs'][key]
        out.append(dict(entity=row['entity'],external_id=row['external_id'],row=None,part='bindings',decision='bind' if key in boundkeys else 'reuse',
            target_model=TARGET[row['entity']][0],target_id=obj.pk,bos_code=getattr(obj,'code',''),display_name=obj.name))
    return out




@exact_arithmetic
def apply_batch(batch,context,phase):
    a=assert_authority(context,'batch',semantic(batch),phase);
    if phase not in ('preview','apply'):raise PermissionError('Невідома фаза імпорту.')
    p=a['row'];principal=a['principal'];phase=a['phase'];refs=p['refs']
    from .service import dispatch
    def run(action,values,ctx=None):return dispatch({'action':'erp_'+action,**values},role='ceo',log=False,import_context=ctx,import_phase=phase)
    record=ImportBatch.objects.create(id=batch['batch_id'],namespace=batch['namespace'],cutover=batch['cutover'],semantic_sha256=semantic(batch),canonical_source=batch,source_part_sha256=p.get('parts',{}),actor_id=principal.user_id)
    def bind(row,obj):
        refs[(row['entity'],row['external_id'])]=obj
        return ImportIdentity.objects.create(namespace=batch['namespace'],entity=row['entity'],external_id=row['external_id'],row_sha256=row_hash(batch,row),source_row=row,first_batch=record,**{TARGET[row['entity']][0]:obj})
    for b in p['binds']:bind(b,refs[(b['entity'],b['external_id'])])
    for entity in ENTITIES:
        for r in [row for row in p['new'] if row['entity']==entity]:
            if entity=='sales_line':continue
            data={k:deepcopy(v) for k,v in r.items() if k not in ('entity','external_id')}
            if 'bos_code' in data:data['code']=data.pop('bos_code')
            if entity=='counterparty':
                obj=Counterparty(**data,is_active=True);obj.full_clean();obj.save(force_insert=True)
            elif entity=='item':
                doc=data.pop('document');data['document_id']=doc['document_id'] if doc else None
                obj=Item.objects.get(pk=run('item',data)['item_id'])
            elif entity=='location':obj=Location.objects.get(pk=run('location',data)['location_id'])
            elif entity=='opening_lot':
                data['item_id']=refs[('item',data.pop('item_ref'))].pk;data['location_id']=refs[('location',data.pop('location_ref'))].pk
                data.pop('unit');data['reason']=data['reason']+' · '+data.pop('source_reference');data['documents']={k:v['document_id'] for k,v in data['documents'].items()}
                obj=Lot.objects.get(pk=run('opening',data)['lot_id'])
            elif entity=='sales_order':
                lines=[x for x in batch['rows'] if x['entity']=='sales_line' and x['order_ref']==r['external_id']]
                data['customer_id']=refs[('counterparty',data.pop('customer_ref'))].pk;status=data.pop('source_status')
                data['lines']=[{'item_id':refs[('item',line['item_ref'])].pk,'quantity':line['quantity'],'price':line['price']} for line in lines]
                obj=SalesOrder.objects.get(pk=run('order',data)['order_id'])
                if status=='confirmed':run('confirm_order',{'order_id':obj.pk})
                for line,target in zip(lines,obj.lines.order_by('pk'),strict=True):bind(line,target)
            else:
                data={'code':r['bos_code'],'item_id':refs[('item',r['item_ref'])].pk,'supplier_id':refs[('counterparty',r['supplier_ref'])].pk,
                    'quantity':r['remaining_quantity'],'price':r['price'],'extras':r['remaining_extras'],'currency':r['currency'],'due_date':r['due_date'],'revision':r['revision']}
                with authority('purchase',digest(data),principal,phase,{'batch':batch,'source':r},parent=context) as ctx:
                    obj=Purchase.objects.get(pk=run('purchase',data,ctx)['purchase_id'])
            bind(r,obj)
    verify_created(p)
    return {'batch_id':str(record.pk)}


@exact_arithmetic
def prepare(request,raw,parts=None,locators_override=None):
    principal=actor(request)
    if principal.role!='ceo':raise PermissionError('Початковий імпорт доступний лише керівнику.')
    batch,locators,input_errors=normalize(raw,collect=True)
    if locators_override:locators=locators_override
    from .service import write_lock,dispatch
    with transaction.atomic():
        write_lock();locked_references(batch);principal=actor(request)
        if principal.role!='ceo':raise PermissionError('Повноваження змінилися.')
        if date.fromisoformat(batch['cutover'])>as_of():raise InvalidBatch([error({},'cutover','Дата зрізу не може бути в майбутньому.')])
        if input_errors:
            try:plan(batch,locators,Policy(request))
            except InvalidBatch as exc:input_errors.extend(exc.errors)
            except Conflict as exc:input_errors.append(error({},'batch',exc,'IDENTITY_CONFLICT'))
            raise InvalidBatch(input_errors)
        p=plan(batch,locators,Policy(request));p['parts']=parts or {};token=fingerprint();before=live_totals(p);delta=source_totals(p['new'])
        if p['known'] is None:
            with authority('batch',semantic(batch),principal,'preview',p) as ctx:
                dispatch({'action':'erp_import_batch','batch':batch},role='ceo',log=False,import_context=ctx,import_phase='preview')
        after=live_totals(p);mapping=mappings(p,preview=True);first=deepcopy(p['known'].receipt) if p['known'] else None
        transaction.set_rollback(True)
    if not request.session.session_key:request.session.create()
    proposal=ActionProposal.objects.create(session_key=request.session.session_key,user_id=principal.user_id,role='ceo',
        payload={'action':'erp_import_batch','batch':batch,'source_part_sha256':parts or {}},fingerprint=token,expires_at=timezone.now()+timedelta(minutes=10))
    return dict(valid=True,batch_id=batch['batch_id'],namespace=batch['namespace'],semantic_sha256=semantic(batch),errors=[],warnings=[],
        counts={'create':len(p['new']),'reuse':len(p['reused'])+len(p['binding_reused']),'bind':len(p['binds'])},mappings=mapping,
        source_control_totals=p['source_control_totals'],planned_delta=delta,live_before=before,projected_after=after,
        proposal={'id':str(proposal.pk),'expires_at':proposal.expires_at.isoformat()},first_commit_receipt=first)


@exact_arithmetic
def confirm_batch(request,payload):
    principal=actor(request)
    if principal.role!='ceo':raise PermissionError('Імпорт погоджує тільки керівник.')
    batch,locators=normalize(payload['batch']);locked_references(batch);p=plan(batch,locators,Policy(request));p['parts']=payload.get('source_part_sha256',{})
    if p['known']:
        if not p['known'].receipt:raise Conflict('Незавершений імпорт.')
        return p['known'].receipt
    before=live_totals(p);delta=source_totals(p['new'])
    from .service import dispatch
    with authority('batch',semantic(batch),principal,'apply',p) as ctx:
        dispatch({'action':'erp_import_batch','batch':batch},role='ceo',log=False,import_context=ctx,import_phase='apply')
    result=dict(state='succeeded',batch_id=batch['batch_id'],namespace=batch['namespace'],semantic_sha256=semantic(batch),
        counts={'create':len(p['new']),'reuse':len(p['reused'])+len(p['binding_reused']),'bind':len(p['binds'])},mappings=mappings(p),source_control_totals=p['source_control_totals'],
        committed_delta=delta,live_before=before,live_after=live_totals(p),impact={'title':'Початковий імпорт','changes':[]})
    event=Event.objects.create(action='erp_import_batch',payload=payload,result=result,role='ceo');result['erp_event_id']=event.pk
    event.result=result;event.save(update_fields=['result']);ImportBatch.objects.filter(pk=batch['batch_id']).update(receipt=result)
    return result


def verify_created(p):
    """Read actual persisted rows before commit; never trust dispatch's receipt."""
    for r in p['new']:
        entity=r['entity'];obj=p['refs'][(entity,r['external_id'])];obj.refresh_from_db()
        wanted={}
        if entity=='counterparty':wanted={k:r[k] for k in ('name','type','edrpou','phone','email','address')}
        elif entity=='item':wanted={k:r[k] for k in ('name','unit','kind','method','revision','currency','minimum','planned_cost','material','lead_days','required_documents')};wanted.update(code=r['bos_code'],document_id=r['document']['document_id'] if r['document'] else None)
        elif entity=='location':wanted=dict(code=r['bos_code'],name=r['name'],kind='warehouse')
        elif entity=='opening_lot':
            wanted=dict(code=r['bos_code'],quantity=r['quantity'],unit_cost=r['unit_cost'],currency=r['currency'],revision=r['revision'],quality='pending',item_id=p['refs'][('item',r['item_ref'])].pk,location_id=p['refs'][('location',r['location_ref'])].pk)
            movements=list(obj.movements.all())
            if len(movements)!=1 or movements[0].kind!='opening' or movements[0].quantity!=D(r['quantity']) or movements[0].cost!=round_fraction(Fraction(D(r['quantity']))*Fraction(D(r['unit_cost']))):raise ValueError('Фактичний початковий рух не відповідає джерелу.')
        elif entity=='sales_order':wanted=dict(code=r['bos_code'],customer_id=p['refs'][('counterparty',r['customer_ref'])].pk,owner_id=r['owner_id'],due_date=date.fromisoformat(r['due_date']),currency=r['currency'],status=r['source_status'])
        elif entity=='sales_line':wanted=dict(order_id=p['refs'][('sales_order',r['order_ref'])].pk,item_id=p['refs'][('item',r['item_ref'])].pk,revision=r['revision'],quantity=r['quantity'],price=r['price'],shipped=D(0),invoiced=D(0))
        elif entity=='purchase_open_balance':
            wanted=dict(code=r['bos_code'],item_id=p['refs'][('item',r['item_ref'])].pk,supplier_id=p['refs'][('counterparty',r['supplier_ref'])].pk,quantity=r['remaining_quantity'],received=D(0),price=r['price'],extras=r['remaining_extras'],currency=r['currency'],revision=r['revision'],due_date=date.fromisoformat(r['due_date']),original_due=date.fromisoformat(r['original_due']),status='ordered',quote_id=None,request_id=None,production_id=None)
            if obj.approval_snapshot.get('row_sha256')!=row_hash(p['batch'],r) or obj.approval_snapshot.get('source')!='imported_open_balance' or obj.movement_set.exists():raise ValueError('Фактичний залишковий PO або його джерело не відповідають зрізу.')
        for key,value in wanted.items():
            actual=getattr(obj,key)
            if isinstance(actual,D):value=D(value)
            if actual!=value:raise ValueError('Фактичний запис не відповідає погодженому джерелу: '+entity+'.'+key)
        identity=ImportIdentity.objects.get(namespace=p['batch']['namespace'],entity=entity,external_id=r['external_id'])
        if identity.row_sha256!=row_hash(p['batch'],r) or getattr(identity,TARGET[entity][0]+'_id')!=obj.pk:raise ValueError('Журнал зовнішніх ID не відповідає фактичному запису.')


def validate_controls(value):
    try:
        if not isinstance(value,dict) or set(value)!={'counts','money','stock'}:raise ValueError('Потрібні counts/money/stock.')
        counts=value['counts']
        if not isinstance(counts,dict) or set(counts)!=set(ENTITIES) or any(type(n) is not int or not 0<=n<=100 for n in counts.values()):raise ValueError('Контрольні counts мають бути цілими числами, не bool/float.')
        if not isinstance(value['money'],list) or len(value['money'])!=3:raise ValueError('Потрібні три валюти.')
        for currency,row in zip(CURRENCIES,value['money'],strict=True):
            if not isinstance(row,dict) or set(row)!={'currency',*MONEY_KEYS} or row['currency']!=currency:raise ValueError('Некоректні money keys/currency order.')
            for key in MONEY_KEYS:
                places=2 if key=='opening_movement_cost' else 5
                if not isinstance(row[key],str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.[0-9]{'+str(places)+'}',row[key]) or len(row[key])>32:raise ValueError('Потрібні точні canonical грошові рядки.')
        if not isinstance(value['stock'],list) or len(value['stock'])>100:raise ValueError('Неправильний stock controls.')
        keys=[]
        for row in value['stock']:
            if not isinstance(row,dict) or set(row)!={'item_ref','location_ref','unit','revision','currency','quantity'}:raise ValueError('Некоректний stock group.')
            for key in ('item_ref','location_ref'):external(row[key])
            external(row['unit'],20);external(row['revision'],40)
            if row['currency'] not in CURRENCIES or decimal(row['quantity'],3)!=row['quantity']:raise ValueError('Некоректна stock quantity/currency.')
            keys.append(tuple(row[k] for k in ('item_ref','location_ref','unit','revision','currency')))
        if keys!=sorted(set(keys)):raise ValueError('Stock groups мають бути унікальні й відсортовані.')
    except (ValueError,TypeError,KeyError) as exc:raise InvalidBatch([error({},'expected_source_control_totals',exc)],422)
