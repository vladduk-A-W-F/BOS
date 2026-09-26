"""Extract one documented synthetic template from existing parser sections.

This is neither OCR nor a general supplier-invoice parser. No AI/API is invoked.
Values and evidence are exact substrings of supplied page text, never normalized.
"""
import re

from . import contract as c

LABELS = {
    'Supplier EDRPOU': 'supplier_edrpou', 'Invoice number': 'invoice_number',
    'Invoice date': 'invoice_date', 'Currency': 'currency', 'Tax basis': 'tax_basis',
    'Item code': 'item_code', 'Revision': 'revision', 'Unit': 'unit',
    'Quantity': 'quantity', 'Unit price': 'unit_price', 'Line total': 'line_total',
    'Invoice total': 'total',
}
PATTERN = re.compile(r'^(' + '|'.join(re.escape(x) for x in LABELS) + r'): (.+)$', re.MULTILINE)


def extract_mock(source):
    c.source(source)
    result = {'schema': c.SCHEMA, 'provider': c.PROVIDER, 'source': c.source_identity(source),
              'state': 'needs_information', 'fields': None, 'exceptions': []}
    def refused(code):
        result['exceptions'] = [code]
        return result
    if source['status'] == 'ocr_required' or not any(s['text'].strip() for s in source['sections']):
        return refused('ocr_required')
    if sum(s['text'].splitlines().count(c.MARKER) for s in source['sections']) != 1:
        return refused('unsupported_document')
    values = {}
    for page, section in enumerate(source['sections'], 1):
        for match in PATTERN.finditer(section['text']):
            key = LABELS[match[1]]
            if key in values:
                return refused('unsupported_multi_line' if key in c.LINE_FIELDS else 'ambiguous_field')
            values[key] = {'value': match[2], 'evidence': {
                'page': page, 'source': section['source'], 'start': match.start(2), 'end': match.end(2),
                'quote': match[2], 'source_sha256': source['sha256']}}
    if set(values) != set(c.HEADER_FIELDS) | set(c.LINE_FIELDS):
        return refused('missing_field')
    fields = {key: values[key] for key in c.HEADER_FIELDS}
    fields['lines'] = [{'ordinal': 1, **{key: values[key] for key in c.LINE_FIELDS}}]
    result.update(state='extracted', fields=fields)
    c.draft(result, source)
    return result
