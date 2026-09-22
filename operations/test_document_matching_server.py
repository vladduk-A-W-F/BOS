"""Scoped synthetic SQLite controls for the read adapter, not workflow readiness."""
from datetime import date
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import uuid

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from boss_project.policy import Policy
from erp.models import Event, GoodsReturn, Item, Location, Lot, Movement, Purchase
from erp.order_trace import ReadStateChanged, digest
from finance.models import Counterparty
from operations.document_matching import contract
from operations.document_matching import server_adapter as adapter
from operations.models import Configuration, Document


FIXTURES = Path(__file__).resolve().parents[1] / 'tests/fixtures/document_matching'


@override_settings(BOS_DATA_MODE='working', ANTHROPIC_API_KEY='')
class DocumentMatchingServerTests(TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get('DJANGO_SETTINGS_MODULE'), 'verification_settings')
        self.assertEqual(connection.vendor, 'sqlite')
        self.assertTrue(Path(connection.settings_dict['NAME']).is_absolute())
        # The test runner must explicitly provide its owned D: temp/media root.
        self.assertEqual(Path(settings.MEDIA_ROOT).drive.lower(), 'd:')
        self.setup_fixture()

    def setup_fixture(self):
        self.folder = tempfile.TemporaryDirectory(prefix='document-match-', dir=settings.MEDIA_ROOT)
        self.addCleanup(self.folder.cleanup)
        self.media = Path(self.folder.name)
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = get_user_model().objects.create_user(username='synthetic-document-ceo')
        self.user.groups.add(Group.objects.get_or_create(name='ceo')[0])
        self.supplier = Counterparty.objects.create(name='Synthetic supplier', type='supplier', edrpou='30900001')
        self.item = Item.objects.create(code='SYN-ITEM-1', name='Synthetic part', unit='pcs', revision='A', currency='UAH')
        self.po = Purchase.objects.create(code='SYN-PO-1', supplier=self.supplier, item=self.item,
            quantity=10, price=1200, revision='A', currency='UAH',
            due_date=date(2026, 9, 20), original_due=date(2026, 9, 20))
        self.location = Location.objects.create(code='SYN-WH', name='Synthetic warehouse')
        self.receipts = [self.receipt('4.000'), self.receipt('6.000')]
        self.raw = (FIXTURES / 'supplier-invoice.pdf').read_bytes()
        self.doc, self.path = self.document(self.raw, 'invoice.pdf')

    def request(self, user=None):
        request = RequestFactory().get('/synthetic-read-only')
        request.user = self.user if user is None else user
        request.session = {}
        return request

    def build(self, **kwargs):
        selection = dict(purchase_id=self.po.pk, supplier_id=self.supplier.pk, item_id=self.item.pk)
        selection.update(kwargs)
        return adapter.build(self.request(), self.doc.pk, **selection)

    def receipt(self, quantity):
        lot = Lot.objects.create(code='SYN-LOT-' + uuid.uuid4().hex, item=self.item,
            location=self.location, revision='A', quantity=quantity, unit_cost=1200, currency='UAH')
        return Movement.objects.create(lot=lot, quantity=quantity, kind='receipt', reference=self.po.code,
                                       purchase=self.po, cost=Decimal(quantity) * 1200)

    def document(self, raw, filename, **kwargs):
        key = uuid.uuid4().hex
        relative = f'documents/{key[:2]}/{key}.blob'
        path = self.media / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        values = dict(code='SYN-DOC-' + key, revision='A', title='Synthetic evidence', filename=filename,
            checksum=hashlib.sha256(raw).hexdigest(), size=len(raw), original_file=relative,
            status='needs_review', access_level='ceo', text='Poisoned cache',
            sections=[{'source': 'Forged page', 'text': 'Invoice total: 0.01'}])
        values.update(kwargs)
        return Document.objects.create(**values), path

    def supplier_return(self, quantity='2.000'):
        source = self.receipts[0]
        result = Movement.objects.create(lot=source.lot, quantity=-Decimal(quantity), kind='supplier_return',
            reference='SYN-RETURN', purchase=self.po, cost=Decimal(quantity) * 1200)
        event = Event.objects.create(action='synthetic_return', payload={}, result={}, role='ceo')
        return GoodsReturn.objects.create(operation_id=uuid.uuid4(), payload_hash='0' * 64,
            code='SYN-RETURN-' + uuid.uuid4().hex, reason='Synthetic fixture', business_date=date(2026, 9, 20),
            actor=self.user, event=event, direction='supplier', source=source, result=result,
            quantity=quantity, source_quantity=source.quantity, source_cost=source.cost,
            currency='UAH', unit_cost=1200, allocated_cost=Decimal(quantity) * 1200,
            source_snapshot={'movement_id': source.pk, 'kind': 'receipt', 'lot_id': source.lot_id,
                'purchase_id': self.po.pk, 'item_id': self.item.pk, 'revision': 'A', 'currency': 'UAH'})

    def assert_neutral(self, result, code):
        self.assertEqual(result['exceptions'], [code])
        for key in ('source', 'fields', 'matches', 'comparison', 'operation_proposal'):
            self.assertIsNone(result[key])

    def mutate_between_reads(self, callback):
        collect = adapter._collect
        count = 0
        def changing(*args):
            nonlocal count
            result = collect(*args)
            count += 1
            if count == 1:
                callback()
            return result
        with patch.object(adapter, '_collect', side_effect=changing), self.assertRaises(ReadStateChanged):
            self.build()

    def test_actual_private_pdf_beats_cached_sections_with_exact_sha_page_quote(self):
        result = self.build()
        self.assertEqual(result['decision'], 'accept_draft')
        self.assertEqual(result['provider'], 'mock.synthetic-invoice.v1')
        self.assertEqual(result['source']['document_id'], self.doc.pk)
        self.assertEqual(result['source']['sha256'], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(result['fields']['total']['value'], '12000.00')
        self.assertEqual(result['fields']['total']['evidence']['source'], 'Сторінка 1')
        parsed_file = io.BytesIO(self.raw)
        parsed_file.name = 'actual.pdf'
        parsed = adapter.documents.parse(parsed_file)
        for claim in [result['fields'][key] for key in contract.HEADER_FIELDS] + [
                result['fields']['lines'][0][key] for key in contract.LINE_FIELDS]:
            evidence = claim['evidence']
            text = parsed['sections'][evidence['page'] - 1]['text']
            self.assertEqual(claim['value'], text[evidence['start']:evidence['end']])
            self.assertEqual(evidence['quote'], claim['value'])
            self.assertEqual(evidence['source_sha256'], self.doc.checksum)

    def test_roles_and_anonymous_deny_before_document_or_financial_queries(self):
        for role in ('manager', 'observer'):
            user = get_user_model().objects.create_user(username='synthetic-' + role)
            user.groups.add(Group.objects.get_or_create(name=role)[0])
            with CaptureQueriesContext(connection) as queries, self.assertRaises(PermissionError):
                adapter.build(self.request(user), self.doc.pk)
            sql = ' '.join(row['sql'].lower() for row in queries)
            for table in ('operations_document', 'finance_counterparty', 'erp_purchase', 'erp_item', 'erp_movement'):
                self.assertNotIn(table, sql)
        with self.assertRaises(PermissionError):
            adapter.build(self.request(AnonymousUser()), self.doc.pk)

    def test_initial_inaccessible_document_returns_no_candidates(self):
        with patch.object(Policy, 'documents', lambda self: Document.objects.none()), self.assertRaises(ObjectDoesNotExist):
            self.build()
        with self.assertRaises(ObjectDoesNotExist):
            adapter.build(self.request(), 999999)

    def test_file_tamper_and_missing_never_fall_back_to_cached_or_legacy_data(self):
        Document.objects.filter(pk=self.doc.pk).update(content=self.raw)
        self.path.write_bytes(b'PRIVATE untrusted tamper')
        self.assert_neutral(self.build(), 'source_unreadable')
        self.path.unlink()
        self.assert_neutral(self.build(), 'source_unreadable')

    def test_explicit_selection_no_first_candidate_or_purchase(self):
        result = self.build(supplier_id=None, item_id=None, purchase_id=None)
        self.assertIn('supplier_selection_required', result['exceptions'])
        self.assertIn('item_selection_required', result['exceptions'])
        self.assertIn('purchase_missing', result['exceptions'])
        self.assertIsNone(result['matches']['purchase_id'])
        Counterparty.objects.create(name='Second synthetic supplier', type='supplier', edrpou=self.supplier.edrpou)
        result = self.build(supplier_id=None)
        self.assertIn('supplier_ambiguous', result['exceptions'])
        self.assertIsNone(result['matches']['supplier_id'])
        self.assertEqual(self.build()['decision'], 'accept_draft')
        self.assertIn('supplier_selection_mismatch', self.build(supplier_id=999999)['exceptions'])

    def test_only_identifiers_are_accepted(self):
        for bad in (True, '1', 0, -1, 9007199254740992):
            with self.assertRaises(contract.ContractError):
                self.build(purchase_id=bad)
        with self.assertRaises(TypeError):
            self.build(context={'amount': '1'})

    def test_partial_receipts_use_originals_even_if_remaining_stock_is_zero(self):
        Lot.objects.all().update(quantity=0)
        self.assertEqual(self.build()['comparison']['receipt_quantity']['gross'], '10.000')
        self.receipts[1].delete()
        result = self.build()
        self.assertIn('received_quantity_mismatch', result['exceptions'])
        self.assertEqual(result['comparison']['receipt_quantity']['difference'], '-6.000')

    def test_linked_supplier_returns_reduce_net(self):
        self.supplier_return()
        result = self.build()
        self.assertEqual(result['comparison']['receipt_quantity'], {
            'gross': '10.000', 'returned': '2.000', 'net': '8.000', 'invoice': '10.000', 'difference': '-2.000'})
        self.assertIn('received_quantity_mismatch', result['exceptions'])
        self.assertEqual(result['matches']['receipt_ids'], [row.pk for row in self.receipts])

    def test_unlinked_or_mismatched_supplier_return_is_explicit_exception(self):
        returned = self.supplier_return()
        GoodsReturn.objects.filter(pk=returned.pk).update(source_snapshot={})
        self.assert_neutral(self.build(), 'inconsistent_receipt_history')
        returned.delete()
        self.assert_neutral(self.build(), 'inconsistent_receipt_history')

    def test_unsupported_real_text_scan_and_status_are_explicit(self):
        for raw, name, expected in ((b'Real ordinary invoice: amount 15', 'real.txt', 'unsupported_document'),
                ((FIXTURES / 'no-text.pdf').read_bytes(), 'scan.pdf', 'ocr_required')):
            self.doc, self.path = self.document(raw, name)
            result = self.build()
            self.assertEqual(result['exceptions'], [expected])
            self.assertIsNone(result['fields'])
        Document.objects.filter(pk=self.doc.pk).update(status='supplier_quote')
        self.assert_neutral(self.build(), 'unsupported_source_status')

    def test_broken_parser_error_does_not_echo_private_data(self):
        self.doc, self.path = self.document(b'PRIVATE SECRET invalid binary', 'broken.pdf')
        with self.assertNoLogs('pypdf', level='WARNING'):
            result = self.build()
        self.assert_neutral(result, 'document_parse_failed')
        self.assertNotIn('SECRET', json.dumps(result))

    def test_approved_source_is_admitted_without_changing_status(self):
        Document.objects.filter(pk=self.doc.pk).update(status='approved')
        self.assertEqual(self.build()['decision'], 'accept_draft')
        self.assertEqual(Document.objects.get(pk=self.doc.pk).status, 'approved')

    def test_old_explicit_version_never_substitutes_newest_hidden_version(self):
        latest, _ = self.document(self.raw, 'new.pdf', code=self.doc.code, revision='B', access_level='ceo')
        self.assert_neutral(self.build(), 'source_not_current')
        result = adapter.build(self.request(), latest.pk, purchase_id=self.po.pk,
                               supplier_id=self.supplier.pk, item_id=self.item.pk)
        self.assertEqual(result['source']['document_id'], latest.pk)

    def test_document_bytes_change_during_read_is_neutral_conflict(self):
        self.mutate_between_reads(lambda: self.path.write_bytes(b'tamper after verified first read'))

    def test_document_status_change_during_read_is_neutral_conflict(self):
        self.mutate_between_reads(lambda: Document.objects.filter(pk=self.doc.pk).update(status='approved'))

    def test_successor_created_during_read_is_neutral_conflict(self):
        self.mutate_between_reads(lambda: self.document(self.raw, 'new.pdf', code=self.doc.code, revision='B'))

    def test_purchase_data_change_during_read_is_neutral_conflict(self):
        self.mutate_between_reads(lambda: Purchase.objects.filter(pk=self.po.pk).update(price=1201))

    def test_receipt_data_change_during_read_is_neutral_conflict(self):
        self.mutate_between_reads(lambda: Movement.objects.filter(pk=self.receipts[0].pk).update(quantity=3))

    def test_role_revocation_and_inactive_user_during_read_are_neutral_conflict(self):
        self.mutate_between_reads(lambda: self.user.groups.set([Group.objects.get_or_create(name='manager')[0]]))
        self.user.groups.set([Group.objects.get(name='ceo')])
        self.mutate_between_reads(lambda: get_user_model().objects.filter(pk=self.user.pk).update(is_active=False))

    def test_capability_change_and_stale_request_revision_are_neutral_conflict(self):
        permission = Permission.objects.get(content_type__app_label='operations', codename='download_document')
        self.mutate_between_reads(lambda: self.user.user_permissions.add(permission))
        request = self.request()
        request.bos_access_revision = 'stale-access'
        with self.assertRaises(ReadStateChanged):
            adapter.build(request, self.doc.pk)

    def test_write_revision_changes_without_mutex_creation_on_read(self):
        self.assertFalse(Configuration.objects.filter(key='erp_write').exists())
        self.build()
        self.assertFalse(Configuration.objects.filter(key='erp_write').exists())
        self.mutate_between_reads(lambda: Configuration.objects.create(key='erp_write', value={'revision': 1}))

    def test_candidate_and_receipt_limits_are_refused_not_truncated(self):
        Counterparty.objects.bulk_create([Counterparty(name='Synthetic candidate ' + str(index),
            type='supplier', edrpou=self.supplier.edrpou) for index in range(100)])
        self.assert_neutral(self.build(), 'context_limit_exceeded')
        Counterparty.objects.exclude(pk=self.supplier.pk).delete()
        Movement.objects.bulk_create([Movement(lot=self.receipts[0].lot, quantity=1, kind='receipt',
            reference=self.po.code, purchase=self.po) for _ in range(99)])
        self.assert_neutral(self.build(), 'context_limit_exceeded')

    def test_byte_text_page_and_section_limits_have_no_silent_truncation(self):
        # Exercise the size boundary with a small local cap, never the prohibited 13 MiB vector.
        with patch.object(adapter.documents, 'MAX_BYTES', 10):
            self.assert_neutral(self.build(), 'source_limit_exceeded')
        self.doc, self.path = self.document(b'x' * 500001, 'large.txt')
        self.assert_neutral(self.build(), 'document_parse_failed')
        from pypdf import PdfWriter
        writer = PdfWriter()
        for _ in range(101):
            writer.add_blank_page(width=72, height=72)
        output = io.BytesIO()
        writer.write(output)
        self.doc, self.path = self.document(output.getvalue(), 'pages.pdf')
        self.assert_neutral(self.build(), 'document_parse_failed')
        from docx import Document as Word
        word = Word()
        for _ in range(101):
            word.add_paragraph('Synthetic bounded section')
        output = io.BytesIO()
        word.save(output)
        self.doc, self.path = self.document(output.getvalue(), 'sections.docx')
        self.assert_neutral(self.build(), 'source_limit_exceeded')

    def test_read_has_no_database_or_private_file_writes_and_raw_receipt(self):
        def snapshot():
            state = {}
            for model in apps.get_models():
                state[model._meta.label] = [{key: hashlib.sha256(bytes(value)).hexdigest()
                    if isinstance(value, (bytes, bytearray, memoryview)) else value
                    for key, value in row.items()} for row in model._base_manager.order_by('pk').values()]
            return digest(state)
        before = snapshot()
        files_before = {str(path.relative_to(self.media)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in self.media.rglob('*') if path.is_file()}
        with CaptureQueriesContext(connection) as queries:
            result = self.build()
        for query in queries:
            self.assertTrue(query['sql'].lstrip().upper().startswith('SELECT'), query['sql'])
        after = snapshot()
        files_after = {str(path.relative_to(self.media)): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in self.media.rglob('*') if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(files_before, files_after)
        self.assertIsNone(result['operation_proposal'])
        print('DOCUMENT_MATCH_READ_RECEIPT ' + json.dumps({'database_vendor': connection.vendor,
            'source_before': before, 'source_after': after, 'private_files_before': files_before,
            'private_files_after': files_after, 'queries': len(queries), 'only_select': True,
            'decision': result['decision'], 'operation_proposal': result['operation_proposal']}, sort_keys=True))
