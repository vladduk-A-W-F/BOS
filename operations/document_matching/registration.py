"""Server-built, source-bound supplier invoice registration.

The accepted record is deliberately narrow: it proves a matched supplier
document for a Purchase. It does not create a customer invoice, stock entry,
payment, payable, ledger posting, or approval of the original Document.
"""
import hashlib, json, re, unicodedata
from datetime import date
from django.db import transaction
from django.utils import timezone
from boss_project.policy import Policy
from erp.models import Event, GoodsReturn
from operations.models import ActionProposal, SupplierInvoiceRegistration
from . import commands
from .server_adapter import build
from erp.order_trace import ReadStateChanged


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()


def _invoice_number_key(value):
    """NFKC, trim, collapse whitespace and uppercase only for duplicate identity."""
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC',value).strip()).upper()


def prepare(request,payload):
    """Rebuild trusted extraction/match state from current original bytes."""
    intent=commands.clean(payload); policy=Policy(request)
    if not policy.ceo: raise PermissionError('Реєстрація рахунку доступна лише керівнику.')
    result=build(request,intent['document_id'],purchase_id=intent['purchase_id'],supplier_id=intent['supplier_id'],item_id=intent['item_id'])
    if result.get('decision')!='accept_draft': raise ValueError('Сверка рахунку більше не придатна до реєстрації.')
    source=result['source']; matches=result['matches']; fields=result['fields']
    if source['sha256'] != intent['source_sha256']:
        raise ValueError('Первинний файл змінився. Підготуйте новий перегляд.')
    if matches != {'supplier_candidate_ids':matches['supplier_candidate_ids'],'item_candidate_ids':matches['item_candidate_ids'],'supplier_id':intent['supplier_id'],'item_id':intent['item_id'],'purchase_id':intent['purchase_id'],'receipt_ids':matches['receipt_ids']}:
        raise ValueError('Вибір або контекст закупівлі змінився.')
    return_ids=sorted(GoodsReturn.objects.filter(direction='supplier',source_id__in=matches['receipt_ids']).values_list('id',flat=True))
    values={'supplier_id':intent['supplier_id'],'purchase_id':intent['purchase_id'],'document_id':intent['document_id'],
            'source_sha256':source['sha256'],'invoice_number':fields['invoice_number']['value'],
            'invoice_date':fields['invoice_date']['value'],'amount':fields['total']['value'],'currency':fields['currency']['value'],
            'receipt_ids':list(matches['receipt_ids']),'return_ids':return_ids}
    invoice_identity=_digest({'supplier_id':values['supplier_id'],'invoice_number_key':_invoice_number_key(values['invoice_number']),
                              'invoice_date':values['invoice_date']})
    identity=_digest({'purchase_id':values['purchase_id'],'invoice_identity_sha256':invoice_identity})
    semantic=_digest({'source_sha256':source['sha256'],'values':{k:v for k,v in values.items() if k!='document_id'},
                      'matches':matches,'comparison':result['comparison'],'returns':return_ids})
    context=_digest({'intent':intent,'source':source,'semantic_context_sha256':semantic})
    return {'intent':intent,'values':values,'identity_sha256':identity,'invoice_identity_sha256':invoice_identity,'context_sha256':context,'semantic_context_sha256':semantic,'access_revision':policy.access_revision()}


def preview_fingerprint(request,payload):
    return prepare(request,payload)['context_sha256']


def projection(request,purchase_id,document_id):
    policy=Policy(request)
    starting_access=policy.access_revision()
    expected_access=getattr(request,'bos_access_revision',starting_access)
    if not policy.ceo: raise PermissionError('Це зіставлення доступне лише керівнику.')
    if expected_access!=starting_access: raise ReadStateChanged()
    rows=[]
    for row in SupplierInvoiceRegistration.objects.filter(purchase_id=purchase_id).select_related('document','supplier'):
        current=policy.documents().filter(code=row.document.code).order_by('-pk').values_list('pk',flat=True).first()
        state='requires_revalidation'
        if current==row.document_id and row.document.checksum==row.source_sha256:
            try:
                fresh=prepare(request,{'action':commands.ACTION,'document_id':row.document_id,'purchase_id':row.purchase_id,
                    'supplier_id':row.supplier_id,'item_id':row.purchase.item_id,'source_sha256':row.source_sha256})
                state='registered' if fresh['semantic_context_sha256']==row.semantic_context_sha256 else 'requires_revalidation'
            except ValueError:
                state='requires_revalidation'
        rows.append({'id':row.id,'supplier_id':row.supplier_id,'purchase_id':row.purchase_id,'document_id':row.document_id,
                     'invoice_number':row.invoice_number,'invoice_date':str(row.invoice_date),'amount':str(row.amount),'currency':row.currency,
                     'receipt_ids':row.receipt_ids,'return_ids':row.return_ids,'status':state})
    final=Policy(request)
    if not final.ceo: raise PermissionError('Це зіставлення доступне лише керівнику.')
    if final.access_revision()!=starting_access: raise ReadStateChanged()
    return {'status':'matched' if rows and all(x['status']=='registered' for x in rows) else 'requires_revalidation' if rows else 'unregistered','items':rows}


