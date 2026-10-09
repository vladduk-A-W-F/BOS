"""«Моніторинг» bento figures: the same Policy scope and money rule as the tables, recomputed from the records.

Synthetic demo company only (v1.0, and v1.1 for the large order); read-only.
"""
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TransactionTestCase, override_settings

from operations.models import Invoice
from .balances import invoice_settlement, purchase_open, sales_open
from .bos4_demo import seed_bos4_demo
from .models import Production, Purchase, SalesOrder
from .service import completed_steps, fingerprint


@override_settings(BOS_DATA_MODE='demo', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class BentoTests(TransactionTestCase):
    version = '1.0'

    def setUp(self):
        folder = TemporaryDirectory(prefix='bos4-bento-test-')
        self.addCleanup(folder.cleanup)
        override = override_settings(MEDIA_ROOT=Path(folder.name) / 'media')
        override.enable()
        self.addCleanup(override.disable)
        seed_bos4_demo(version=self.version)

    def get(self, role):
        user = get_user_model().objects.create_user(username='synthetic-' + role, password='synthetic-pass')
        Group.objects.get_or_create(name=role)[0].user_set.add(user)
        self.client.force_login(user)
        before = fingerprint()
        data = self.client.get('/api/erp/monitoring/').json()
        self.assertEqual(fingerprint(), before)
        return data

    def open_orders(self):
        out = []
        for order in SalesOrder.objects.filter(status='confirmed'):
            lines = list(order.lines.all())
            remaining = sum((sales_open(l) for l in lines), D(0))
            if remaining:
                out.append((order, sum((l.quantity for l in lines), D(0)), remaining))
        return out

    def test_ceo_tiles_match_the_records_and_the_tables(self):
        data = self.get('ceo')
        bento, today = data['bento'], date.fromisoformat(data['as_of'])
        orders = self.open_orders()
        table = next(t for t in data['tables'] if t['key'] == 'orders')
        self.assertEqual(bento['orders']['open'], len(orders))
        self.assertEqual(bento['orders']['open'], table['total'])
        self.assertEqual(bento['orders']['late'], sum(o.due_date < today for o, _, _ in orders))
        self.assertEqual(D(str(bento['orders']['units_total'])), sum((t for _, t, _ in orders), D(0)))
        self.assertEqual(D(str(bento['orders']['units_shipped'])), sum((t - r for _, t, r in orders), D(0)))
        top = bento['orders']['top']
        self.assertLessEqual(len(top), 4)
        self.assertEqual([t['ref']['id'] for t in top],
                         [o.pk for o, _, _ in sorted(orders, key=lambda x: (-x[2], x[0].due_date, x[0].code))][:4])
        for tile in top:
            row = next(r for r in table['rows'] if r['ref'] == tile['ref'])
            self.assertEqual(row['cells'][4], f'{tile["shipped"]} з {tile["total"]}')     # the same figure as the table
            self.assertEqual(tile['late'], row['late'])

        jobs = list(Production.objects.all())
        production = bento['production']
        for status in ('planned', 'running', 'done'):
            self.assertEqual(production[status], sum(j.status == status for j in jobs))
        self.assertEqual(production['late'], sum(j.status != 'done' and j.due_date < today for j in jobs))
        running = [j for j in jobs if j.status == 'running']
        self.assertEqual(production['steps_total'], sum(len({s['name'] for s in j.routing}) for j in running))
        self.assertEqual(production['steps_done'],
                         sum(len({s['name'] for s in j.routing} & completed_steps(j)) for j in running))

        purchases = [p for p in Purchase.objects.all() if purchase_open(p)]
        supply = bento['supply']
        self.assertEqual((supply['open'], supply['late']), (len(purchases), sum(p.due_date < today for p in purchases)))
        upcoming = sorted((p for p in purchases if p.due_date >= today), key=lambda p: (p.due_date, p.code))
        self.assertEqual(supply['next']['ref']['id'] if supply['next'] else None, upcoming[0].pk if upcoming else None)

        money = {m['currency']: m for m in bento['money']}
        numbers = {n['key']: n['value'] for n in data['numbers']}
        self.assertEqual(D(money['UAH']['open']), D(str(numbers['invoices'])))
        uah = [i for i in Invoice.objects.filter(currency='UAH')]
        self.assertEqual(D(money['UAH']['paid']), sum((i.paid for i in uah), D(0)))
        self.assertEqual(D(money['UAH']['overdue']),
                         sum((invoice_settlement(i)['receivable'] for i in uah if i.due_date < today), D(0)))
        self.assertRegex(money['UAH']['open'], r'^\d+\.\d{2}$')                          # exact money text

        tasks = next(t for t in data['tables'] if t['key'] == 'tasks')
        self.assertEqual(bento['tasks'], {'open': tasks['total'], 'late': sum(r['late'] for r in tasks['rows'])})
        self.assertEqual(bento['sources']['total'], len(data['sources']))

        ahead = bento['ahead']
        self.assertEqual([a['date'] for a in ahead], [str(today + timedelta(days=n)) for n in range(14)])
        for day in ahead:
            when = date.fromisoformat(day['date'])
            self.assertEqual(day['orders'], sum(o.due_date == when for o, _, _ in orders))
            self.assertEqual(day['deliveries'], sum(p.due_date == when for p in purchases))
            self.assertEqual(day['jobs'], sum(j.status != 'done' and j.due_date == when for j in jobs))
            self.assertEqual(day['invoices'], sum(i.due_date == when and bool(invoice_settlement(i)['receivable'])
                                                  for i in Invoice.objects.all()))
        self.assertGreater(sum(a['orders'] + a['deliveries'] + a['jobs'] for a in ahead), 0)

    def test_observer_gets_counts_without_money(self):
        data = self.get('observer')
        bento = data['bento']
        self.assertEqual(bento['money'], [])
        self.assertTrue(all(day['invoices'] is None for day in bento['ahead']))
        self.assertEqual(bento['orders']['open'], next(t for t in data['tables'] if t['key'] == 'orders')['total'])
        text = repr(bento)
        for invoice in Invoice.objects.all():
            self.assertNotIn(str(invoice.amount), text)

    def test_manager_gets_no_money_tile(self):
        bento = self.get('manager')['bento']
        self.assertEqual(bento['money'], [])
        self.assertTrue(all(day['invoices'] is None for day in bento['ahead']))


class LargeOrderBentoTests(BentoTests):
    version = '1.1'

    def test_the_large_order_leads_the_order_tile(self):
        bento = self.get('ceo')['bento']
        lead = bento['orders']['top'][0]
        self.assertEqual((lead['code'], lead['customer'], lead['shipped'], lead['total']),
                         ('ZM-0150', 'ТОВ «Склад-Мережа Схід»', 270, 1275))
        self.assertEqual((bento['production']['running'] >= 29, bento['production']['steps_done'] > 0), (True, True))
