"""CEO-only statement surfaces; private originals are committed before proposals."""
import io
from functools import wraps
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_GET,require_POST
from boss_project.identity import actor,IdentityDenied
from boss_project.policy import Policy
from operations.models import Document
from operations.private_storage import private_document_storage,legacy_blob_usage
from operations.views import errors,doc_dict
from .statement_csv import FORMAT,PARSER_VERSION,MAX_BODY,MAX_FILE,parse,marker,safe_text,StatementError


def pre_body(request):
    """Called after authentication middleware, before any CSRF body parsing."""
    if not(request.path.startswith('/api/statements/') or request.path.rstrip('/').removesuffix('.json')=='/api/transactions/summary'):return None
    try:
        principal=actor(request)
        if principal.role!='ceo':raise IdentityDenied('Виписки та грошові підсумки доступні лише керівнику.')
    except IdentityDenied as exc:return JsonResponse({'error':str(exc),'code':'identity_denied'},status=exc.status)
    if request.path!='/api/statements/sources/' or request.method!='POST':return None
    try:
        declared=request.META.get('CONTENT_LENGTH')
        if declared not in (None,'') and (not str(declared).isascii() or not str(declared).isdigit() or len(str(declared))>12):raise StatementError('Некоректна довжина запиту.',status=400)
        length=int(declared) if declared not in (None,'') else None
        if length is not None and length>MAX_BODY:raise StatementError('Запит перевищує 1 MiB + 64 KiB.',code='statement_size',status=413)
        if hasattr(request,'_body'):raw=request._body
        else:
            if getattr(request,'_read_started',False):raise StatementError('Тіло вже прочитано до перевірки.',status=400)
            raw=request.read(MAX_BODY+1)
        if len(raw)>MAX_BODY:raise StatementError('Запит перевищує 1 MiB + 64 KiB.',code='statement_size',status=413)
        if length is not None and len(raw)!=length:raise StatementError('Довжина потоку не збігається.',status=400)
        request._body=raw;request._stream=io.BytesIO(raw);request.META['CONTENT_LENGTH']=str(len(raw))
    except StatementError as exc:return JsonResponse({'error':str(exc),'code':exc.code},status=exc.status)
    return None


def ceo(fn):
    @wraps(fn)
    def wrapped(request,*args,**kwargs):
        if not Policy(request).ceo:raise PermissionError('Доступно лише керівнику.')
        return fn(request,*args,**kwargs)
    return wrapped

@require_POST
@errors
@ceo
def sources(request):
    if set(request.FILES)!= {'file'} or set(request.POST)!={'code','revision','title'} or any(len(request.FILES.getlist(k))!=1 for k in request.FILES) or any(len(request.POST.getlist(k))!=1 for k in request.POST):raise StatementError('Потрібні рівно file, code, revision, title.')
    file=request.FILES['file'];name=file.name
    safe_text(name,200,minimum=1)
    if not name.lower().endswith('.csv'):raise StatementError('Потрібен файл .csv.')
    code=safe_text(request.POST['code'],80,minimum=1);revision=safe_text(request.POST['revision'],40,minimum=1);title=safe_text(request.POST['title'],200,minimum=1)
    parsed=parse(file.read(MAX_FILE+1));receipt=None;committed=False
    def after_commit():
        nonlocal committed
        committed=True;private_document_storage.finalize(receipt)
    try:
        with transaction.atomic(durable=True):
            from erp.service import write_lock
            write_lock();p=Policy(request)
            if not p.ceo:raise PermissionError('Повноваження змінено.')
            old=list(Document.objects.filter(code=code))
            if any(d.access_level!='ceo' or marker(d) is None for d in old):raise StatementError('Код належить іншому виду документа.',code='statement_source_conflict',status=409)
            if any(d.revision==revision for d in old):raise StatementError('Ця версія вже існує. Перевірте точний checksum у джерелах.',code='statement_source_conflict',status=409)
            file.seek(0);raw=file.read(MAX_FILE+1)
            receipt=private_document_storage.save_verified(raw,parsed['checksum'],legacy_blob_bytes=legacy_blob_usage)
            summary={'kind':FORMAT,'format':FORMAT,'parser_version':PARSER_VERSION,'row_count':parsed['row_count'],'source_totals':parsed['source_totals'],'source':'Первинний CSV','text':f"Формат {FORMAT}; рядків: {parsed['row_count']}. Призначення платежів доступне лише у фінансовому розділі."}
            d=Document.objects.create(code=code,revision=revision,title=title,filename=name,access_level='ceo',status='needs_review',content=b'',original_file=receipt.name,size=receipt.size,checksum=parsed['checksum'],text=summary['text'],sections=[summary])
            response=JsonResponse({**doc_dict(d,p),'format':FORMAT,'parser_version':PARSER_VERSION,'row_count':parsed['row_count'],'source_totals':parsed['source_totals']},status=201)
            transaction.on_commit(after_commit)
    except BaseException:
        if receipt is not None and not committed:private_document_storage.discard_new(receipt)
        raise
    return response

@require_GET
@errors
@ceo
def imports(request):
    from .statement_reads import imports as read
    return JsonResponse(read(request))
@require_GET
@errors
@ceo
def import_detail(request,pk):
    from .statement_reads import import_detail as read
    return JsonResponse(read(request,pk))
@require_GET
@errors
@ceo
def export(request,pk):
    from .statement_reads import export as read
    return read(request,pk)
@require_GET
@errors
@ceo
def lines(request):
    from .statement_reads import lines as read
    return JsonResponse(read(request))
@require_GET
@errors
@ceo
def line_detail(request,pk):
    from .statement_reads import line_detail as read
    return JsonResponse(read(request,pk))
@require_GET
@errors
@ceo
def candidates(request,pk):
    from .statement_reads import candidates as read
    return JsonResponse(read(request,pk))
@require_GET
@errors
@ceo
def summary(request):
    from .statement_reads import summary as read
    return JsonResponse(read(request))
