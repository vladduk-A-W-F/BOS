"""M3-a: column mapping and normalization of connected tables. Pure functions, synthetic tables only."""
from django.test import SimpleTestCase

from .mapping import MappingError, fields, normalize, suggest, validate


class MappingTests(SimpleTestCase):
    columns = ['№ замовлення', 'Покупець', 'Строк', 'Сума, грн', 'Валюта', 'Примітка']

    def test_suggest_uses_header_words_once_each(self):
        self.assertEqual(suggest('orders', self.columns), {
            'code': '№ замовлення', 'customer': 'Покупець', 'due_date': 'Строк',
            'amount': 'Сума, грн', 'currency': 'Валюта'})
        self.assertEqual(suggest('other', self.columns), {})
        self.assertEqual([f['field'] for f in fields('stock') if f['required']], ['item', 'quantity'])

    def test_validate_needs_required_fields_existing_columns_and_no_reuse(self):
        self.assertEqual(validate('orders', self.columns, {'code': '№ замовлення', 'customer': 'Покупець', 'amount': ''}),
                         {'code': '№ замовлення', 'customer': 'Покупець'})
        with self.assertRaisesRegex(MappingError, 'Клієнт'):
            validate('orders', self.columns, {'code': '№ замовлення'})
        with self.assertRaisesRegex(MappingError, 'немає колонки'):
            validate('orders', self.columns, {'code': 'Номер', 'customer': 'Покупець'})
        with self.assertRaisesRegex(MappingError, 'лише одному'):
            validate('orders', self.columns, {'code': 'Покупець', 'customer': 'Покупець'})
        with self.assertRaisesRegex(MappingError, 'Невідоме поле'):
            validate('orders', self.columns, {'code': '№ замовлення', 'customer': 'Покупець', 'price': 'Сума, грн'})
        self.assertEqual(validate('other', self.columns, {}), {})
        with self.assertRaises(MappingError):
            validate('other', self.columns, {'code': '№ замовлення'})

    def test_normalize_reads_exact_values_and_rejects_with_reasons(self):
        mapping = suggest('orders', self.columns)
        rows = [
            ['ZM-1', 'ТОВ «Тест»', '03.10.2026', '1 234,50', 'грн', ''],
            ['ZM-2', 'ПП «Два»', '2026-10-10', '1.234,56', '', ''],
            ['ZM-3', 'ПП «Три»', '', '1,234.5', 'EUR', ''],
            ['ZM-4', '', '03.10.2026', '10', 'UAH', ''],
            ['ZM-5', 'ТОВ', '31.02.2026', '10', 'UAH', ''],
            ['ZM-6', 'ТОВ', '03.10.2026', '10,005', 'UAH', ''],
            ['ZM-7', 'ТОВ', '03.10.2026', '10', 'BTC', ''],
            ['ZM-8', 'ТОВ', '03.10.2026', 'десять', 'UAH', ''],
        ]
        result = normalize('orders', self.columns, rows, mapping)
        self.assertEqual((result['accepted'], result['total']), (3, 8))
        self.assertEqual(result['rows'][0], {'code': 'ZM-1', 'customer': 'ТОВ «Тест»', 'due_date': '2026-10-03',
                                             'amount': '1234.50', 'currency': 'UAH'})
        self.assertEqual((result['rows'][1]['amount'], result['rows'][1]['currency']), ('1234.56', 'UAH'))
        self.assertEqual((result['rows'][2]['amount'], result['rows'][2]['due_date'], result['rows'][2]['currency']),
                         ('1234.50', None, 'EUR'))
        self.assertEqual([(r['row'], r['reason']) for r in result['rejected']], [
            (5, 'порожнє поле «Клієнт»'), (6, '«Строк»: незрозуміла дата'),
            (7, '«Сума»: більше 2 знаків після коми'), (8, '«Валюта»: невідома валюта'), (9, '«Сума»: не число')])

    def test_amounts_are_never_floats(self):
        result = normalize('payments', ['Документ', 'Платник', 'Сума'],
                           [['PD-1', 'ТОВ', '0.1'], ['PD-2', 'ТОВ', '999999999999.99'], ['PD-3', 'ТОВ', '1000000000000']],
                           {'reference': 'Документ', 'counterparty': 'Платник', 'amount': 'Сума'})
        self.assertEqual([r['amount'] for r in result['rows']], ['0.10', '999999999999.99'])
        self.assertTrue(all(isinstance(r['amount'], str) for r in result['rows']))
        self.assertEqual(result['rejected'], [{'row': 4, 'reason': '«Сума»: число поза межами'}])

    def test_stock_and_calls(self):
        stock = normalize('stock', ['Товар', 'Залишок'], [['Кутник', '12,5'], ['Лист', '1.0005']],
                          {'item': 'Товар', 'quantity': 'Залишок'})
        self.assertEqual(stock['rows'], [{'item': 'Кутник', 'quantity': '12.500'}])
        calls = normalize('calls', ['Час', 'Телефон', 'Тип'], [['05.10.2026 10:30', '+380000000000', 'вхідний']],
                          {'started_at': 'Час', 'contact': 'Телефон', 'direction': 'Тип'})
        self.assertEqual(calls['rows'], [{'started_at': '2026-10-05T10:30', 'contact': '+380000000000', 'direction': 'in'}])

    def test_broken_grouping_and_exponents_are_rejected_not_reinterpreted(self):
        cells = ['1,2.34', '1.2,34', '12.34,56', '1 23,4', '1e1000000', '1E5', '0x10', '--5', '1,234,56.7',
                 '12\n34', '₴ 1\n2 грн', '12\r\n34']
        result = normalize('payments', ['Документ', 'Платник', 'Сума'], [['PD', 'ТОВ', c] for c in cells],
                           {'reference': 'Документ', 'counterparty': 'Платник', 'amount': 'Сума'})
        self.assertEqual(result['accepted'], 0)
        self.assertEqual({r['reason'] for r in result['rejected']}, {'«Сума»: не число'})

    def test_valid_grouping_forms_and_currency_marks(self):
        cells = ['1 234,50', '1\u00a0234\u00a0567,5', '1,234,567.50', '1.234.567,50', '₴ 99', '1 500 грн', '250 UAH', '-12,5']
        result = normalize('payments', ['Документ', 'Платник', 'Сума'], [['PD', 'ТОВ', c] for c in cells],
                           {'reference': 'Документ', 'counterparty': 'Платник', 'amount': 'Сума'})
        self.assertEqual([r['amount'] for r in result['rows']],
                         ['1234.50', '1234567.50', '1234567.50', '1234567.50', '99.00', '1500.00', '250.00', '-12.50'])

    def test_call_time_keeps_seconds(self):
        calls = normalize('calls', ['Час', 'Телефон'], [['05.10.2026 10:30:59', '+380'], ['2026-10-05T10:31', '+380']],
                          {'started_at': 'Час', 'contact': 'Телефон'})
        self.assertEqual([r['started_at'] for r in calls['rows']], ['2026-10-05T10:30:59', '2026-10-05T10:31'])
