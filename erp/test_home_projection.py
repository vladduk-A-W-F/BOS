from unittest.mock import patch

from django.test import SimpleTestCase

from erp.experience import home


class HomeProjectionInvoiceCurrencyTests(SimpleTestCase):
    @patch('tasks.queries.project_list', return_value=[])
    @patch('tasks.queries.active', return_value=[])
    def test_invoice_only_currency_is_present_with_its_financial_totals(self, _active, _project_list):
        result = home({
            'orders': [],
            'lots': [],
            'purchases': [],
            'costs': [],
            'invoices': [{'currency': 'USD', 'open': '125.50', 'paid': '24.50'}],
        })
        self.assertEqual(result['financial'], [{
            'currency': 'USD',
            'order_value': '0',
            'shipped_value': '0',
            'shipped_cost': '0',
            'gross_margin': '0',
            'receivable': '125.50',
            'paid': '24.50',
            'purchase_open': '0.00',
            'stock_value': '0.00',
        }])

    @patch('tasks.queries.project_list', return_value=[])
    @patch('tasks.queries.active', return_value=[])
    def test_empty_snapshot_keeps_eur_financial_fallback(self, _active, _project_list):
        result = home({
            'orders': [],
            'lots': [],
            'purchases': [],
            'costs': [],
            'invoices': [],
        })
        self.assertEqual(result['financial'][0]['currency'], 'EUR')
        self.assertEqual(result['financial'][0]['receivable'], '0')
        self.assertEqual(result['financial'][0]['paid'], '0')