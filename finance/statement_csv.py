"""Strict, bounded and deterministic CSV input; no database or inferred matching."""
import csv,hashlib,io,json,re
from datetime import date
from decimal import Decimal,localcontext

FORMAT='bos_statement_csv_v1'
PARSER_VERSION='1'
MAX_FILE=1024*1024
MAX_BODY=MAX_FILE+64*1024
CURRENCIES=('EUR','UAH','USD')
COLUMNS=('external_id','booking_date','direction','amount','currency','counterparty_external_id','invoice_reference','purpose')

class StatementError(ValueError):
    def __init__(self,message,*,code='statement_invalid',status=422,errors=None):
        super().__init__(message);self.code=code;self.status=status;self.errors=errors or []


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def safe_text(value,maximum,*,minimum=0,edges=False,multiline=False):
    if not isinstance(value,str) or not minimum<=len(value)<=maximum:raise ValueError('Некоректна довжина тексту.')
    if not edges and value!=value.strip():raise ValueError('Крайні пробіли не допускаються.')
    if any((ord(c)<32 and not(multiline and c in '\r\n\t')) or 0x7f<=ord(c)<=0x9f or 0xd800<=ord(c)<=0xdfff for c in value):raise ValueError('Керівні символи не допускаються.')
    return value


def money(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,2})?',value) or len(value.lstrip('0'))>16:raise ValueError('Потрібна додатна сума з максимум двома десятковими знаками.')
    amount=Decimal(value)
    if not 0<amount<=Decimal('999999999999.99'):raise ValueError('Сума поза допустимим діапазоном.')
    return format(amount,'.2f')


def iso_date(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):raise ValueError('Потрібна календарна дата YYYY-MM-DD.')
    return date.fromisoformat(value).isoformat()


def account(source,account):
    if not isinstance(source,str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,47}',source):raise ValueError('Некоректний source_system.')
    if not isinstance(account,str) or not re.fullmatch(r'[A-Z0-9][A-Z0-9_.:-]{0,119}',account):raise ValueError('Некоректний account_ref.')
    return source,account


def _quotes(text):
    # csv.strict permits bare quotes in unquoted fields; reject those with the
    # exact logical record and physical line, preserving quoted newlines.
    state='start';physical=1;record=1;column=0;i=0
    def fail(message):
        raise StatementError('CSV не відповідає схемі.',code='statement_csv_invalid',errors=[{'record':record,'column':COLUMNS[column] if column<len(COLUMNS) else None,'code':'CSV_SYNTAX','message':message,'physical_end_line':physical}])
    while i<len(text):
        c=text[i]
        if state=='quoted':
            if c=='"':state='closed'
        elif state=='closed':
            if c=='"':state='quoted'
            elif c==',':state='start';column+=1
            elif c in '\r\n':state='start'
            else:fail('Символ після закритих лапок.')
        else:
            if c=='"':
                if state!='start':fail('Лапки всередині нецитованого поля.')
                state='quoted'
            elif c==',':state='start';column+=1
            elif c in '\r\n':state='start'
            else:state='plain'
        if c=='\r' and state!='quoted' and (i+1>=len(text) or text[i+1]!='\n'):fail('Потрібен LF або CRLF.')
        if c=='\n':
            physical+=1
            if state!='quoted':record+=1;column=0
        i+=1
    if state=='quoted':fail('Незакриті лапки.')


def totals(rows):
    with localcontext() as ctx:
        ctx.prec=50
        result=[]
        for currency in CURRENCIES:
            incoming=sum((Decimal(r['amount']) for r in rows if r['currency']==currency and r['direction']=='in'),Decimal(0))
            outgoing=sum((Decimal(r['amount']) for r in rows if r['currency']==currency and r['direction']=='out'),Decimal(0))
            result.append({'currency':currency,'in':format(incoming,'.2f'),'out':format(outgoing,'.2f'),'net':format(incoming-outgoing,'.2f')})
        return result


def parse(raw):
    if not isinstance(raw,bytes):raise StatementError('Потрібні первинні bytes.')
    if len(raw)>MAX_FILE:raise StatementError('CSV перевищує 1 MiB.',code='statement_size',status=413)
    errors=[];rows=[];record=1;physical=1
    try:
        text=raw.decode('utf-8-sig');_quotes(text)
        reader=csv.reader(io.StringIO(text,newline=''),strict=True)
        if tuple(next(reader,()))!=COLUMNS:raise csv.Error('Заголовок CSV має точно відповідати схемі.')
        seen=set()
        for record,values in enumerate(reader,2):
            physical=reader.line_num
            if record>1001:raise csv.Error('Допускається максимум 1000 рядків даних.')
            if len(values)!=len(COLUMNS):
                errors.append({'record':record,'column':None,'code':'FIELD_COUNT','message':'Потрібні рівно 8 полів; порожні записи заборонені.','physical_end_line':physical});continue
            row=dict(zip(COLUMNS,values));valid=True
            for name in COLUMNS:
                try:
                    v=row[name]
                    if name=='external_id':
                        safe_text(v,120,minimum=1)
                        if v in seen:raise ValueError('Повторний external_id у CSV.')
                        seen.add(v)
                    elif name=='booking_date':iso_date(v)
                    elif name=='direction':
                        if v not in ('in','out'):raise ValueError('Оберіть in або out.')
                    elif name=='amount':row[name]=money(v)
                    elif name=='currency':
                        if v not in CURRENCIES:raise ValueError('Оберіть EUR, UAH або USD.')
                    elif name=='purpose':safe_text(v,2000,edges=True,multiline=True)
                    else:safe_text(v,120)
                except ValueError as exc:
                    valid=False;errors.append({'record':record,'column':name,'code':'FIELD_VALUE','message':str(exc),'physical_end_line':physical})
            if valid:rows.append({**row,'record':record,'semantic_sha256':digest(row)})
        if record==1:errors.append({'record':2,'column':None,'code':'EMPTY','message':'CSV не містить рядків даних.'})
    except (UnicodeError,csv.Error) as exc:
        errors.append({'record':record,'column':None,'code':'CSV_SYNTAX','message':str(exc),'physical_end_line':physical})
    if errors:raise StatementError('CSV не відповідає схемі.',code='statement_csv_invalid',errors=errors)
    return {'rows':rows,'row_count':len(rows),'source_totals':totals(rows),'checksum':hashlib.sha256(raw).hexdigest()}


def marker(document):
    return next((s for s in document.sections if isinstance(s,dict) and s.get('kind')==FORMAT),None)
