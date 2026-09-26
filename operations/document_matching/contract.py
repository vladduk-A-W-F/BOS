"""Bounded DTO validation for an explicitly synthetic, non-writing contract.

The caller must obtain a complete admitted context through Policy and verify the
original bytes. DTO validation proves neither authorization nor file integrity.
Extracted values remain verbatim; normalization belongs only in comparisons.
"""
from datetime import date
from decimal import Context, Decimal, localcontext, ROUND_HALF_EVEN
import re

SCHEMA = 'bos.document-match.v1'
PROVIDER = 'mock.synthetic-invoice.v1'
MARKER = 'BOS SYNTHETIC SUPPLIER INVOICE V1'
MAX_ID = 9007199254740991
SHA = re.compile(r'[0-9a-f]{64}\Z')
IDENTITY_KEYS = {'document_id', 'code', 'revision', 'sha256'}
HEADER_FIELDS = ('supplier_edrpou', 'invoice_number', 'invoice_date', 'currency', 'tax_basis', 'total')
LINE_FIELDS = ('item_code', 'revision', 'unit', 'quantity', 'unit_price', 'line_total')


class ContractError(ValueError):
    """Safe structural code; never include supplied private data in the error."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise ContractError(code)


def shape(value, keys):
    require(type(value) is dict and set(value) == set(keys), 'invalid_shape')


def text(value, maximum=200, *, blank=False):
    require(type(value) is str and (blank or bool(value)) and len(value) <= maximum,
            'invalid_text')
    require('\x00' not in value and not any(0xD800 <= ord(c) <= 0xDFFF for c in value), 'invalid_text')
    return value


def identity(value):
    shape(value, IDENTITY_KEYS)
    positive_id(value['document_id'])
    text(value['code'], 80)
    text(value['revision'], 40)
    require(type(value['sha256']) is str and SHA.fullmatch(value['sha256']), 'invalid_sha256')
    return value


def positive_id(value):
    require(type(value) is int and 0 < value <= MAX_ID, 'invalid_id')
    return value


def decimal(value, *, places, positive=False, total=False):
    require(type(value) is str and len(value) <= 32, 'invalid_decimal')
    require(re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]{1,' + str(places) + r'})?', value),
            'invalid_decimal')
    number = Decimal(value)
    maximum = Decimal('9999999999999.99') if total else Decimal('1000000000')
    require(number <= maximum and (not positive or number > 0), 'decimal_range')
    return number


def formatted(number, places):
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        return format(number.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN), 'f')


def source(value):
    shape(value, IDENTITY_KEYS | {'status', 'sections'})
    identity({key: value[key] for key in IDENTITY_KEYS})
    require(value['status'] in ('needs_review', 'approved', 'ocr_required'), 'invalid_source_status')
    require(type(value['sections']) is list and len(value['sections']) <= 100, 'invalid_sections')
    size = 0
    for section in value['sections']:
        shape(section, {'source', 'text'})
        text(section['source'], 120)
        text(section['text'], 500000, blank=True)
        size += len(section['text'])
    require(size <= 500000, 'source_too_large')
    return value


def source_identity(value):
    return {key: value[key] for key in sorted(IDENTITY_KEYS)}


def claim(value, supplied_source):
    shape(value, {'value', 'evidence'})
    text(value['value'], 200)
    evidence = value['evidence']
    shape(evidence, {'page', 'source', 'start', 'end', 'quote', 'source_sha256'})
    require(type(evidence['page']) is int and 1 <= evidence['page'] <= len(supplied_source['sections']),
            'invalid_evidence')
    section = supplied_source['sections'][evidence['page'] - 1]
    start, end = evidence['start'], evidence['end']
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(section['text'])
            and end - start <= 200, 'invalid_evidence')
    require(evidence['source'] == section['source'] and evidence['source_sha256'] == supplied_source['sha256']
            and evidence['quote'] == section['text'][start:end] == value['value'], 'evidence_mismatch')


def draft(value, supplied_source):
    source(supplied_source)
    shape(value, {'schema', 'provider', 'source', 'state', 'fields', 'exceptions'})
    require(value['schema'] == SCHEMA and value['provider'] == PROVIDER, 'invalid_provider')
    identity(value['source'])
    require(value['source'] == source_identity(supplied_source), 'source_changed')
    require(value['state'] in ('extracted', 'needs_information'), 'invalid_draft_state')
    require(type(value['exceptions']) is list and len(value['exceptions']) <= 20, 'invalid_exceptions')
    allowed = {'ocr_required', 'unsupported_document', 'unsupported_multi_line', 'ambiguous_field', 'missing_field'}
    require(all(type(code) is str and code in allowed for code in value['exceptions']), 'invalid_exceptions')
    if value['state'] == 'needs_information':
        require(value['fields'] is None and bool(value['exceptions']), 'invalid_draft_state')
        return value
    require(not value['exceptions'] and supplied_source['status'] != 'ocr_required', 'invalid_draft_state')
    require(any(MARKER in section['text'].splitlines() for section in supplied_source['sections']), 'unsupported_document')
    fields = value['fields']
    shape(fields, set(HEADER_FIELDS) | {'lines'})
    require(type(fields['lines']) is list and len(fields['lines']) == 1, 'unsupported_multi_line')
    for key in HEADER_FIELDS:
        claim(fields[key], supplied_source)
    line = fields['lines'][0]
    shape(line, set(LINE_FIELDS) | {'ordinal'})
    require(type(line['ordinal']) is int and line['ordinal'] == 1, 'invalid_ordinal')
    for key in LINE_FIELDS:
        claim(line[key], supplied_source)
    require(re.fullmatch(r'[0-9]{8,10}', fields['supplier_edrpou']['value']), 'invalid_supplier_code')
    text(fields['invoice_number']['value'], 60)
    raw_date = fields['invoice_date']['value']
    require(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', raw_date), 'invalid_date')
    try:
        date.fromisoformat(raw_date)
    except ValueError:
        raise ContractError('invalid_date') from None
    require(fields['currency']['value'] in ('EUR', 'USD', 'UAH'), 'invalid_currency')
    text(fields['tax_basis']['value'], 30)
    for key, maximum in (('item_code', 60), ('revision', 40), ('unit', 20)):
        text(line[key]['value'], maximum)
    decimal(line['quantity']['value'], places=3, positive=True)
    decimal(line['unit_price']['value'], places=2)
    decimal(line['line_total']['value'], places=2, total=True)
    decimal(fields['total']['value'], places=2, total=True)
    return value


def context(value):
    shape(value, {'access', 'source', 'suppliers', 'items', 'selection', 'purchase', 'receipts'})
    require(value['access'] in ('admitted', 'restricted'), 'invalid_access_context')
    if value['access'] == 'restricted':
        return value
    source(value['source'])
    shape(value['selection'], {'supplier_id', 'item_id', 'purchase_id'})
    for selected in value['selection'].values():
        if selected is not None:
            positive_id(selected)
    for name, keys in (('suppliers', {'id', 'name', 'edrpou', 'type', 'is_active'}),
                       ('items', {'id', 'code', 'revision', 'unit'}),
                       ('receipts', {'id', 'purchase_id', 'item_id', 'revision', 'unit', 'currency', 'quantity', 'returned_quantity'})):
        rows = value[name]
        require(type(rows) is list and len(rows) <= 100, 'invalid_context_rows')
        ids = set()
        for row in rows:
            shape(row, keys)
            positive_id(row['id'])
            require(row['id'] not in ids, 'duplicate_' + name + '_id')
            ids.add(row['id'])
            if name == 'suppliers':
                text(row['name'], 200)
                text(row['edrpou'], 20, blank=True)
                text(row['type'], 20)
                require(type(row['is_active']) is bool, 'invalid_boolean')
            elif name == 'items':
                text(row['code'], 60); text(row['revision'], 40); text(row['unit'], 20)
            else:
                positive_id(row['purchase_id']); positive_id(row['item_id'])
                text(row['revision'], 40); text(row['unit'], 20)
                require(row['currency'] in ('EUR', 'USD', 'UAH'), 'invalid_currency')
                quantity = decimal(row['quantity'], places=3, positive=True)
                returned = decimal(row['returned_quantity'], places=3)
                require(returned <= quantity, 'invalid_return_quantity')
    purchase = value['purchase']
    if purchase is not None:
        shape(purchase, {'id', 'code', 'supplier_id', 'item_id', 'revision', 'unit', 'currency', 'quantity', 'price', 'extras'})
        for key in ('id', 'supplier_id', 'item_id'):
            positive_id(purchase[key])
        for key, maximum in (('code', 60), ('revision', 40), ('unit', 20)):
            text(purchase[key], maximum)
        require(purchase['currency'] in ('EUR', 'USD', 'UAH'), 'invalid_currency')
        decimal(purchase['quantity'], places=3, positive=True)
        decimal(purchase['price'], places=2)
        decimal(purchase['extras'], places=2)
    return value
