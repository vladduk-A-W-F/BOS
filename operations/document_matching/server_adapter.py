"""CEO-only, read-only bridge to the explicitly synthetic v1 contract.

The original is verified and parsed on each read; cached document sections are
never evidence. Optimistic double-reading follows the existing read projections:
it detects observed changes, but is not an atomic snapshot or a posting command.
No client-supplied context, amounts, checksum or extracted sections are accepted.
"""
import hashlib
import io
import logging
import sys
import threading
from decimal import Context, Decimal, localcontext

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from boss_project.policy import Policy
from erp.models import GoodsReturn, Item, Lot, Movement, Purchase
from erp.order_trace import ReadStateChanged, digest, write_revision
from finance.models import Counterparty
from operations import documents
from operations.private_storage import PrivateFileError, verified_document_bytes
from . import contract as c
from .mock_adapter import extract_mock
from .reconcile import reconcile


LIMIT = 100


class _Refused(Exception):
    def __init__(self, code):
        self.code = code


def _empty(code):
    return {'schema': c.SCHEMA, 'provider': c.PROVIDER, 'source': None,
            'fields': None, 'matches': None, 'comparison': None,
            'exceptions': [code], 'decision': 'needs_information',
            'operation_proposal': None}


def _rows(queryset, *fields):
    rows = list(queryset.order_by('pk').values(*fields)[:LIMIT + 1])
    if len(rows) > LIMIT:
        raise _Refused('context_limit_exceeded')
    return rows


def _parse_original(original):
    if original.name.rsplit('.', 1)[-1].lower() != 'pdf':
        return documents.parse(original)
    try:
        import pypdf  # Load its parser modules before applying per-thread filters.
    except ImportError:
        return documents.parse(original)  # Existing parser supplies a safe error.
    thread_id = threading.get_ident()
    class PrivateParserLog(logging.Filter):
        def filter(self, record):
            # pypdf diagnostics can contain private bytes (e.g. invalid header).
            # Do not change global logging levels or silence other requests.
            return record.thread != thread_id
    guard = PrivateParserLog()
    loggers = [logging.getLogger(name) for name in tuple(sys.modules)
               if name == 'pypdf' or name.startswith('pypdf.')]
    for logger in loggers:
        logger.addFilter(guard)
    try:
        return documents.parse(original)
    finally:
        for logger in loggers:
            logger.removeFilter(guard)


def _receipts(policy, purchase):
    movements = _rows(policy.queryset(Movement).filter(purchase_id=purchase['id'],
        kind__in=('receipt', 'supplier_return')), 'id', 'lot_id', 'purchase_id',
        'quantity', 'kind', 'line_id', 'production_id')
    originals = {row['id']: row for row in movements if row['kind'] == 'receipt'}
    outgoing = {row['id']: row for row in movements if row['kind'] == 'supplier_return'}
    lots = {row['id']: row for row in _rows(policy.queryset(Lot).filter(
        pk__in={row['lot_id'] for row in movements}), 'id', 'item_id', 'revision', 'currency')}
    items = {row['id']: row for row in _rows(policy.queryset(Item).filter(
        pk__in={row['item_id'] for row in lots.values()}), 'id', 'unit')}
    returns = _rows(policy.queryset(GoodsReturn).filter(
        Q(source_id__in=originals) | Q(result_id__in=outgoing)),
        'id', 'direction', 'source_id', 'result_id', 'quantity', 'source_quantity',
        'currency', 'source_snapshot')
    returned = {pk: Decimal(0) for pk in originals}
    linked = set()
    for row in returns:
        source = originals.get(row['source_id'])
        result = outgoing.get(row['result_id'])
        snapshot = row['source_snapshot']
        if source is None or result is None or not isinstance(snapshot, dict):
            raise _Refused('inconsistent_receipt_history')
        lot = lots.get(source['lot_id'])
        expected = {'movement_id': source['id'], 'kind': 'receipt',
                    'lot_id': source['lot_id'], 'purchase_id': purchase['id'],
                    'item_id': lot['item_id'] if lot else None,
                    'revision': lot['revision'] if lot else None,
                    'currency': lot['currency'] if lot else None}
        if (row['direction'] != 'supplier' or lot is None
                or row['source_quantity'] != source['quantity']
                or row['currency'] != lot['currency']
                or result['quantity'] != -row['quantity']
                or result['lot_id'] != source['lot_id']
                or any(snapshot.get(key) != value for key, value in expected.items())
                or result['line_id'] is not None or result['production_id'] is not None):
            raise _Refused('inconsistent_receipt_history')
        returned[source['id']] += row['quantity']
        linked.add(result['id'])
    if linked != set(outgoing):
        # A legacy unallocated supplier return cannot silently disappear.
        raise _Refused('inconsistent_receipt_history')
    receipts = []
    for row in originals.values():
        lot = lots.get(row['lot_id'])
        item = items.get(lot['item_id']) if lot else None
        if (item is None or row['quantity'] <= 0 or returned[row['id']] > row['quantity']
                or row['line_id'] is not None or row['production_id'] is not None):
            raise _Refused('inconsistent_receipt_history')
        receipts.append({'id': row['id'], 'purchase_id': row['purchase_id'],
            'item_id': lot['item_id'], 'revision': lot['revision'], 'unit': item['unit'],
            'currency': lot['currency'], 'quantity': str(row['quantity']),
            'returned_quantity': str(returned[row['id']])})
    return receipts, (movements, lots, items, returns)