def confirm(request,proposal):
    """Validate before any replay and atomically persist domain row, Event, receipt."""
    from operations.service import Conflict
    try:
        prepared=prepare(request,proposal.payload)
    except (ValueError,ReadStateChanged) as exc:
        from operations.service import Conflict
        raise Conflict('Джерело або контекст змінилися. Підготуйте новий перегляд.') from exc
    if proposal.expires_at < timezone.now() or proposal.fingerprint != prepared['context_sha256']:
        from operations.service import Conflict
        raise Conflict('Дані, права або строк погодження змінилися. Підготуйте новий перегляд.')
    existing=SupplierInvoiceRegistration.objects.filter(purchase_id=prepared['values']['purchase_id']).first()
    def validated_existing(row):
        try:
            accepted=prepare(request,{'action':commands.ACTION,'document_id':row.document_id,'purchase_id':row.purchase_id,
                'supplier_id':row.supplier_id,'item_id':row.purchase.item_id,'source_sha256':row.source_sha256})
        except (ValueError,ReadStateChanged) as exc:
            from operations.service import Conflict
            raise Conflict('Прийняте джерело або його контекст більше не актуальні; потрібна окрема корекція.') from exc
        if (row.source_sha256 != prepared['values']['source_sha256'] or row.semantic_context_sha256 != prepared['semantic_context_sha256']
                or accepted['semantic_context_sha256'] != row.semantic_context_sha256):
            from operations.service import Conflict
            raise Conflict('Цей рахунок уже зареєстровано з іншою перевіреною версією; історію не перезаписано.')
    if proposal.receipt:
        row=SupplierInvoiceRegistration.objects.filter(pk=proposal.receipt.get('supplier_invoice_registration_id')).first()
        if row is None: raise Conflict('Збережений результат неповний. Підготуйте новий перегляд.')
        validated_existing(row)
        return proposal.receipt
    if not ActionProposal.objects.filter(pk=proposal.pk,receipt__isnull=True).update(receipt={'state':'running'}):
        from operations.service import Conflict
        raise Conflict('Дія вже виконується. Повторіть запит.')
    proposal.refresh_from_db()
    if existing:
        validated_existing(existing)
        receipt={'state':'succeeded','action':commands.ACTION,'supplier_invoice_registration_id':existing.id,'purchase_id':existing.purchase_id,'invoice_matching_status':'matched','replayed':True}
        proposal.receipt=receipt;proposal.save(update_fields=['receipt']);return receipt
    duplicate=SupplierInvoiceRegistration.objects.filter(invoice_identity_sha256=prepared['invoice_identity_sha256']).first()
    if duplicate:
        from operations.service import Conflict
        raise Conflict('Цей рахунок постачальника вже зареєстровано для іншої закупівлі; виправлення потребує окремої команди.')
    values=prepared['values']
    event=Event.objects.create(action=commands.ACTION,payload=prepared['intent'],result={},role=Policy(request).role)
    row=SupplierInvoiceRegistration.objects.create(identity_sha256=prepared['identity_sha256'],invoice_identity_sha256=prepared['invoice_identity_sha256'],context_sha256=prepared['context_sha256'],semantic_context_sha256=prepared['semantic_context_sha256'],registered_by_id=Policy(request).actor.user_id,**values)
    receipt={'state':'succeeded','action':commands.ACTION,'supplier_invoice_registration_id':row.id,'purchase_id':row.purchase_id,'invoice_matching_status':'matched','erp_event_id':event.id,'replayed':False}
    event.result=receipt;event.save(update_fields=['result']);proposal.receipt=receipt;proposal.save(update_fields=['receipt'])
    return receipt
