"""A07 real database boundaries; no model validation or mocked writes.

Run through verification_settings on a new synthetic test database only.
The allowed boundary examples deliberately preserve signed stock movements,
released zero reservations, zero-price invoices and temporary empty intents.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.db import connection, transaction, IntegrityError, DataError
from django.test import TestCase

from employees.models import Employee
from finance.models import Counterparty, FinancialIntent, Salary, Transaction
from erp.models import (Item, Location, Lot, Movement, Production, Purchase,
                        Reservation, SalesLine, SalesOrder)
from operations.models import AuditEvent, Invoice


D = Decimal


class DatabaseMoneyStockBoundaryTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(full_name='Синтетичний A07', role='Тест')
        self.partner = Counterparty.objects.create(name='Синтетичний A07')
        self.item = Item.objects.create(code='A07-ITEM', name='Синтетичний виріб', currency='EUR')
        self.location = Location.objects.create(code='A07-LOC', name='Синтетичний склад')
        self.lot = Lot.objects.create(code='A07-LOT', item=self.item, location=self.location,
            revision='A', quantity=D('10'), unit_cost=D('2.00'), currency='EUR')
        self.order = SalesOrder.objects.create(code='A07-ORDER', customer=self.partner,
            owner=self.employee, due_date=date(2026, 9, 30), currency='EUR')
        self.line = SalesLine.objects.create(order=self.order, item=self.item, revision='A',
            quantity=D('10'), shipped=D('5'), invoiced=D('2'), price=D('10.00'))
        self.job = Production.objects.create(code='A07-JOB', line=self.line, item=self.item,
            quantity=D('10'), produced=D('3'), revision='A', location=self.location,
            owner=self.employee, due_date=date(2026, 9, 30), planned_cost=D('20.00'),
            actual_cost=D('6.00'), currency='EUR')
        self.purchase = Purchase.objects.create(code='A07-PO', item=self.item, supplier=self.partner,
            quantity=D('10'), received=D('3'), price=D('2.00'), extras=D('1.00'), currency='EUR',
            due_date=date(2026, 9, 30), original_due=date(2026, 9, 30), revision='A')
        self.movement = Movement.objects.create(lot=self.lot, quantity=D('-1.000'),
            kind='shipment', reference='A07-REF', line=self.line, cost=D('2.00'))
        self.invoice = Invoice.objects.create(code='A07-INVOICE', customer=self.partner,
            amount=D('100.00'), paid=D('20.00'), currency='EUR', due_date=date(2026, 9, 30))
        self.tx = Transaction.objects.create(direction='out', amount=D('100.00'), currency='EUR',
            date=date(2026, 9, 11), description='Синтетична A07', category='supplier')
        self.salary = Salary.objects.create(employee=self.employee, amount=D('100.00'), currency='EUR',
            period_year=2026, period_month=9)

    def raw_update(self, row, changes):
        quote = connection.ops.quote_name
        fields = [row._meta.get_field(name) for name in changes]
        sql = 'UPDATE ' + quote(row._meta.db_table) + ' SET ' + ', '.join(
            quote(field.column) + ' = %s' for field in fields) + ' WHERE ' + quote(row._meta.pk.column) + ' = %s'
        params = [str(value) if isinstance(value, Decimal) else value for value in changes.values()]
        with connection.cursor() as cursor:
            cursor.execute(sql, params + [row.pk])
            self.assertEqual(cursor.rowcount, 1)

    def assert_database_rejects(self, row, changes, *, raw=False, capacity=False):
        """A missing CHECK fails while its synthetic bad value is cleaned up.

        With a real IntegrityError the nested atomic block itself must undo
        both the preceding audit insert and the invalid write.  Only the red
        path (no DB rejection) is explicitly rolled back to keep later
        independent subTests from inheriting an invalid fixture.
        """
        model = type(row)
        before = model._base_manager.values().get(pk=row.pk)
        marker = str(uuid4())
        denied = False
        with transaction.atomic():
            try:
                with transaction.atomic():
                    AuditEvent.objects.create(action='a07.constraint_probe', payload={'marker': marker})
                    if raw:
                        self.raw_update(row, changes)
                    else:
                        self.assertEqual(model._base_manager.filter(pk=row.pk).update(**changes), 1)
            except IntegrityError:
                denied = True
            except DataError:
                # PostgreSQL numeric(p,s) can reject overflow before a CHECK
                # is reached.  Only an explicit capacity case accepts this
                # native type error; other DataError results still fail.
                if not capacity:
                    raise
                denied = True
            if not denied:
                transaction.set_rollback(True)
        self.assertTrue(denied, f'DB accepted forbidden {model._meta.label} values: {changes}')
        self.assertEqual(model._base_manager.values().get(pk=row.pk), before)
        self.assertFalse(AuditEvent.objects.filter(action='a07.constraint_probe', payload__marker=marker).exists())

    def test_invoice_amount_capacity_and_paid_range_are_enforced_by_sql(self):
        for changes in ({'amount': D('-0.01')}, {'amount': D('1000000000000.00')},
                        {'paid': D('-0.01')}, {'paid': D('100.01')}):
            with self.subTest(changes=changes):
                self.assert_database_rejects(self.invoice, changes, raw=True,
                    capacity=changes.get('amount') == D('1000000000000.00'))

    def test_purchase_quantity_and_received_are_bounded_in_database(self):
        for changes in ({'quantity': D('0')}, {'quantity': D('-0.001')},
                        {'received': D('-0.001')}, {'received': D('10.001')}):
            with self.subTest(changes=changes):
                self.assert_database_rejects(self.purchase, changes)

    def test_purchase_price_and_extras_cannot_be_negative_via_raw_sql(self):
        for field in ('price', 'extras'):
            with self.subTest(field=field):
                self.assert_database_rejects(self.purchase, {field: D('-0.01')}, raw=True)

    def test_production_quantity_and_produced_are_bounded_in_database(self):
        for changes in ({'quantity': D('0')}, {'quantity': D('-0.001')},
                        {'produced': D('-0.001')}, {'produced': D('10.001')}):
            with self.subTest(changes=changes):
                self.assert_database_rejects(self.job, changes)

    def test_production_planned_and_actual_cost_cannot_be_negative_via_sql(self):
        for field in ('planned_cost', 'actual_cost'):
            with self.subTest(field=field):
                self.assert_database_rejects(self.job, {field: D('-0.01')}, raw=True)

    def test_sales_line_invoiced_shipped_quantity_chain_and_price(self):
        for changes in ({'invoiced': D('-0.001')}, {'invoiced': D('5.001')},
                        {'shipped': D('1.999')}, {'shipped': D('10.001')},
                        {'quantity': D('4.999')}, {'price': D('-0.01')}):
            with self.subTest(changes=changes):
                self.assert_database_rejects(self.line, changes)

    def test_lot_unit_cost_cannot_be_negative_via_raw_sql(self):
        self.assert_database_rejects(self.lot, {'unit_cost': D('-0.01')}, raw=True)

    def test_movement_cost_cannot_be_negative_but_quantity_stays_signed(self):
        self.assertEqual(self.movement.quantity, D('-1.000'))
        self.assert_database_rejects(self.movement, {'cost': D('-0.01')}, raw=True)
        self.movement.refresh_from_db()
        self.assertEqual((self.movement.quantity, self.movement.cost), (D('-1.000'), D('2.00')))

    def test_finance_positive_amount_and_field_capacity_also_hold_below_commands(self):
        for row, overflow in ((self.tx, D('1000000000000.00')),
                              (self.salary, D('10000000000.00'))):
            for amount in (D('0'), D('-0.01'), overflow):
                with self.subTest(model=row._meta.label, amount=amount):
                    self.assert_database_rejects(row, {'amount': amount}, raw=True, capacity=amount == overflow)

    def test_existing_three_currency_domain_is_enforced_below_writers(self):
        for row in (self.item, self.lot, self.order, self.job, self.purchase,
                    self.invoice, self.tx, self.salary):
            with self.subTest(model=row._meta.label):
                self.assert_database_rejects(row, {'currency': 'XYZ'}, raw=True)
                # Valid currency codes still remain independent currencies;
                # these SQL shape tests do not perform conversion or totals.
                for currency in ('EUR', 'USD', 'UAH'):
                    self.raw_update(row, {'currency': currency})
                    row.refresh_from_db()
                    self.assertEqual(row.currency, currency)

    def test_valid_zero_equal_maximum_and_temporary_boundaries_remain_legal(self):
        self.raw_update(self.invoice, {'amount': D('0.00'), 'paid': D('0.00')})
        self.invoice.refresh_from_db()
        self.assertEqual((self.invoice.amount, self.invoice.paid), (D('0.00'), D('0.00')))
        self.raw_update(self.invoice, {'amount': D('999999999999.99'), 'paid': D('999999999999.99')})
        self.invoice.refresh_from_db()
        self.assertEqual((self.invoice.amount, self.invoice.paid), (D('999999999999.99'), D('999999999999.99')))
        self.raw_update(self.tx, {'amount': D('999999999999.99')})
        self.raw_update(self.salary, {'amount': D('9999999999.99')})
        self.tx.refresh_from_db(); self.salary.refresh_from_db()
        self.assertEqual((self.tx.amount, self.salary.amount), (D('999999999999.99'), D('9999999999.99')))
        Purchase.objects.filter(pk=self.purchase.pk).update(received=D('10'), price=D('0'), extras=D('0'))
        Production.objects.filter(pk=self.job.pk).update(produced=D('10'), planned_cost=D('0'), actual_cost=D('0'))
        SalesLine.objects.filter(pk=self.line.pk).update(shipped=D('10'), invoiced=D('10'), price=D('0'))
        Lot.objects.filter(pk=self.lot.pk).update(quantity=D('0'), unit_cost=D('0'))
        Movement.objects.filter(pk=self.movement.pk).update(quantity=D('-0.001'), cost=D('0'))
        reserve = Reservation.objects.create(lot=self.lot, line=self.line, quantity=D('0'))
        reserve.refresh_from_db()
        self.assertEqual(reserve.quantity, D('0'))
        self.movement.refresh_from_db()
        self.assertEqual((self.movement.quantity, self.movement.cost), (D('-0.001'), D('0')))
        with transaction.atomic():
            receipt = FinancialIntent.objects.create(key='a' * 64, payload_hash='b' * 64)
            self.assertEqual((receipt.transaction_id, receipt.salary_id), (None, None))
            receipt.transaction = self.tx
            receipt.save(update_fields=['transaction'])
        receipt.refresh_from_db()
        self.assertEqual((receipt.transaction_id, receipt.salary_id), (self.tx.pk, None))
        # A07 does not rewrite old paid-without-source fixtures: A02 detects
        # that inconsistent historical state when a payment is requested.
        Salary.objects.filter(pk=self.salary.pk).update(status='paid')
        self.salary.refresh_from_db()
        self.assertEqual((self.salary.status, self.salary.transaction_id), ('paid', None))

    def test_invoice_constraint_failure_rolls_back_prior_stock_line_and_audit_writes(self):
        models_rows = ((Lot, self.lot.pk), (SalesLine, self.line.pk), (Invoice, self.invoice.pk))
        before = {model._meta.label: model.objects.values().get(pk=pk) for model, pk in models_rows}
        marker = str(uuid4())
        denied = False
        with transaction.atomic():
            try:
                with transaction.atomic():
                    Lot.objects.filter(pk=self.lot.pk).update(quantity=D('7'))
                    SalesLine.objects.filter(pk=self.line.pk).update(shipped=D('8'))
                    AuditEvent.objects.create(action='a07.constraint_probe', payload={'marker': marker})
                    self.raw_update(self.invoice, {'paid': D('100.01')})
            except IntegrityError:
                denied = True
            if not denied:
                transaction.set_rollback(True)
        self.assertTrue(denied, 'The invoice constraint must reject the final statement')
        for model, pk in models_rows:
            self.assertEqual(model.objects.values().get(pk=pk), before[model._meta.label])
        self.assertFalse(AuditEvent.objects.filter(action='a07.constraint_probe', payload__marker=marker).exists())
