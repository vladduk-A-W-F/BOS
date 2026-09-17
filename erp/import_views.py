"""CEO-only raw-byte input adapter for the bounded initial import."""
import csv,hashlib,io,json
from copy import deepcopy
from functools import wraps
from pathlib import Path
from uuid import uuid4
from datetime import timedelta

from django.http import JsonResponse
from django.views.decorators.http import require_GET,require_POST
from django.db import IntegrityError,OperationalError
from django.core.exceptions import ObjectDoesNotExist,ValidationError
from boss_project.identity import actor,IdentityDenied
from boss_project.data_rules import strict_json_loads
from operations.service import Conflict,as_of
from employees.models import Employee
from . import importing as imp
from .models import ImportBatch,ImportIdentity

MAX_BODY=160*1024
MAX_SOURCE=128*1024


def failure(errors,status=422):
    return JsonResponse(dict(valid=False,batch_id=None,namespace=None,semantic_sha256=None,proposal=None,
        errors=errors,warnings=[],counts={'create':0,'reuse':0,'bind':0},mappings=[],source_control_totals=None,
        planned_delta=None,live_before=None,projected_after=None,first_commit_receipt=None),status=status)


def guarded(fn):
    @wraps(fn)
    def wrapped(request,*args,**kwargs):
        try:
            if actor(request).role!='ceo':raise PermissionError('Початковий імпорт доступний тільки керівнику.')
            return fn(request,*args,**kwargs)
        except IdentityDenied as exc:return JsonResponse({'error':str(exc)},status=exc.status)
        except PermissionError as exc:return JsonResponse({'error':str(exc)},status=403)
        except imp.InvalidBatch as exc:return failure(exc.errors,exc.status)
        except (Conflict,IntegrityError,OperationalError):return failure([imp.error({},'batch','Дані або identity змінилися; потрібен новий перегляд.','IDENTITY_CONFLICT')],409)
        except ObjectDoesNotExist:return failure([imp.error({},'reference','Запис недоступний.','MISSING_REFERENCE')],404)
        except (ValueError,TypeError,KeyError,ValidationError,csv.Error) as exc:return failure([imp.error({},'batch',str(exc))],400)
    return wrapped


def decode(raw):
    return strict_json_loads(raw.decode('utf-8-sig'))


def read_input(request):
    try:length=int(request.META.get('CONTENT_LENGTH') or 0)
    except ValueError:length=0
    if length>MAX_BODY:raise imp.InvalidBatch([imp.error({},'file','Запит перевищує160KiB.')],413)
    raw=request._body if hasattr(request,'_body') else request.read(MAX_BODY+1)
    if len(raw)>MAX_BODY:raise imp.InvalidBatch([imp.error({},'file','Запит перевищує160KiB.')],413)
    if request.content_type=='application/json':
        if len(raw)>MAX_SOURCE:raise imp.InvalidBatch([imp.error({},'file','Джерело перевищує128KiB.')],413)
        return decode(raw),{'batch':hashlib.sha256(raw).hexdigest()},None
    if request.content_type!='multipart/form-data':raise ValueError('Потрібен JSON або multipart/form-data.')
    request._body=raw;request._stream=io.BytesIO(raw)
    files=request.FILES;form=request.POST;keys=set(files)|set(form);parts={}
    for key in keys:
        if len(files.getlist(key))+len(form.getlist(key))!=1:raise ValueError('Multipart part повторено.')
        parts[key]=files[key].read(MAX_SOURCE+1) if key in files else form[key].encode('utf-8')
    if sum(map(len,parts.values()))>MAX_SOURCE:raise imp.InvalidBatch([imp.error({},'file','Сума manifest/files перевищує128KiB.')],413)
    hashes={k:hashlib.sha256(v).hexdigest() for k,v in parts.items()}
    extra=decode(parts.pop('bindings')) if 'bindings' in parts else []
    if not isinstance(extra,list):raise ValueError('bindings має бути JSON array.')
    if 'batch' in parts:
        if set(parts)!={'batch'}:raise ValueError('batch не можна змішувати з manifest/CSV.')
        value=decode(parts['batch'])
        if not isinstance(value,dict) or not isinstance(value.get('bindings'),list):raise ValueError('Некоректний batch.')
        value['bindings']+=extra;return value,hashes,None
    if 'manifest' not in parts:raise ValueError('Потрібен manifest або batch.')
    value=decode(parts.pop('manifest'))
    if not isinstance(value,dict) or 'rows' in value or not isinstance(value.get('csv_files'),list):raise ValueError('Потрібен CSV manifest.')
    specs=value.pop('csv_files');rows=[];locators={};wanted=set();entities=set()
    for spec in specs:
        if not isinstance(spec,dict) or set(spec)!={'entity','part'} or spec['entity'] not in imp.ENTITIES or spec['part']!='rows_'+spec['entity']:raise ValueError('Невідомий CSV part.')
        entity,part=spec['entity'],spec['part']
        if part in wanted or entity in entities:raise ValueError('Повторний CSV part.')
        wanted.add(part);entities.add(entity)
        if part not in parts:raise ValueError('Відсутній CSV part.')
        reader=csv.reader(io.StringIO(parts[part].decode('utf-8-sig'),newline=''),strict=True)
        try:headers=next(reader)
        except StopIteration:raise ValueError('Порожній CSV без header.')
        required=set(imp.REQUIRED[entity].split())|{'external_id'};allowed=required|set(imp.DEFAULTS[entity])
        if len(headers)!=len(set(headers)) or set(headers)-allowed or not required<=set(headers):
            raise imp.InvalidBatch([imp.error({'entity':entity},'header','Повторні, невідомі або відсутні заголовки.','DUPLICATE_HEADER')])
        for index,values in enumerate(reader,2):
            if len(values)!=len(headers):raise ValueError('CSV має зайві або відсутні cells.')
            row={'entity':entity}
            for key,text in zip(headers,values):
                if text=='' and key in imp.DEFAULTS[entity]:continue
                if key in ('document','required_documents','documents','source_documents'):row[key]=decode(text.encode())
                elif key in ('owner_id','lead_days'):
                    if not text.isdigit():raise ValueError('CSV ID/lead_days потребує цілого числа.')
                    row[key]=int(text)
                else:row[key]=text
            rows.append(row);locators[(entity,row.get('external_id'))]={'row':index,'part':part}
    if wanted!=set(parts):raise ValueError('Невідомі додаткові CSV parts.')
    if not isinstance(value.get('bindings'),list):raise ValueError('bindings має бути array.')
    value['bindings']+=extra;value['rows']=rows
    return value,hashes,locators


