"""Additive four-route access matrix; all old gate-4 definitions remain intact."""
import json
import sys
import tempfile
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.test import TestCase,override_settings
from scripts import check_access as checker
from scripts.access_fixtures import SweepFixtures


@override_settings(BOS_DATA_MODE='working',DEBUG=False,PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ImportAccessMatrixTests(TestCase):
    def test_new_four_routes_all_five_roles_and_nine_methods(self):
        sys.modules.setdefault('check_access',checker)
        with tempfile.TemporaryDirectory(prefix='bos-b02-access-media-') as folder,override_settings(MEDIA_ROOT=Path(folder)):
            fixtures=SweepFixtures('operations.test_access');fixtures.build();self.assertEqual(fixtures.issues,[])
            routes=[r for r in checker.catalogue() if r['pattern'].startswith('api/erp/import/')]
            self.assertEqual(len(routes),4);seen=[]
            for row in routes:
                for path in checker.materialize(row,fixtures):
                    for role in checker.ROLES:
                        for method in checker.METHODS:
                            with self.subTest(path=path,role=role,method=method),transaction.atomic():
                                client=fixtures.client(role);data,mode=fixtures.payload(row,path,method,role,client)
                                before=fixtures.state_digest();body=json.dumps(data,ensure_ascii=False) if data is not None else ''
                                response=client.generic(method,path+fixtures.query(row,path),body,content_type='application/json',HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value)
                                expected,_=checker.contract(row,path,method,role)
                                self.assertIn(response.status_code,expected,response.content[:500])
                                defects,_=checker.response_oracle(response,row,path,method,role,fixtures,'full');self.assertFalse(defects,defects)
                                if method!='POST' or role!='ceo' or response.status_code!=200:self.assertEqual(fixtures.state_digest(),before)
                                else:self.assertNotEqual(fixtures.state_digest(),before,'Valid preview must persist its proposal')
                                seen.append((path,role,method));transaction.set_rollback(True)
            self.assertEqual(len(seen),180)
