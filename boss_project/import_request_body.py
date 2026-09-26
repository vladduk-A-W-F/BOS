"""Bound the new import input before Django CSRF can parse multipart bodies.

This reads only the stream presented by Django. HTTP framing rejected/truncated
by the WSGI server is outside this adapter; it never reads a raw client socket.
"""
import io
from django.http import JsonResponse

IMPORT_PATH='/api/erp/import/preview/'
MAX_BODY=160*1024


def capture_import_body(request):
    if request.path!=IMPORT_PATH or request.method!='POST':return None
    def reject(status,message):
        return JsonResponse({'valid':False,'proposal':None,'errors':[{'entity':None,'external_id':None,'row':None,'part':'request','field':'file','code':'BODY_LIMIT' if status==413 else 'BODY_FRAMING','message':message}]},status=status)
    declared=request.META.get('CONTENT_LENGTH')
    try:
        length=None if declared in (None,'') else int(declared)
        if length is not None and length<0:raise ValueError
    except (TypeError,ValueError):return reject(400,'Некоректна довжина запиту.')
    if length is not None and length>MAX_BODY:return reject(413,'Запит перевищує 160 KiB.')
    if hasattr(request,'_body'):
        raw=request._body
    else:
        if getattr(request,'_read_started',False):return reject(400,'Тіло імпорту вже прочитано до захисної перевірки.')
        raw=request.read(MAX_BODY+1)
    if len(raw)>MAX_BODY:return reject(413,'Запит перевищує 160 KiB.')
    if length is not None and length!=len(raw):return reject(400,'Заявлена та фактична довжина потоку не збігаються.')
    request._body=raw;request._stream=io.BytesIO(raw)
    request.META['CONTENT_LENGTH']=str(len(raw))
    return None
