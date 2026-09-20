"""Pure contract controls. No Django setup/database, server or paid AI calls."""
from copy import deepcopy
from decimal import getcontext, Inexact
import hashlib
import importlib
import io
import json
from pathlib import Path
import socket
import sqlite3
import sys
import types
import unittest
from unittest.mock import patch

from operations.document_matching import ContractError, extract_mock, reconcile
from operations.document_matching import contract

FIXTURES = Path(__file__).resolve().parents[1] / 'tests/fixtures/document_matching'


class NamedBytes(io.BytesIO):
    name = 'synthetic.pdf'


class DocumentMatchingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # documents.py does not use Document. Stub that import only; the actual
        # parser and pypdf execute against the real fixture bytes, without ORM.
        unused_models = types.ModuleType('operations.models')
        unused_models.Document = object
        with patch.dict(sys.modules, {'operations.models': unused_models}):
            cls.parse = staticmethod(importlib.import_module('operations.documents').parse)

    def setUp(self):
        self.raw = (FIXTURES / 'supplier-invoice.pdf').read_bytes()
        parsed = self.parse(NamedBytes(self.raw))
        self.source = {'document_id': 1, 'code': 'SYN-INVOICE', 'revision': 'A',
                       'sha256': parsed['checksum'], 'status': parsed['status'], 'sections': parsed['sections']}
        self.context = json.loads((FIXTURES / 'context.json').read_text())
        self.context['source'] = deepcopy(self.source)

    def draft(self):
        return extract_mock(self.source)

    def match(self):
        return reconcile(self.draft(), self.context)

    def change(self, label, before, after):
        old = label + ': ' + before
        self.assertIn(old, self.source['sections'][0]['text'])
        self.source['sections'][0]['text'] = self.source['sections'][0]['text'].replace(old, label + ': ' + after)
        # Subsequent negative vectors are synthetic parsed-source DTOs, not a
        # claim of changed bytes in the fixture. Bind both snapshots explicitly.
        self.source['sha256'] = hashlib.sha256(self.source['sections'][0]['text'].encode()).hexdigest()
        self.context['source'] = deepcopy(self.source)

    def test_real_pdf_source_and_verbatim_evidence(self):
        self.assertEqual(self.source['sha256'], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(self.source['status'], 'needs_review')
        self.assertEqual(self.source['sections'][0]['source'], 'Сторінка 1')
        draft = self.draft()
        self.assertEqual(draft['provider'], 'mock.synthetic-invoice.v1')
        self.assertEqual(draft['fields']['lines'][0]['quantity']['value'], '10.000')
        for claim in [draft['fields'][key] for key in contract.HEADER_FIELDS] + [draft['fields']['lines'][0][key] for key in contract.LINE_FIELDS]:
            evidence = claim['evidence']
            self.assertEqual(evidence['quote'], self.source['sections'][evidence['page'] - 1]['text'][evidence['start']:evidence['end']])
            self.assertEqual(claim['value'], evidence['quote'])
            self.assertEqual(evidence['source_sha256'], self.source['sha256'])

    def test_exact_full_purchase_multiple_receipts(self):
        result = self.match()
        self.assertEqual(result['decision'], 'accept_draft')
        self.assertEqual(result['exceptions'], [])
        self.assertEqual(result['matches']['receipt_ids'], [41, 42])
        self.assertEqual(result['comparison']['receipt_quantity'], {
            'gross': '10.000', 'returned': '0.000', 'net': '10.000', 'invoice': '10.000', 'difference': '0.000'})
        self.assertEqual(result['comparison']['line_total']['expected'], '12000.00')
        self.assertIsNone(result['operation_proposal'])

    def test_partial_receipt_has_exact_gap(self):
        self.context['receipts'].pop()
        result = self.match()
        self.assertEqual(result['decision'], 'needs_information')
        self.assertIn('received_quantity_mismatch', result['exceptions'])
        self.assertEqual(result['comparison']['receipt_quantity']['difference'], '-6.000')

    def test_returns_reduce_receipts_without_remaining_stock(self):
        self.context['receipts'][0]['returned_quantity'] = '2.000'
        result = self.match()
        self.assertEqual(result['comparison']['receipt_quantity']['net'], '8.000')
        self.assertEqual(result['comparison']['receipt_quantity']['difference'], '-2.000')
        self.assertEqual(result['decision'], 'needs_information')

    def test_explicit_selection_never_picks_first_candidate(self):
        self.context['selection']['supplier_id'] = None
        self.assertIn('supplier_selection_required', self.match()['exceptions'])
        self.context['suppliers'].append({**self.context['suppliers'][0], 'id': 12})
        result = self.match()
        self.assertIn('supplier_ambiguous', result['exceptions'])
        self.assertIsNone(result['matches']['supplier_id'])
        self.context['selection']['supplier_id'] = 11
        self.assertEqual(self.match()['decision'], 'accept_draft')

    def test_inactive_and_wrong_type_supplier_are_not_matches(self):
        self.context['suppliers'][0]['is_active'] = False
        self.assertIn('supplier_missing', self.match()['exceptions'])
        self.context['suppliers'][0].update(is_active=True, type='customer')
        self.assertIn('supplier_missing', self.match()['exceptions'])

    def test_price_and_revision_mismatch(self):
        self.change('Unit price', '1200.00', '1199.99')
        result = self.match()
        self.assertIn('price_mismatch', result['exceptions'])
        self.assertIn('line_total_mismatch', result['exceptions'])
        self.assertEqual(result['comparison']['price']['difference'], '-0.01')
        self.change('Revision', 'A', 'B')
        self.assertIn('revision_mismatch', self.match()['exceptions'])

    def test_currency_and_unit_mismatch_do_not_convert_or_subtract(self):
        self.change('Currency', 'UAH', 'USD')
        result = self.match()
        self.assertIn('currency_mismatch', result['exceptions'])
        self.assertIsNone(result['comparison']['price'])
        self.change('Unit', 'pcs', 'kg')
        result = self.match()
        self.assertIn('unit_mismatch', result['exceptions'])
        self.assertIsNone(result['comparison']['quantity'])
        self.assertIsNone(result['comparison']['receipt_quantity']['difference'])

    def test_overage_partial_invoice_extras_and_tax_are_exceptions(self):
        self.context['receipts'][1]['quantity'] = '7.000'
        self.assertIn('receipt_overage', self.match()['exceptions'])
        self.context['purchase']['extras'] = '1.00'
        self.assertIn('unsupported_extras', self.match()['exceptions'])
        self.change('Tax basis', 'excluding_VAT', 'including_VAT')
        self.assertIn('unsupported_tax_basis', self.match()['exceptions'])
        self.change('Quantity', '10.000', '5.000')
        self.assertIn('full_purchase_quantity_mismatch', self.match()['exceptions'])

    def test_duplicate_ids_foreign_receipts_invalid_return_rejected(self):
        self.context['receipts'].append(deepcopy(self.context['receipts'][0]))
        with self.assertRaisesRegex(ContractError, 'duplicate_receipts_id'):
            self.match()
        self.context['receipts'].pop()
        self.context['receipts'][0]['purchase_id'] = 99
        self.assertIn('receipt_source_mismatch', self.match()['exceptions'])
        self.context['receipts'][0]['returned_quantity'] = '4.001'
        with self.assertRaisesRegex(ContractError, 'invalid_return_quantity'):
            self.match()

    def test_source_changed_and_fabricated_evidence(self):
        draft = self.draft()
        self.context['source']['sha256'] = 'a' * 64
        result = reconcile(draft, self.context)
        self.assertEqual(result['exceptions'], ['source_changed'])
        self.assertEqual(result['decision'], 'reject_draft')
        self.context['source'] = deepcopy(self.source)
        draft['fields']['lines'][0]['quantity']['evidence']['start'] = -1
        with self.assertRaisesRegex(ContractError, 'invalid_evidence'):
            reconcile(draft, self.context)
        draft = self.draft()
        draft['fields']['lines'][0]['quantity'] = deepcopy(draft['fields']['lines'][0]['unit_price'])
        with self.assertRaisesRegex(ContractError, 'mock_evidence_mismatch'):
            reconcile(draft, self.context)

    def test_restricted_context_discloses_no_fields_ids_counts_or_money(self):
        self.context['access'] = 'restricted'
        result = self.match()
        self.assertEqual(result, {'schema': contract.SCHEMA, 'provider': contract.PROVIDER,
            'source': None, 'fields': None, 'matches': None, 'comparison': None,
            'exceptions': ['restricted'], 'decision': 'needs_information', 'operation_proposal': None})

    def test_no_text_pdf_preserves_ocr_required(self):
        parsed = self.parse(NamedBytes((FIXTURES / 'no-text.pdf').read_bytes()))
        self.source.update(sha256=parsed['checksum'], status=parsed['status'], sections=parsed['sections'])
        self.context['source'] = deepcopy(self.source)
        result = self.match()
        self.assertEqual(parsed['status'], 'ocr_required')
        self.assertEqual(result['exceptions'], ['ocr_required'])
        self.assertIsNone(result['fields'])

    def test_corrupt_and_encrypted_pdf_use_actual_parser_refusal(self):
        with self.assertRaises(ValueError):
            self.parse(NamedBytes(b'%PDF-1.4\ncorrupt'))
        from pypdf import PdfWriter
        writer = PdfWriter(); writer.add_blank_page(width=300, height=300); writer.encrypt('synthetic-password')
        stream = io.BytesIO(); writer.write(stream)
        with self.assertRaisesRegex(ValueError, 'пароль'):
            self.parse(NamedBytes(stream.getvalue()))

    def test_multi_line_and_unknown_document_are_explicitly_unsupported(self):
        self.source['sections'][0]['text'] += '\nItem code: SYN-ITEM-2\n'
        self.context['source'] = deepcopy(self.source)
        self.assertEqual(self.match()['exceptions'], ['unsupported_multi_line'])
        self.source['sections'][0]['text'] = 'ordinary invoice text without synthetic marker'
        self.context['source'] = deepcopy(self.source)
        self.assertEqual(self.match()['exceptions'], ['unsupported_document'])

    def test_malformed_numbers_keys_ids_and_overflow_fail_closed(self):
        original = deepcopy(self.context)
        for value in ('NaN', 'Infinity', '-1', '1e2', '1.0001', '1000000001', 1.0, True):
            with self.subTest(value=value):
                self.context = deepcopy(original)
                self.context['purchase']['quantity'] = value
                with self.assertRaises(ContractError):
                    self.match()
        self.context = deepcopy(original); self.context['purchase']['id'] = True
        with self.assertRaises(ContractError): self.match()
        self.context = deepcopy(original); self.context['purchase']['surprise'] = 'hidden'
        with self.assertRaises(ContractError): self.match()
        self.context = deepcopy(original)
        self.change('Quantity', '10.000', '1000000000')
        self.change('Unit price', '1200.00', '1000000000')
        with self.assertRaisesRegex(ContractError, 'decimal_range'): self.match()

    def test_pure_deterministic_nonmutating_functions_without_external_io(self):
        source = deepcopy(self.source); context = deepcopy(self.context)
        with patch('builtins.open', side_effect=AssertionError('file IO')), patch.object(sqlite3, 'connect', side_effect=AssertionError('DB IO')), patch.object(socket, 'socket', side_effect=AssertionError('network IO')):
            first = self.match(); second = self.match()
        self.assertEqual(first, second)
        self.assertEqual(self.source, source); self.assertEqual(self.context, context)
        first['fields']['currency']['value'] = 'USD'
        self.assertEqual(self.draft()['fields']['currency']['value'], 'UAH')

    def test_global_decimal_precision_and_traps_do_not_change_result(self):
        old = getcontext().copy()
        try:
            getcontext().prec = 2
            getcontext().traps[Inexact] = True
            self.assertEqual(self.match()['decision'], 'accept_draft')
        finally:
            from decimal import setcontext
            setcontext(old)


if __name__ == '__main__':
    unittest.main()
