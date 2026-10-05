"""BoS 4 demo v1.1: AdventureWorks catalog and a large order, pinned and consistent. Synthetic, new DB only."""
from datetime import date, timedelta
from decimal import Decimal as D, ROUND_HALF_UP
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from operations.models import Configuration, Document
from . import bos4_demo_aw_v11 as aw
from .models import DocumentLink, Item, Lot, Production, Purchase, SalesOrder


class SubsetModuleTests(SimpleTestCase):
    """The generated module is self-consistent and every number can be recomputed from its rules."""

    def test_pins_and_ledger(self):
        self.assertEqual(aw.PINS['repository'], 'https://github.com/microsoft/sql-server-samples')
        self.assertRegex(aw.PINS['commit'], r'^[0-9a-f]{40}$')
        self.assertIn('MIT', aw.PINS['license'])
        self.assertTrue(aw.PINS['aw_build_version'])
        for name in ('Product.csv', 'BillOfMaterials.csv', 'SalesOrderHeader.csv', 'SalesOrderDetail.csv'):
            self.assertRegex(aw.PINS['csv_sha256'][name], r'^[0-9a-f]{64}$')
        self.assertEqual([row[0] for row in aw.LEDGER], ['Вибір замовлення', 'Кількість', 'Перерахунок ціни AW',
                                                         'Сценарна ціна', 'Виріб', 'Специфікація', 'Виключено',
                                                         'Залишок', 'Закупівля', 'Виробництво', 'Сценарне'])
        for name in ('ProductInventory.csv', 'ProductVendor.csv', 'Vendor.csv', 'WorkOrder.csv'):
            self.assertRegex(aw.PINS['csv_sha256'][name], r'^[0-9a-f]{64}$')
        self.assertEqual((aw.RATE['currency'], aw.RATE['date'], aw.RATE['uah_per_unit']), ('USD', '2026-10-01', '44.6819'))
        self.assertIn('НБУ', aw.RATE['source'])

    def test_scale_meets_the_spec(self):
        lines = aw.ORDER['lines']
        self.assertGreaterEqual(len({line['code'] for line in lines}), 20)
        self.assertGreaterEqual(sum(line['quantity'] for line in lines), 1000)
        for line in lines:
            self.assertEqual(line['quantity'], line['aw_qty'] * aw.QTY_SCALE)

    def test_costs_and_prices_follow_the_ledger(self):
        price = {k: D(m['price']) for k, m in aw.MATERIALS.items()}
        for product in aw.PRODUCTS:
            with self.subTest(product=product['code']):
                self.assertTrue(set(product['bom']) <= set(price), product['bom'])
                cost = sum((price[a] * D(q) for a, q in product['bom'].items()), D(aw.LABOR[product['kind']]))
                self.assertEqual(D(product['planned_cost']), cost.quantize(D('0.01')))
                expected = (cost * D(aw.MARKUP[product['kind']]) / 10).quantize(D('1'), rounding=ROUND_HALF_UP) * 10
                self.assertEqual(D(product['price']), expected)
                self.assertGreater(D(product['price']), D(product['planned_cost']))
                # A localized derivative, not a renamed bicycle: furniture name, AW keys kept for provenance.
                self.assertRegex(product['name'], r'^(Каркас стелажа|Стелаж складський) .+, H \d{4} мм$')
                self.assertEqual(product['height_mm'], 1000 + 20 * int(product['aw_name'].rsplit(', ', 1)[1]))
        by_code = {p['code']: p for p in aw.PRODUCTS}
        for line in aw.ORDER['lines']:
            self.assertEqual(line['price'], by_code[line['code']]['price'])
            self.assertEqual(line['aw_product_id'], by_code[line['code']]['aw_product_id'])

    def test_aw_prices_are_converted_with_the_pinned_rate(self):
        rate = D(aw.RATE['uah_per_unit'])
        total_usd = total_uah = scenario = D(0)
        for line in aw.ORDER['lines']:
            with self.subTest(line=line['aw_detail_id']):
                usd = D(line['aw_unit_price_usd']) * (1 - D(line['aw_unit_discount']))
                self.assertEqual(D(line['aw_unit_price_uah']), (usd * rate).quantize(D('0.01'), rounding=ROUND_HALF_UP))
                total_usd += usd * line['quantity']
                total_uah += D(line['aw_unit_price_uah']) * line['quantity']
                scenario += D(line['price']) * line['quantity']
        self.assertEqual(D(aw.ORDER['aw_total_usd']), total_usd.quantize(D('0.01'), rounding=ROUND_HALF_UP))
        self.assertEqual(D(aw.ORDER['aw_total_uah']), total_uah)
        self.assertEqual(D(aw.ORDER['total_uah']), scenario)
        self.assertEqual(aw.ORDER['aw_sales_order_number'], 'SO' + str(aw.ORDER['aw_sales_order_id']))

    def test_stock_and_purchases_cover_the_order_exactly(self):
        need = {}
        by_code = {p['code']: p for p in aw.PRODUCTS}
        for line in aw.ORDER['lines']:
            for article, qty in by_code[line['code']]['bom'].items():
                need[article] = need.get(article, D(0)) + D(qty) * line['quantity']
        stock = {row['article']: D(row['quantity']) for row in aw.STOCK}
        self.assertEqual(set(stock), {m['article'] for m in aw.MATERIALS.values()})
        for row in aw.STOCK:
            per = D(aw.MATERIALS[row['article']]['per_aw_unit'] or '1')
            self.assertEqual(stock[row['article']], sum(D(r['aw_quantity']) for r in row['aw_rows']) * per)
            self.assertTrue(all(1 <= r['aw_location_id'] <= 6 for r in row['aw_rows']))
        bought = {p['article']: p for p in aw.PURCHASES}
        self.assertEqual(set(bought), {a for a in need if need[a] > stock[a]})
        for article, p in bought.items():
            with self.subTest(article=article):
                self.assertEqual((D(p['need']), D(p['on_hand'])), (need[article], stock[article]))
                minimum = D(p['aw_min_order_qty']) * D(aw.MATERIALS[article]['per_aw_unit'] or '1') if p['aw_unit'] == 'EA' else D(0)
                expected = max(need[article] - stock[article], minimum).to_integral_value(rounding='ROUND_CEILING')
                self.assertEqual(D(p['quantity']), expected)
                self.assertGreaterEqual(stock[article] + D(p['quantity']), need[article])
                self.assertEqual(p['price'], aw.MATERIALS[article]['price'])
                self.assertEqual(p['supplier'], aw.MATERIALS[article]['supplier'])
                self.assertEqual(D(p['aw_standard_price_uah']),
                                 (D(p['aw_standard_price_usd']) * D(aw.RATE['uah_per_unit'])).quantize(D('0.01'), rounding=ROUND_HALF_UP))
                self.assertEqual(p['due_date'], str(date.fromisoformat(aw.SUPPLY_DATE) + timedelta(days=p['lead_days'])))

    def test_jobs_follow_aw_work_orders_and_fit_the_order(self):
        lines = aw.ORDER['lines']
        self.assertEqual([(j['product'], j['quantity'], j['aw_detail_id']) for j in aw.JOBS],
                         [(l['code'], l['quantity'], l['aw_detail_id']) for l in lines])
        self.assertEqual(len({j['code'] for j in aw.JOBS}), len(lines))
        shift = {date.fromisoformat(j['start_date']) - date.fromisoformat(j['aw_start_date']) for j in aw.JOBS}
        shift |= {date.fromisoformat(j['due_date']) - date.fromisoformat(j['aw_due_date']) for j in aw.JOBS}
        self.assertEqual(len(shift), 1)            # one shift for the whole schedule: AW offsets and durations kept
        self.assertEqual(min(j['start_date'] for j in aw.JOBS), aw.FIRST_START)
        self.assertGreater(aw.FIRST_START, max(p['due_date'] for p in aw.PURCHASES))
        self.assertLess(max(j['due_date'] for j in aw.JOBS), '2026-11-27')
        self.assertTrue(all(j['aw_start_date'] >= aw.ORDER['aw_order_date'] for j in aw.JOBS))

    def test_bicycle_only_parts_never_enter_a_bom(self):
        used = {a for p in aw.PRODUCTS for a in p['bom']}
        self.assertFalse(used & set(aw.EXCLUDED_LEAVES))
        self.assertIn('TI-R092', aw.EXCLUDED_LEAVES)       # a road tire
        self.assertIn('LR-2398', aw.EXCLUDED_LEAVES)       # a bearing lock ring, not a furniture lock

    def test_generator_reproduces_the_module_when_the_pinned_source_is_present(self):
        source = os.environ.get('BOS_AW_SOURCE')
        if not source:
            self.skipTest('BOS_AW_SOURCE (локальний checkout sql-server-samples) не задано.')
        from scripts import bos4_aw_subset as generator
        module = Path(aw.__file__).read_text(encoding='utf-8')
        self.assertEqual(generator.render(generator.build(source), aw.PINS['commit']), module)


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SeedV11Tests(TransactionTestCase):
    def setUp(self):
        folder = TemporaryDirectory(prefix='bos4-demo-v11-test-')
        self.addCleanup(folder.cleanup)
        override = override_settings(MEDIA_ROOT=Path(folder.name) / 'media')
        override.enable()
        self.addCleanup(override.disable)

    def seed(self, version):
        output = StringIO()
        call_command('seed_bos4_demo', '--dataset-version', version, stdout=output)
        return json.loads(output.getvalue())

    def test_large_order_is_consistent_with_catalog_documents_and_provenance(self):
        receipt = self.seed('1.1')
        self.assertEqual((receipt['version'], receipt['counts']['aw_order_units']), ('1.1', 1275))
        order = SalesOrder.objects.get(code='ZM-0150')
        lines = list(order.lines.select_related('item'))
        self.assertEqual(order.status, 'confirmed')
        self.assertGreaterEqual(len(lines), 20)
        self.assertGreaterEqual(sum(l.quantity for l in lines), 1000)
        total = sum(l.quantity * l.price for l in lines)
        for line in lines:
            self.assertGreater(line.price, line.item.planned_cost)
            self.assertEqual(line.item.external_codes['AdventureWorks ProductNumber'],
                             next(p['aw_number'] for p in aw.PRODUCTS if p['code'] == line.item.code))
            self.assertTrue(line.item.bom)
            self.assertTrue(Document.objects.filter(pk=line.item.document_id, status='approved').exists())
        text = DocumentLink.objects.get(order=order).document.text
        amount = f'{total:,.2f}'.replace(',', ' ').replace('.', ',')
        self.assertIn(amount + ' грн', text)
        self.assertEqual(total, D(aw.ORDER['total_uah']))
        self.assertIn('НБУ 44.6819 грн/USD на 2026-10-01: 31 489 328,20 грн (704744.62 USD)', text)
        self.assertIn(f'{len(lines)} позицій, {int(sum(l.quantity for l in lines))} шт.', text)
        provenance = Configuration.objects.get(key='bos4_demo_provenance').value
        self.assertEqual((provenance['aw_sales_order_id'], provenance['pins'], provenance['rate']), (47395, aw.PINS, aw.RATE))
        self.assertEqual((provenance['aw_total_uah'], provenance['scenario_total_uah']), ('31489328.20', '6476450.00'))
        self.assertIn('клієнт ТОВ «Склад-Мережа Схід»', provenance['scenario'])
        self.assertEqual(provenance['aw_work_order_ids'], [j['aw_work_order_id'] for j in aw.JOBS])

    def test_supply_chain_is_seeded_through_the_ordinary_commands(self):
        receipt = self.seed('1.1')
        self.assertEqual((receipt['counts']['aw_jobs'], receipt['counts']['aw_purchases']), (40, len(aw.PURCHASES)))
        order = SalesOrder.objects.get(code='ZM-0150')
        jobs = Production.objects.filter(code__startswith='VZ-0150-').select_related('item', 'line')
        self.assertEqual(jobs.count(), 40)
        for job in jobs:
            self.assertEqual((job.line.order_id, job.line.item_id, job.quantity), (order.pk, job.item_id, job.line.quantity))
            self.assertEqual(job.location.code, 'KM-ZHY-SHOP')
        for n, p in enumerate(aw.PURCHASES, 1):
            po = Purchase.objects.get(code=f'ZK-0150-{n:02d}')
            self.assertEqual((po.item.code, po.quantity, po.price, str(po.due_date)),
                             (p['article'], D(p['quantity']), D(p['price']), p['due_date']))
        for row in aw.STOCK:
            lot = Lot.objects.get(code='KM-L-AW-' + row['article'])
            self.assertEqual((lot.quantity, lot.quality, lot.location.code), (D(row['quantity']), 'approved', 'KM-ZHY-METAL'))

    def test_three_cases_and_public_screen_are_unchanged(self):
        self.seed('1.1')
        components = SalesOrder.objects.get(code='ZM-0141').lines.get(item__code='SM-1800')
        self.assertEqual((components.quantity, components.shipped), (D(120), D(120)))
        self.assertEqual(SalesOrder.objects.get(code='ZM-0144').lines.get(item__code='SHM-2').shipped, D(40))
        self.assertEqual(self.client.get('/api/erp/showcase/').json()['cases'][0]['steps'][0]['text'],
                         'Замовлення на 254 вироби на 1 922 800 грн; під нього закуплено 300 кутників')
        self.assertFalse(Item.objects.filter(code__startswith='KS-', bom=[]).exists())

    def test_monitoring_shows_the_large_order(self):
        self.seed('1.1')
        user = get_user_model().objects.create_user(username='synthetic-ceo', password='synthetic-pass')
        Group.objects.get_or_create(name='ceo')[0].user_set.add(user)
        self.client.force_login(user)
        data = self.client.get('/api/erp/monitoring/').json()
        orders = next(t for t in data['tables'] if t['key'] == 'orders')
        row = next(r for r in orders['rows'] if r['cells'][0] == 'ZM-0150')
        self.assertEqual(row['cells'][4], '0 з 1275')

    def test_versions_never_mix(self):
        self.seed('1.0')
        self.assertFalse(SalesOrder.objects.filter(code='ZM-0150').exists())
        self.assertFalse(Configuration.objects.filter(key='bos4_demo_provenance').exists())
        with self.assertRaisesRegex(CommandError, 'версії 1.0'):
            self.seed('1.1')
        self.assertFalse(SalesOrder.objects.filter(code='ZM-0150').exists())
