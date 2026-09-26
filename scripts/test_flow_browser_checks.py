"""Bounded stdlib controls for flow evidence and isolation; no app/browser/server."""
from copy import deepcopy
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock

from scripts import flow_browser_checks as flow


class FlowBrowserControls(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ['BOS_FLOW_TEST_TEMP']).resolve()
        self.assertTrue(root.is_absolute())
        self.assertEqual(root.drive.lower(), 'd:')
        self.folder = tempfile.TemporaryDirectory(prefix='flow-unit-', dir=root)
        self.addCleanup(self.folder.cleanup)
        self.database = Path(self.folder.name) / 'boscheck_synthetic.sqlite3'
        self.origin = 'http://127.0.0.1:54321'
        self.report = {'checks': [{'id': 'existing-gate10', 'passed': True}], 'isolation': {
            'vendor': 'sqlite', 'origin': self.origin, 'database': str(self.database),
            'database_initially_absent': True}}
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.executescript('''
                CREATE TABLE operations_configuration (id INTEGER PRIMARY KEY,key TEXT,value TEXT);
                CREATE TABLE erp_salesorder (id INTEGER PRIMARY KEY,code TEXT);
                CREATE TABLE erp_item (id INTEGER PRIMARY KEY,code TEXT);
                CREATE TABLE erp_salesline (id INTEGER PRIMARY KEY,order_id INTEGER,item_id INTEGER);
                CREATE TABLE erp_purchase (id INTEGER PRIMARY KEY,code TEXT,supplier_id INTEGER,item_id INTEGER);
                CREATE TABLE erp_location (id INTEGER PRIMARY KEY,code TEXT);
                CREATE TABLE erp_lot (id INTEGER PRIMARY KEY,code TEXT,item_id INTEGER,location_id INTEGER,
                                      quantity TEXT,currency TEXT,quality TEXT);
                CREATE TABLE operations_invoice (id INTEGER PRIMARY KEY,code TEXT,amount TEXT,paid TEXT,currency TEXT);
                CREATE TABLE operations_document (id INTEGER PRIMARY KEY,code TEXT,content BLOB);
                CREATE TABLE erp_event (id INTEGER PRIMARY KEY,action TEXT,payload TEXT);
                CREATE TABLE erp_movement (id INTEGER PRIMARY KEY,quantity TEXT);
                CREATE TABLE finance_financialintent (key TEXT PRIMARY KEY,payload_hash TEXT);
                INSERT INTO operations_configuration VALUES (1,'ua_workpoints_dataset','{"synthetic":true,"currency":"UAH"}');
                INSERT INTO erp_salesorder VALUES (1,'UA-DEMO-KY-SO');
                INSERT INTO erp_item VALUES (2,'UA-DEMO-PRODUCT');
                INSERT INTO erp_salesline VALUES (3,1,2);
                INSERT INTO erp_purchase VALUES (4,'UA-DEMO-KY-PO',5,2);
                INSERT INTO erp_location VALUES (6,'UA-DEMO-KY-WH');
                INSERT INTO erp_lot VALUES (7,'UA-DEMO-LV-LOT',2,8,'12.000','UAH','approved');
                INSERT INTO operations_invoice VALUES (9,'UA-DEMO-KY-INV','3600.00','1200.00','UAH');
                INSERT INTO operations_document VALUES (10,'UA-DEMO-CERT',X'66697874757265');
            ''')

    def selected(self):
        return flow.validate_isolation(self.origin, self.database, self.report)

    def facts(self):
        return flow.facts(self.database, self.selected(), 'UI-TRANSFER', 'UI-PAYMENT')

    def test_read_only_oracle_preserves_database_and_refuses_sql_writes(self):
        before = self.database.read_bytes()
        selected = self.selected()
        self.assertEqual(selected['line_id'], 3)
        self.assertEqual(self.facts()['invoice']['paid'], '1200.00')
        connection = flow._connect(self.database)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("UPDATE operations_invoice SET paid='0'")
        finally:
            connection.close()
        self.assertEqual(before, self.database.read_bytes())

    def test_existing_or_wrong_database_and_origin_refused_before_any_browser_call(self):
        for key, value in (('database_initially_absent', False), ('vendor', 'postgres'),
                           ('origin', 'http://127.0.0.1:12345'), ('database', str(self.database.with_name('other.sqlite3')))):
            report = deepcopy(self.report)
            report['isolation'][key] = value
            page = Mock()
            with self.assertRaises(AssertionError):
                flow.run_flow_checks(page, self.origin, self.database, self.database.parent, report)
            self.assertEqual(page.mock_calls, [])
            self.assertFalse(report['flow_complete'])
        for origin in ('https://example.com', 'http://localhost:1234', 'http://owner:secret@127.0.0.1:1234'):
            with self.assertRaises(AssertionError):
                flow.validate_isolation(origin, self.database, self.report)

    def test_missing_or_non_synthetic_seed_is_not_admitted(self):
        for value in ({'synthetic': False, 'currency': 'UAH'}, {'synthetic': True, 'currency': 'EUR'}):
            with closing(sqlite3.connect(self.database)) as connection, connection:
                connection.execute('UPDATE operations_configuration SET value=?', (json.dumps(value),))
            with self.assertRaises(AssertionError):
                self.selected()

    def test_ambiguous_explicit_fixture_never_chooses_first_row(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("INSERT INTO erp_salesorder VALUES (11,'UA-DEMO-KY-SO')")
        with self.assertRaises(AssertionError):
            self.selected()

    def test_transfer_oracle_requires_conservation_destination_and_no_money_change(self):
        before = self.facts()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE erp_lot SET quantity='11.000' WHERE id=7")
            connection.execute("INSERT INTO erp_lot VALUES (11,'UI-TRANSFER',2,6,'1.000','UAH','approved')")
            connection.execute("INSERT INTO erp_movement VALUES (1,'-1.000')")
            connection.execute("INSERT INTO erp_movement VALUES (2,'1.000')")
            connection.execute('INSERT INTO erp_event VALUES (1,?,?)',
                               ('erp_transfer', json.dumps({'code': 'UI-TRANSFER'})))
        after = self.facts()
        flow.validate_transfer(before, after, self.selected())
        for key, value in (('movement_count', 3), ('item_quantity', '13.000'), ('source_quantity', '12.000')):
            bad = {**after, key: value}
            with self.assertRaises(AssertionError):
                flow.validate_transfer(before, bad, self.selected())
        bad = deepcopy(after)
        bad['destination'][0] = (11, 2, 9999, '1.000', 'UAH', 'approved')
        with self.assertRaises(AssertionError):
            flow.validate_transfer(before, bad, self.selected())

    def test_payment_oracle_rejects_duplicate_event_wrong_amount_and_stock_change(self):
        before = self.facts()
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE operations_invoice SET paid='1212.34' WHERE id=9")
            connection.execute('INSERT INTO erp_event VALUES (1,?,?)',
                               ('erp_payment', json.dumps({'reference': 'UI-PAYMENT'})))
        after = self.facts()
        flow.validate_payment(before, after)
        for mutate in (lambda row: row.update(event_count=2),
                       lambda row: row['invoice'].update(paid='1212.35'),
                       lambda row: row.update(movement_count=1)):
            bad = deepcopy(after)
            mutate(bad)
            with self.assertRaises(AssertionError):
                flow.validate_payment(before, bad)
        self.assertNotEqual(before['business_sha256'], after['business_sha256'])

    def test_report_cannot_complete_with_missing_duplicate_or_failed_flow(self):
        report = deepcopy(self.report)
        report.update(flow_schema=flow.SCHEMA, flow_checks=[])
        self.assertFalse(flow.finish_report(report))
        report['flow_checks'] = [{'id': name, 'passed': True} for name in flow.CHECKS]
        self.assertTrue(flow.finish_report(report))
        report['flow_checks'][1] = deepcopy(report['flow_checks'][0])
        self.assertFalse(flow.finish_report(report))
        report['flow_checks'] = [{'id': name, 'passed': name != flow.CHECKS[-1]} for name in flow.CHECKS]
        self.assertFalse(flow.finish_report(report))
        self.assertEqual(report['checks'], self.report['checks'])

    def test_existing_flow_evidence_cannot_be_overwritten(self):
        report = deepcopy(self.report)
        report['flow_schema'] = flow.SCHEMA
        original = deepcopy(report)
        page = Mock()
        with self.assertRaises(AssertionError):
            flow.run_flow_checks(page, self.origin, self.database, self.database.parent, report)
        self.assertEqual(report, original)
        self.assertEqual(page.mock_calls, [])

    def test_replay_invalidated_bundle_requires_refresh_and_explicit_kyiv_before_open(self):
        state = {'bundle': False, 'chosen': None, 'opened': False}
        page = Mock()
        chooser = Mock()
        chooser.locator.return_value.evaluate_all.return_value = [
            {'value': '1', 'text': 'Львів'}, {'value': '2', 'text': 'Київ'}]
        def choose(value):
            self.assertTrue(state['bundle'], 'Choice requires the freshly read bundle')
            state['chosen'] = value
        chooser.select_option.side_effect = choose
        def role(kind, *, name, **kwargs):
            node = Mock()
            if kind == 'combobox':
                self.assertTrue(state['bundle'], 'Replay cleared the previous bundle')
                return chooser
            if name == 'Оновити робочі точки':
                node.click.side_effect = lambda: state.update(bundle=True)
            elif name == 'UA-DEMO-KY-SO':
                def open_record():
                    self.assertTrue(state['bundle'])
                    self.assertEqual(state['chosen'], '2')
                    state['opened'] = True
                node.click.side_effect = open_record
            return node
        page.get_by_role.side_effect = role
        flow._open_order(page, Mock())
        self.assertTrue(state['opened'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
