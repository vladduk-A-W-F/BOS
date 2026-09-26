"""Конкретні A04 регресії після 48/48: next-step text та replay result scope."""
import json
from datetime import timedelta

from erp.models import Item, Production, SalesLine, SalesOrder
from operations.models import ActionProposal
from operations.test_access import A04SyntheticCase, text_body


class A04RemainingContextTests(A04SyntheticCase):
    def test_visible_order_next_step_never_names_a_hidden_job_component(self):
        item = Item.objects.create(code='A04-NEXT-ITEM', name='Видимий новий виріб',
                                   method='make', document=self.public_doc)
        order = SalesOrder.objects.create(code='A04-NEXT-ORDER', customer=self.customer,
                                           owner=self.employee, due_date=self.today + timedelta(days=20),
                                           status='confirmed')
        line = SalesLine.objects.create(order=order, item=item, revision='A', quantity=3, price=1)
        # Історична BOM роботи може відрізнятися від поточної специфікації Item.
        # Цю роботу policy вже правильно приховує через закритий компонент.
        job = Production.objects.create(code='A04-CLOSED-JOB', line=line, item=item,
                                         quantity=3, revision='A', owner=self.employee,
                                         location=self.location, due_date=order.due_date,
                                         bom=[{'item_id': self.hidden_item.pk, 'quantity': '1'}])
        for stock_quantity in (10, 0):
            # За stock=10 внутрішня підказка має action; за stock=0 її
            # payload від початку None. Обидві можуть розкрити назву джерела.
            self.hidden_lot.quantity = stock_quantity
            self.hidden_lot.save(update_fields=['quantity'])
            for role in ('manager', 'observer'):
                with self.subTest(role=role, stock_quantity=stock_quantity):
                    client = self.grant(role, 'view_document')
                    snapshot = self.json_get(client, '/api/erp/snapshot/')
                    self.assertIn(order.pk, [row['id'] for row in snapshot['orders']])
                    self.assertNotIn(job.pk, [row['id'] for row in snapshot['jobs']])
                    response = client.get(f'/api/erp/orders/{order.pk}/next/')
                    self.assertEqual(response.status_code, 200, text_body(response))
                    self.assert_no_canaries(response.json(), (self.hidden_item.code, job.code, self.hidden_doc.code))

    def test_replay_rechecks_scope_of_created_result_not_only_original_payload(self):
        client = self.grant('manager', 'view_document')
        response = self.post(client, '/api/erp/preview/', {
            'action': 'erp_order', 'code': 'A04-CREATED-THEN-CLOSED',
            'customer_id': self.customer.pk, 'owner_id': self.employee.pk,
            'due_date': (self.today + timedelta(days=20)).isoformat(), 'currency': 'EUR',
            'lines': [{'item_id': self.item.pk, 'quantity': '2', 'price': '1'}],
        })
        self.assertEqual(response.status_code, 200, text_body(response))
        proposal_id = response.json()['id']
        confirmed = self.post(client, '/api/operations/confirm/', {'proposal_id': proposal_id, 'confirmed': True})
        self.assertEqual(confirmed.status_code, 200, text_body(confirmed))
        order = SalesOrder.objects.get(pk=confirmed.json()['order_id'])
        receipt = ActionProposal.objects.get(pk=proposal_id).receipt
        # Поточні права бачать усі початкові input IDs, але вже не створений
        # об'єкт: до нього додано позицію закритої номенклатури.
        SalesLine.objects.create(order=order, item=self.hidden_item, revision='A', quantity=1, price=1)
        self.assertEqual(client.get(f'/api/erp/orders/{order.pk}/next/').status_code, 404)
        counts = (SalesOrder.objects.count(), SalesLine.objects.count(), ActionProposal.objects.count())
        replay = self.post(client, '/api/operations/confirm/', {'proposal_id': proposal_id, 'confirmed': True})
        self.assertIn(replay.status_code, (403, 404), text_body(replay))
        self.assert_no_canaries(replay.json(), (order.code,))
        self.assertEqual((SalesOrder.objects.count(), SalesLine.objects.count(), ActionProposal.objects.count()), counts)
        self.assertEqual(ActionProposal.objects.get(pk=proposal_id).receipt, receipt)