def _context(policy, source, draft, selection):
    context = {'access': 'admitted', 'source': source, 'selection': selection,
               'suppliers': [], 'items': [], 'purchase': None, 'receipts': []}
    if draft['state'] != 'extracted':
        return context, None
    fields = draft['fields']
    line = fields['lines'][0]
    context['suppliers'] = _rows(policy.queryset(Counterparty).filter(
        edrpou=fields['supplier_edrpou']['value'], type='supplier', is_active=True),
        'id', 'name', 'edrpou', 'type', 'is_active')
    context['items'] = _rows(policy.queryset(Item).filter(
        code=line['item_code']['value'], revision=line['revision']['value'],
        unit=line['unit']['value']), 'id', 'code', 'revision', 'unit')
    purchase_rows = _rows(policy.queryset(Purchase).filter(pk=selection['purchase_id']),
        'id', 'code', 'supplier_id', 'item_id', 'revision', 'currency',
        'quantity', 'price', 'extras', 'status') if selection['purchase_id'] else []
    dependencies = {'purchases': purchase_rows}
    if purchase_rows:
        raw = purchase_rows[0]
        units = _rows(policy.queryset(Item).filter(pk=raw['item_id']), 'id', 'unit')
        if not units:
            raise _Refused('selection_unavailable')
        context['purchase'] = {key: str(value) if isinstance(value, Decimal) else value
                               for key, value in raw.items() if key != 'status'}
        context['purchase']['unit'] = units[0]['unit']
        context['receipts'], dependencies['receipts'] = _receipts(policy, raw)
    return context, dependencies


def _collect(policy, document_id, selection):
    document = policy.document(document_id)
    # CEO v1 sees the complete Policy document set, including hidden successors.
    current = policy.documents().filter(code=document.code).order_by('-pk').values_list('pk', flat=True).first()
    state = {'document': {key: getattr(document, key) for key in
             ('pk', 'code', 'revision', 'filename', 'checksum', 'size', 'status', 'access_level')},
             'file': document.original_file.name, 'current': current}
    try:
        if current != document.pk:
            raise _Refused('source_not_current')
        if document.status not in ('approved', 'needs_review', 'ocr_required'):
            raise _Refused('unsupported_source_status')
        if document.size is not None and document.size > documents.MAX_BYTES:
            raise _Refused('source_limit_exceeded')
        try:
            raw = verified_document_bytes(document)
        except (PrivateFileError, OSError, ValueError):
            raise _Refused('source_unreadable') from None
        state['sha256'] = hashlib.sha256(raw).hexdigest()
        if state['sha256'] != document.checksum:
            raise _Refused('source_unreadable')
        if len(raw) > documents.MAX_BYTES:
            raise _Refused('source_limit_exceeded')
        original = io.BytesIO(raw)
        original.name = document.filename or document.code + '.txt'
        try:
            parsed = _parse_original(original)
        except (ValueError, OSError):
            raise _Refused('document_parse_failed') from None
        if parsed['checksum'] != state['sha256']:
            raise _Refused('source_unreadable')
        if len(parsed['sections']) > LIMIT or sum(len(row['text']) for row in parsed['sections']) > 500000:
            raise _Refused('source_limit_exceeded')
        source = {'document_id': document.pk, 'code': document.code, 'revision': document.revision,
                  'sha256': state['sha256'], 'sections': parsed['sections'],
                  'status': 'ocr_required' if parsed['status'] == 'ocr_required' else document.status}
        draft = extract_mock(source)
        context, state['dependencies'] = _context(policy, source, draft, selection)
        result = reconcile(draft, context)
        state['context'] = context
    except _Refused as exc:
        result = _empty(exc.code)
    except c.ContractError:
        result = _empty('invalid_source_data')
    state['result'] = result
    return result, digest(state)


def build(request, document_id, *, purchase_id=None, supplier_id=None, item_id=None):
    """Return a draft/explicit exception; never approve, confirm or write.

    Initial access denial raises PermissionError, missing documents raise
    ObjectDoesNotExist, invalid identifiers raise ContractError. A concurrent
    source/data/access change raises the existing neutral ReadStateChanged.
    """
    first = Policy(request)
    if not first.ceo:
        raise PermissionError('Це зіставлення доступне лише керівнику.')
    c.positive_id(document_id)
    selection = {'purchase_id': purchase_id, 'supplier_id': supplier_id, 'item_id': item_id}
    for value in selection.values():
        if value is not None:
            c.positive_id(value)
    access = first.access_revision()
    if getattr(request, 'bos_access_revision', access) != access:
        raise ReadStateChanged()
    before = write_revision()
    with localcontext(Context(prec=50)):
        result, first_digest = _collect(first, document_id, selection)
        middle = write_revision()
        try:
            second = Policy(request)
            if not second.ceo or second.access_revision() != access:
                raise ReadStateChanged()
            _, second_digest = _collect(second, document_id, selection)
            final = Policy(request)
            final_access = final.access_revision()
            if not final.ceo:
                raise ReadStateChanged()
        except (PermissionError, ObjectDoesNotExist):
            raise ReadStateChanged() from None
    after = write_revision()
    if before != middle or middle != after or first_digest != second_digest or final_access != access:
        raise ReadStateChanged()
    request.bos_access_revision = access
    return result
