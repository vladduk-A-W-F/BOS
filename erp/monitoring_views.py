"""Read-only BoS 4 monitoring API over Policy-scoped rows."""
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from boss_project.policy import Policy
from operations.views import errors
from . import monitoring
from .network_views import identity_errors


@identity_errors
@errors
@require_GET
def overview(request):
    return JsonResponse(monitoring.build(Policy(request)))


@identity_errors
@errors
@require_GET
def standard_query(request, key):
    return JsonResponse(monitoring.query(Policy(request), key))


@require_GET
def showcase(request):
    """Public first screen: only the synthetic demo cases of a demo database."""
    from django.conf import settings
    from operations.models import Configuration
    from training.access import enabled
    cases = Configuration.objects.filter(key='demo_cases').first()
    if (settings.BOS_DATA_MODE != 'demo' or enabled() or cases is None
            or not isinstance(cases.value, dict) or cases.value.get('synthetic') is not True):
        return JsonResponse({'cases': []})
    company = Configuration.objects.filter(key='organization').first()
    name = company.value.get('name', '') if company and isinstance(company.value, dict) else ''
    return JsonResponse({'company': name, 'cases': cases.value.get('cases', [])})


@identity_errors
@errors
@require_GET
def document_links(request):
    """Documents attached to an order or invoice, or the records a document is attached to."""
    from .models import DocumentLink, Lot, SalesOrder
    policy = Policy(request)
    rows = DocumentLink.objects.select_related('document', 'order', 'invoice').filter(
        document__in=policy.documents()).order_by('-created_at', '-pk')
    if not policy.ceo:
        rows = rows.filter(invoice__isnull=True, order__in=policy.queryset(SalesOrder))
    keys = [k for k in ('order', 'invoice', 'document') if request.GET.get(k)]
    if len(keys) != 1:
        raise ValueError('Вкажіть один параметр: order, invoice або document.')
    rows = rows.filter(**{keys[0] + '_id': int(request.GET[keys[0]])})
    image = lambda d: (d.filename or '').rsplit('.', 1)[-1].lower() in ('png', 'jpg', 'jpeg')
    # The reverse of «attach to lot»: lots this exact document version is filed under (Lot.documents).
    lots = []
    if keys[0] == 'document':
        doc_id = int(request.GET['document'])
        if policy.documents().filter(pk=doc_id).exists():
            for lot in policy.queryset(Lot).exclude(documents={}).order_by('code').only('id', 'code', 'documents'):
                lots += [{'id': lot.pk, 'code': lot.code, 'kind': kind}
                         for kind, value in lot.documents.items() if value == doc_id]
    return JsonResponse({'lots': lots[:50], 'links': [{
        'id': x.pk, 'note': x.note, 'created_at': x.created_at.isoformat(),
        'document': {'id': x.document_id, 'code': x.document.code, 'revision': x.document.revision,
                     'title': x.document.title, 'status': x.document.status, 'image': image(x.document)},
        'order': {'id': x.order_id, 'code': x.order.code} if x.order_id else None,
        'invoice': {'id': x.invoice_id, 'code': x.invoice.code} if x.invoice_id else None,
    } for x in rows[:200]]})
