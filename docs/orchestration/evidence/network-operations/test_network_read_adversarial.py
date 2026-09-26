from decimal import Decimal as D
from unittest.mock import patch
from django.test import RequestFactory
from operations.test_access import A04SyntheticCase
from boss_project.policy import Policy
from erp.models import Lot
from erp import network
from erp.queries import plan_line

class NetworkReadIndependent(A04SyntheticCase):
    def test_document_scope_change_during_projection_refuses_stale_private_rows(self):
        client=self.grant('manager','view_document')
        self.lot.currency='UAH';self.lot.save()
        build=network.build
        def changed(policy,params):
            data=build(policy,params)
            self.assertIn(self.lot.code,[r['code'] for r in data['rows']['lots']])
            self.item.document.access_level='ceo';self.item.document.save(update_fields=['access_level'])
            return data
        with patch('erp.network_views.network.build',side_effect=changed):
            response=client.get('/api/erp/network/?currency=UAH')
        self.assertEqual(response.status_code,409,response.content)
    def test_ua_h_order_does_not_count_eur_stock_at_fulfillment_point(self):
        client=self.grant('ceo','view_document')
        self.order.fulfillment_location=self.location;self.order.currency='UAH';self.order.save()
        self.line.shipped=D(0);self.line.invoiced=D(0);self.line.quantity=D(10);self.line.save()
        self.lot.quantity=D(0);self.lot.save()
        Lot.objects.create(code='REVIEW-EUR-ONLY',item=self.item,location=self.location,revision=self.line.revision,quantity='10.000',quality='approved',unit_cost='3.00',currency='EUR')
        request=RequestFactory().get('/');request.user=self.users['ceo'];request.session=client.session
        result=plan_line(self.line,Policy(request))
        self.assertEqual(D(result['free']),D(0),result)