@require_POST
@guarded
def preview(request):
    raw,hashes,locators=read_input(request)
    return JsonResponse(imp.prepare(request,raw,parts=hashes,locators_override=locators))


def template_batch(owner_id):
    owner=Employee.objects.get(pk=owner_id)
    if owner.archived_at is not None:raise ValueError('Відповідальний архівний.')
    data=json.loads((Path(__file__).parent/'seed'/'initial_import_ua.json').read_text())
    token=uuid4();data['batch_id']=str(token);data['namespace']='demo-'+token.hex[:12];data['cutover']=str(as_of())
    for row in data['rows']:
        if 'bos_code' in row:row['bos_code']=row['bos_code'].replace('B02-A-','IMP-'+token.hex[:8]+'-')
        if row['entity']=='sales_order':row['owner_id']=owner.pk;row['due_date']=str(as_of()+timedelta(days=19))
        if row['entity']=='purchase_open_balance':row['due_date']=row['original_due']=str(as_of()-timedelta(days=11))
    return data


@require_GET
@guarded
def template(request):
    if set(request.GET)-{'owner_id','format'}:raise ValueError('Невідомі параметри шаблону.')
    data=template_batch(int(request.GET['owner_id']));fmt=request.GET.get('format','json')
    if fmt=='json':return JsonResponse(data,json_dumps_params={'ensure_ascii':False,'indent':2})
    if fmt!='csv':raise ValueError('Потрібен format json/csv.')
    manifest=deepcopy(data);rows=manifest.pop('rows');manifest['csv_files']=[];files=[]
    for entity in imp.ENTITIES:
        selected=[r for r in rows if r['entity']==entity]
        if not selected:continue
        headers=sorted({k for row in selected for k in row if k!='entity'});stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=headers);writer.writeheader()
        for row in selected:writer.writerow({k:json.dumps(row[k],ensure_ascii=False) if isinstance(row[k],(dict,list)) or row[k] is None else row[k] for k in headers if k in row})
        part='rows_'+entity;manifest['csv_files'].append(dict(entity=entity,part=part));files.append(dict(part=part,filename=part+'.csv',content_utf8=stream.getvalue()))
    return JsonResponse(dict(manifest=manifest,files=files),json_dumps_params={'ensure_ascii':False})


@require_GET
@guarded
def batch_detail(request,batch_id):
    record=ImportBatch.objects.get(pk=batch_id)
    targets=[]
    wanted={(row['entity'],row['external_id']) for row in record.canonical_source['rows']+record.canonical_source['bindings']}
    for identity in ImportIdentity.objects.filter(namespace=record.namespace).order_by('entity','external_id'):
        if (identity.entity,identity.external_id) not in wanted:continue
        model=imp.TARGET[identity.entity][0];obj=getattr(identity,model)
        targets.append(dict(entity=identity.entity,external_id=identity.external_id,target_model=model,target_id=obj.pk))
    return JsonResponse(dict(first_commit_receipt=record.receipt,current_targets=targets))


@require_GET
@guarded
def export(request,batch_id):
    record=ImportBatch.objects.get(pk=batch_id)
    data=dict(format='bos.initial-import.receipt.v1',batch_id=str(record.pk),namespace=record.namespace,cutover=str(record.cutover),semantic_sha256=record.semantic_sha256,
        source_part_sha256=record.source_part_sha256,canonical_source=record.canonical_source,first_commit_receipt=record.receipt)
    response=JsonResponse(data,json_dumps_params={'ensure_ascii':False,'indent':2});response['Content-Disposition']='attachment; filename="BoS_import_'+str(record.pk)+'.json"';return response
